export const meta = {
  name: 'thumb-fanout-haiku',
  description: '썸네일 팬아웃 — 기본은 기준이미지 선택(run) 배치, mode:audit 이면 정합검사, mode:verdict 면 생성본 3축 판정 배치를 이미지예산으로 묶어 Sonnet 워커에 분배 (생성·크레딧은 범위 밖)',
  whenToUse: 'bulsaja-thumbnail SKILL.md run/audit/verdict(Workflow 모드)이 지정한 경우에만',
  phases: [
    { title: '선택', detail: '워커당 누적 이미지 ≤24장 · 상품 ≤8건 빈패킹', model: 'haiku' },
    { title: '오디트', detail: 'results 누락 배치 1회 재팬아웃' },
  ],
}
// args = { runDir: 절대경로, promptPath: 지시서 절대경로(run=썸네일-워커-프롬프트 /
//          audit=정합검사-판정기준 / verdict=검수-판정기준), mode?: 'audit'|'verdict',
//          batches: [{ n: 3, path: "...batch_003.json", imgs: 22, count: 4 }...]  // pending만
//          budgetImgs?: 24, maxCount?: 8, retried?: false }
//
// 스크립트는 파일시스템이 없다 — pending 산출은 호출자가 한다:
//   run_thumbs.py pending --run-dir <R> [--audit|--verdict]   → 이 args 를 그대로 찍는다.
//   (verdict 배치 자체는 run_thumbs.py verdict --run-dir <R> 가 만든다)
// 세 모드는 결과 폴더가 전부 달라(results/ · audit_results/ · verdict/results/)
// **같은 run-dir 에서 병렬 실행이 안전**하다 — 정합검사·검수 판정은 크레딧 0(판정뿐).
// 대표옵션 확정건은 prep 이 result_000 에 선기록하고 배치에서 뺐다 — 여기 오는 건
// 비전 판단건뿐이다. **이 워크플로는 results 생성까지다. apply --generate 는 절대
// 부르지 않는다 — 자동반영 방어·복원이 걸린 구간이라 메인이 직접 바로 부른다
// (승인 대기 없음, 2026-08-06 이룸님).**
//
// catfix-fanout 에서 검증된 하네스 특성 2개를 그대로 따른다:
//  ① args 가 파싱 안 된 JSON 문자열로 도착할 수 있다 → 문자열이면 파싱.
//  ② tool_use 스키마의 property key 는 ASCII 만 허용(API 400) → 스키마는 ASCII,
//     사람이 읽는 최종 return 객체만 한글.
const args_ = (typeof args === 'string') ? JSON.parse(args) : args
const AUDIT = args_.mode === 'audit'
const VERDICT = args_.mode === 'verdict'
const OUT = AUDIT ? 'audit_results/audit_result_NNN.json'
  : VERDICT ? 'verdict/results/vresult_NNN.json'
    : 'results/result_NNN.json'
const KIND = AUDIT ? '정합' : VERDICT ? '검수' : '썸네일'
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
  const head = AUDIT
    ? `너는 불사자 썸네일 정합검사 워커다. 판정기준 ${args_.promptPath} 를 Read 하고 그대로 따른다.\n` +
      `상품마다 [대표옵션이미지경로 | 현재대표경로] 2장을 각 1회 Read 해 같은 물건인지 판정한다\n` +
      `(일치/불일치/대조불가 — 불일치는 사유 필수). 크레딧 0 — 어떤 생성·MCP·스크립트도 부르지 않는다.\n`
    : VERDICT
      ? `너는 불사자 썸네일 검수 판정 워커다. 판정기준 ${args_.promptPath} 를 Read 하고 그대로 따른다.\n` +
        `상품마다 [대표옵션경로 | 생성본경로 | 기존대표경로(있으면)] 을 각 1회 Read 해 3축으로 판정한다\n` +
        `(사용가능/주의/제외/제외(대표옵션의심)/제외(글자변조)/제외(기준이미지없음) — 제외·주의는 사유 필수).\n` +
        `제품 정확성 축은 절대 자동 통과 금지. 크레딧 0 — 어떤 생성·MCP·스크립트도 부르지 않는다.\n`
      : `너는 불사자 썸네일 기준이미지 선택 워커다. 지시서 ${args_.promptPath} 를 Read 하고 그대로 따른다.\n` +
        `절대 금지: apply --generate·스크립트·불사자 MCP 실행(크레딧·자동반영 위험).\n`
  const scope = (AUDIT || VERDICT) ? '각각 독립 수행, 순서대로' : '각각 §0부터 §5까지 독립 수행, 순서대로'
  return head +
    `맡은 배치 파일 (${scope}):\n` +
    bin.items.map(b => `  - 배치 ${b.n}: ${b.path}  (상품 ${b.count}건 · 이미지 ${b.imgs}장)`).join('\n') +
    `\n\n산출물은 ${args_.runDir}/${OUT} (NNN=배치번호 3자리 0채움).\n` +
    `배치 하나당 Write 1회. **배치의 모든 상품을 넣는다**(빠뜨리면 미판정이 '사용가능'으로 반영된다).\n` +
    `반환은 배치별 결과 배열(results)만` +
    (AUDIT ? ` — done=판정 건수, held=대조불가 상품id.`
      : VERDICT ? ` — done=판정 건수, held=제외·주의 상품id.` : `.`)
}

phase('선택')
// 이 팬아웃은 세션 기본 가이드라인(동시 에이전트 ≤15)을 스킬 지시로 덮어쓴다 —
// 워커는 디스크에만 쓰고 상호 간섭이 없다. 상한은 이미지예산과 하네스 동시성 캡이 관리한다.
const first = await parallel(bins.map((bin, i) => () =>
  agent(prompt(bin), {
    label: `${KIND}:${bin.items.map(b => b.n).join(',')}`,
    phase: '선택', schema: SCHEMA, model: 'haiku', effort: 'low', agentType: 'fanout-worker',
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
      label: `재${KIND}:${bin.items[0].n}`,
      phase: '오디트', schema: SCHEMA, model: 'haiku', effort: 'low', agentType: 'fanout-worker',
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
    ? `배치 ${stillMissing.join(',')} 미완 — run_thumbs.py pending${AUDIT ? ' --audit' : VERDICT ? ' --verdict' : ''} 으로 다시 확인 후 재호출`
    : AUDIT
      ? `run_thumbs.py audit --run-dir ${args_.runDir} --commit 으로 판정을 현황판에 반영한다 ` +
        `(불일치→재작업 flag · 일치→완료(정합확인) · 대조불가→집계만).`
      : VERDICT
        ? `run_thumbs.py verdict --run-dir ${args_.runDir} --commit 으로 decisions.json 을 만든 뒤 ` +
          `apply --commit 으로 반영한다(누락이 있으면 commit 이 차단한다).`
        : `메인이 run_thumbs.py apply --run-dir ${args_.runDir} --generate 를 바로 부른다 ` +
          `(승인 대기 없음, 2026-08-06 — 워크플로·워커는 부르지 않는다).`,
}
