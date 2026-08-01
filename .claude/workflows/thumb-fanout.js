export const meta = {
  name: 'thumb-fanout',
  description: '썸네일 run 팬아웃 — 비전 판단 배치를 이미지예산으로 묶어 Sonnet 워커에 분배 (생성·크레딧은 범위 밖)',
  whenToUse: 'bulsaja-thumbnail SKILL.md run(Workflow 모드)이 지정한 경우에만',
  phases: [
    { title: '선택', detail: '워커당 누적 이미지 ≤24장 · 상품 ≤8건 빈패킹', model: 'sonnet' },
    { title: '오디트', detail: 'results 누락 배치 1회 재팬아웃' },
  ],
}
// args = { runDir: 절대경로, promptPath: 썸네일-워커-프롬프트.md 절대경로,
//          batches: [{ n: 3, path: "...batch_003.json", imgs: 22, count: 4 }...]  // pending만
//          budgetImgs?: 24, maxCount?: 8, retried?: false }
//
// 스크립트는 파일시스템이 없다 — pending 산출은 호출자가 한다:
//   run_thumbs.py pending --run-dir <R>   → 이 args 를 그대로 찍는다.
// 대표옵션 확정건은 prep 이 result_000 에 선기록하고 배치에서 뺐다 — 여기 오는 건
// 비전 판단건뿐이다. **이 워크플로는 results 생성까지다. apply --generate(크레딧 소모·
// 자동반영 위험)는 절대 부르지 않는다 — 이룸님 승인 게이트 뒤 메인이 직접.**
//
// catfix-fanout 에서 검증된 하네스 특성 2개를 그대로 따른다:
//  ① args 가 파싱 안 된 JSON 문자열로 도착할 수 있다 → 문자열이면 파싱.
//  ② tool_use 스키마의 property key 는 ASCII 만 허용(API 400) → 스키마는 ASCII,
//     사람이 읽는 최종 return 객체만 한글.
const args_ = (typeof args === 'string') ? JSON.parse(args) : args
const BUDGET = (args_.budgetImgs || 24)
const MAXCOUNT = (args_.maxCount || 8)

// 빈패킹 — 큰 배치부터 first-fit. 상품당 이미지가 최대 6장(대표1+후보5)이라 기본
// 배치(10건)면 배치 하나가 예산을 단독 초과한다 → SKILL.md 가 prep --batch-size 4 를
// 권고한다. 단독 초과 배치는 혼자 1워커(쪼갤 수 없다).
const sorted = [...args_.batches].sort((a, b) => (b.imgs || 0) - (a.imgs || 0))
const bins = []
for (const b of sorted) {
  const fit = bins.find(x => x.imgs + (b.imgs || 0) <= BUDGET
    && x.count + (b.count || 0) <= MAXCOUNT)
  if (fit) { fit.imgs += (b.imgs || 0); fit.count += (b.count || 0); fit.items.push(b) }
  else bins.push({ imgs: (b.imgs || 0), count: (b.count || 0), items: [b] })
}
const totalCount = args_.batches.reduce((s, b) => s + (b.count || 0), 0)
log(`배치 ${args_.batches.length}개(상품 ${totalCount}건) → 워커 ${bins.length}명 ` +
  `(이미지예산 ${BUDGET}장 · 상품상한 ${MAXCOUNT}건)`)

// 워커 1명이 배치 여러 개를 받으므로 반환은 **배치별 배열**이어야 한다.
const BATCH_RESULT = {
  type: 'object', additionalProperties: false,
  properties: {
    batch: { type: 'integer' },
    done: { type: 'integer' },
    held: { type: 'array', items: { type: 'string' } },
    error: { type: 'string' },
  },
  required: ['batch', 'done', 'held', 'error'],
}
const SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: { results: { type: 'array', items: BATCH_RESULT } },
  required: ['results'],
}

function prompt(bin) {
  return `너는 불사자 썸네일 기준이미지 선택 워커다. 지시서 ${args_.promptPath} 를 Read 하고 그대로 따른다.\n` +
    `절대 금지: apply --generate·스크립트·불사자 MCP 실행(크레딧·자동반영 위험).\n` +
    `맡은 배치 파일 (각각 §1부터 §4까지 독립 수행, 순서대로):\n` +
    bin.items.map(b => `  - 배치 ${b.n}: ${b.path}  (상품 ${b.count}건 · 이미지 ${b.imgs}장)`).join('\n') +
    `\n\n산출물은 ${args_.runDir}/results/result_NNN.json (NNN=배치번호 3자리 0채움).\n` +
    `배치 하나당 Write 1회. 반환은 배치별 결과 배열(results)만.`
}

phase('선택')
// 이 팬아웃은 세션 기본 가이드라인(동시 에이전트 ≤15)을 스킬 지시로 덮어쓴다 —
// 워커는 디스크에만 쓰고 상호 간섭이 없다. 상한은 이미지예산과 하네스 동시성 캡이 관리한다.
const first = await parallel(bins.map((bin, i) => () =>
  agent(prompt(bin), {
    label: `썸네일:${bin.items.map(b => b.n).join(',')}`,
    phase: '선택', schema: SCHEMA, model: 'sonnet', effort: 'low',
  })))

const rows = first.filter(Boolean).flatMap(r => r.results || [])
const done = new Set(rows.filter(r => !r.error).map(r => r.batch))

// 오디트 — 결과를 못 낸 배치(워커가 죽었거나 error 를 담은 것)를 1회만 다시 돌린다.
phase('오디트')
const missing = args_.batches.filter(b => !done.has(b.n))
let retryRows = []
if (missing.length && !args_.retried) {
  log(`미완 배치 ${missing.length}개 → 재팬아웃 1회 (${missing.map(b => b.n).join(',')})`)
  const rbins = missing.map(b => ({ imgs: b.imgs || 0, count: b.count || 0, items: [b] }))
  const again = await parallel(rbins.map(bin => () =>
    agent(prompt(bin), {
      label: `재선택:${bin.items[0].n}`,
      phase: '오디트', schema: SCHEMA, model: 'sonnet', effort: 'low',
    })))
  retryRows = again.filter(Boolean).flatMap(r => r.results || [])
} else if (missing.length) {
  log(`미완 배치 ${missing.length}개 — 이미 재시도한 run 이라 여기서 멈춘다`)
}

const all = [...rows, ...retryRows]
const ok = all.filter(r => !r.error)
const okSet = new Set(ok.map(r => r.batch))
const stillMissing = args_.batches.filter(b => !okSet.has(b.n)).map(b => b.n)

return {
  배치: args_.batches.length,
  워커: bins.length,
  완료배치: okSet.size,
  선택: ok.reduce((s, r) => s + (r.done || 0), 0),
  보류: ok.flatMap(r => r.held || []),
  오류: all.filter(r => r.error).map(r => ({ 배치: r.batch, 사유: r.error })),
  재팬아웃필요배치: stillMissing,
  다음: stillMissing.length
    ? `배치 ${stillMissing.join(',')} 미완 — run_thumbs.py pending 으로 다시 확인 후 재호출`
    : `run_thumbs.py apply --run-dir ${args_.runDir} 미리보기까지만. ` +
      `--generate 는 크레딧 소모 — 이룸님 승인(게이트1) 후 메인이 직접 부른다.`,
}
