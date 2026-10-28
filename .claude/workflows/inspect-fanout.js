export const meta = {
  name: 'inspect-fanout',
  description: '소싱 검수 팬아웃 — 배치를 이미지예산으로 묶어 Sonnet 워커에 pass/drop 판정 분배',
  whenToUse: 'sourcing-inspect SKILL.md 가 지정한 경우에만 (run_inspect.py pending 출력을 args 로)',
  phases: [
    { title: '판정', detail: '워커당 누적 썸네일 ≤20장 빈패킹', model: 'sonnet' },
    { title: '오디트', detail: '결과 없는 배치 1회 재팬아웃' },
  ],
}
// args = run_inspect.py pending 출력 그대로:
//   { runDir, promptPath, stage, batches: [{ n, path, count, imgs }], budgetImgs?, retried? }
// 스크립트는 파일시스템이 없다 — 정본은 디스크(judged/judged_NNN.json), pending 계산은 호출자.
// catfix-fanout 실측 하네스 특성: args 가 JSON 문자열로 올 수 있고, 스키마 key 는 ASCII 만.
const args_ = (typeof args === 'string') ? JSON.parse(args) : args
const BUDGET = (args_.budgetImgs || 20)
// 판정 모델 — 기본 sonnet. A/B 비교 때만 args.model 로 바꾼다
const MODEL = args_.model || 'sonnet'
// 대량 run 은 args 를 줄이려고 batches 대신 compact [[n,count,imgs],...] 로 줄 수 있다(경로는 runDir 에서 만든다).
// range = {from,to,count,imgs} 균일 배치 축약(마지막 배치는 lastCount/lastImgs 로 덮는다).
if (!args_.batches && !args_.compact && args_.range) {
  const r = args_.range
  args_.compact = []
  for (let n = r.from; n <= r.to; n++) {
    args_.compact.push(n === r.to && r.lastCount ? [n, r.lastCount, r.lastImgs || 0] : [n, r.count, r.imgs])
  }
}
if (!args_.batches && args_.compact) {
  args_.batches = args_.compact.map(([n, count, imgs]) => ({
    n, count, imgs, path: `${args_.runDir}/batches/batch_${String(n).padStart(3, '0')}.json`,
  }))
}

// 이미지 예산 빈패킹 — 큰 배치부터 first-fit. 단독 초과 배치는 혼자 1워커.
const sorted = [...args_.batches].sort((a, b) => (b.imgs || 0) - (a.imgs || 0))
const bins = []
for (const b of sorted) {
  const fit = bins.find(x => x.imgs + (b.imgs || 0) <= BUDGET)
  if (fit) { fit.imgs += (b.imgs || 0); fit.items.push(b) }
  else bins.push({ imgs: (b.imgs || 0), items: [b] })
}
const totalCount = args_.batches.reduce((s, b) => s + (b.count || 0), 0)
log(`${args_.stage}차 · 배치 ${args_.batches.length}개(상품 ${totalCount}건) → 워커 ${bins.length}명`)

const BATCH_RESULT = {
  type: 'object', additionalProperties: false,
  properties: {
    batch: { type: 'integer' },
    judged: { type: 'integer' },
    dropped: { type: 'integer' },
    error: { type: 'string' },
    thumbs_read: { type: 'integer' },
  },
  required: ['batch', 'judged', 'dropped', 'error', 'thumbs_read'],
}
const SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: { results: { type: 'array', items: BATCH_RESULT } },
  required: ['results'],
}

function prompt(bin) {
  return `너는 소싱 검수 판정 워커다. 지시서 ${args_.promptPath} 를 Read 하고 그대로 따른다.\n` +
    `맡은 배치 파일 (각각 독립 수행, 순서대로):\n` +
    bin.items.map(b => `  - 배치 ${b.n}: ${b.path}  (상품 ${b.count}건)`).join('\n') +
    `\n\n산출물은 ${args_.runDir}/judged/judged_NNN.json (NNN=배치번호 3자리 0채움). 배치 하나당 Write 1회.\n` +
    (args_.stage === 2
      ? `\n**stage 2: 상품마다 tb_thumb 이미지를 Read 도구로 실제로 열어 보고 판정한다. 텍스트(tb_title)만 보고 판정하면 실패다.**\n`
      : `\n지시서가 thumb 확인을 요구하는 상품(정체 불명·액체 의심·캐릭터 의심 등)은 thumb 를 Read 도구로 실제로 연다.\n`) +
    `note 에는 무슨 물건인지와 판정 근거를 쓴다(상품명 복사 금지). 판정은 상품마다 직접 한다.\n` +
    `반환은 배치별 결과 배열(results)만: batch, judged(판정 건수), dropped(drop 건수), error(정상이면 빈 문자열), thumbs_read(그 배치에서 Read 로 연 썸네일 수).`
}

phase('판정')
const first = await parallel(bins.map(bin => () =>
  agent(prompt(bin), {
    label: `판정:${bin.items.map(b => b.n).join(',')}`,
    phase: '판정', schema: SCHEMA, model: MODEL, agentType: 'fanout-worker',
  })))

const rows = first.filter(Boolean).flatMap(r => r.results || [])
// 2차는 썸네일을 거의 안 연 배치를 미완으로 본다 — 2026-10-18 전량 run 에서 워커가 텍스트만 보고 끝냈다
const cnt = Object.fromEntries(args_.batches.map(b => [b.n, b.count || 0]))
const looked = r => args_.stage !== 2 || (r.thumbs_read || 0) >= Math.floor((cnt[r.batch] || 0) * 0.8)
const done = new Set(rows.filter(r => !r.error && looked(r)).map(r => r.batch))

// 오디트 — 결과를 못 낸 배치를 1회만 다시 돌린다(배치번호로 대조).
phase('오디트')
const missing = args_.batches.filter(b => !done.has(b.n))
let retryRows = []
if (missing.length && !args_.retried) {
  log(`미완 배치 ${missing.length}개 → 재팬아웃 1회 (${missing.map(b => b.n).join(',')})`)
  const again = await parallel(missing.map(b => () =>
    agent(prompt({ imgs: b.imgs || 0, items: [b] }), {
      label: `재판정:${b.n}`,
      phase: '오디트', schema: SCHEMA, model: MODEL, agentType: 'fanout-worker',
    })))
  retryRows = again.filter(Boolean).flatMap(r => r.results || [])
} else if (missing.length) {
  log(`미완 배치 ${missing.length}개 — 이미 재시도한 run 이라 여기서 멈춘다`)
}

const all = [...rows, ...retryRows]
const okSet = new Set(all.filter(r => !r.error).map(r => r.batch))
const stillMissing = args_.batches.filter(b => !okSet.has(b.n)).map(b => b.n)

return {
  배치: args_.batches.length,
  워커: bins.length,
  완료배치: okSet.size,
  판정: all.filter(r => !r.error).reduce((s, r) => s + (r.judged || 0), 0),
  탈락: all.filter(r => !r.error).reduce((s, r) => s + (r.dropped || 0), 0),
  오류: all.filter(r => r.error).map(r => ({ 배치: r.batch, 사유: r.error })),
  재팬아웃필요배치: stillMissing,
  다음: stillMissing.length
    ? `배치 ${stillMissing.join(',')} 미완 — run_inspect.py pending 으로 확인 후 재호출`
    : `run_inspect.py merge → report --run-dir ${args_.runDir}`,
}
