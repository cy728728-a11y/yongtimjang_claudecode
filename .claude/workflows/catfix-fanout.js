export const meta = {
  name: 'catfix-fanout',
  description: '카테고리 Step3a 팬아웃 — 증거 4종 정체판별을 이미지예산으로 묶어 Sonnet 워커에 분배',
  whenToUse: 'bulsaja-category-fix SKILL.md Step 3a(Workflow 모드)가 지정한 경우에만',
  phases: [
    { title: '판정', detail: '워커당 누적 썸네일 ≤16장 빈패킹', model: 'sonnet' },
    { title: '오디트', detail: 'named 누락 배치 1회 재팬아웃' },
  ],
}
// args = { runDir: 절대경로, promptPath: 판정-워커-프롬프트.md 절대경로,
//          batches: [{ n: 7, path: "...batch_007.json", imgs: 6, count: 8 }...]  // pending만
//          budgetImgs?: 16, retried?: false }
//
// 스크립트는 파일시스템이 없다 — pending 산출은 호출자가 한다:
//   run_all.py pending --run-dir <R>   → 이 args 를 그대로 찍는다.
// 정본은 디스크(named_NNN.json). 이 run 이 죽어도 재호출 시 호출자가 pending 을 다시 계산한다.
//
// pname-fanout 스모크(2026-07-29)에서 실측한 하네스 특성 2개를 그대로 따른다:
//  ① args 가 파싱 안 된 JSON 문자열로 도착할 수 있다 → 문자열이면 파싱.
//  ② tool_use 스키마의 property key 는 ASCII 만 허용(API 400) → 스키마는 ASCII,
//     사람이 읽는 최종 return 객체만 한글.
const args_ = (typeof args === 'string') ? JSON.parse(args) : args
const BUDGET = (args_.budgetImgs || 16)

// 이미지 예산 빈패킹 — 큰 배치부터 first-fit. 상품명 팬아웃은 '뷰 KB'가 비용을 지배했지만
// 여기선 **썸네일 장수**가 지배한다(텍스트 3종은 배치당 몇 KB).
// 이미지가 예산을 단독 초과하는 배치는 혼자 1워커(쪼갤 수 없다).
const sorted = [...args_.batches].sort((a, b) => (b.imgs || 0) - (a.imgs || 0))
const bins = []
for (const b of sorted) {
  const fit = bins.find(x => x.imgs + (b.imgs || 0) <= BUDGET)
  if (fit) { fit.imgs += (b.imgs || 0); fit.items.push(b) }
  else bins.push({ imgs: (b.imgs || 0), items: [b] })
}
const totalCount = args_.batches.reduce((s, b) => s + (b.count || 0), 0)
log(`배치 ${args_.batches.length}개(상품 ${totalCount}건) → 워커 ${bins.length}명 (이미지예산 ${BUDGET}장)`)

// 워커 1명이 배치 여러 개를 받으므로 반환은 **배치별 배열**이어야 한다.
// 마지막 배치만 담으면 집계가 1/N 로 축소되고 앞 배치의 보류 pid 가 유실된다.
const BATCH_RESULT = {
  type: 'object', additionalProperties: false,
  properties: {
    batch: { type: 'integer' },
    created: { type: 'integer' },
    held_unclear: { type: 'array', items: { type: 'string' } },
    error: { type: 'string' },
  },
  required: ['batch', 'created', 'held_unclear', 'error'],
}
const SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: { results: { type: 'array', items: BATCH_RESULT } },
  required: ['results'],
}

function prompt(bin) {
  return `너는 불사자 카테고리 판정 워커다. 지시서 ${args_.promptPath} 를 Read 하고 그대로 따른다.\n` +
    `맡은 배치 파일 (각각 §1부터 §4까지 독립 수행, 순서대로):\n` +
    bin.items.map(b => `  - 배치 ${b.n}: ${b.path}  (상품 ${b.count}건 · 썸네일 ${b.imgs}장)`).join('\n') +
    `\n\n산출물은 ${args_.runDir}/named/named_NNN.json (NNN=배치번호 3자리 0채움).\n` +
    `배치 하나당 Write 1회. 반환은 배치별 결과 배열(results)만.`
}

phase('판정')
// 이 팬아웃은 세션 기본 가이드라인(동시 에이전트 ≤15)을 스킬 지시로 덮어쓴다 —
// 워커는 디스크에만 쓰고 상호 간섭이 없다. 상한은 이미지예산과 하네스 동시성 캡이 관리한다.
const first = await parallel(bins.map((bin, i) => () =>
  agent(prompt(bin), {
    label: `판정:${bin.items.map(b => b.n).join(',')}`,
    phase: '판정', schema: SCHEMA, model: 'sonnet', effort: 'low',
  })))

const rows = first.filter(Boolean).flatMap(r => r.results || [])
const done = new Set(rows.filter(r => !r.error).map(r => r.batch))

// 오디트 — 결과를 못 낸 배치(워커가 죽었거나 error 를 담은 것)를 1회만 다시 돌린다.
// check 류 검증은 '존재하는 파일'만 보므로 죽은 워커를 못 잡는다. 배치번호로 대조해야 한다.
phase('오디트')
const missing = args_.batches.filter(b => !done.has(b.n))
let retryRows = []
if (missing.length && !args_.retried) {
  log(`미완 배치 ${missing.length}개 → 재팬아웃 1회 (${missing.map(b => b.n).join(',')})`)
  const rbins = missing.map(b => ({ imgs: b.imgs || 0, items: [b] }))
  const again = await parallel(rbins.map(bin => () =>
    agent(prompt(bin), {
      label: `재판정:${bin.items[0].n}`,
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
  생성: ok.reduce((s, r) => s + (r.created || 0), 0),
  보류_정체불명: ok.flatMap(r => r.held_unclear || []),
  오류: all.filter(r => r.error).map(r => ({ 배치: r.batch, 사유: r.error })),
  재팬아웃필요배치: stillMissing,
  다음: stillMissing.length
    ? `배치 ${stillMissing.join(',')} 미완 — run_all.py pending 으로 다시 확인 후 재호출`
    : `run_all.py auto --run-dir ${args_.runDir} 를 백그라운드로 실행 (merge→finish→steer)`,
}
