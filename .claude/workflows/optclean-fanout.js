export const meta = {
  name: 'optclean-fanout',
  description: '옵션정리 run 팬아웃 — 배치를 이미지예산+상품수 상한으로 묶어 Sonnet 워커에 분배',
  whenToUse: 'bulsaja-option-cleanup SKILL.md run(Workflow 모드)이 지정한 경우에만',
  phases: [
    { title: '판단', detail: '워커당 누적 이미지 ≤16장 · 상품 ≤10건 빈패킹 (기본 sonnet)' },
    { title: '오디트', detail: 'results 누락 배치 1회 재팬아웃' },
  ],
}
// args = { runDir: 절대경로, promptPath: 옵션-워커-프롬프트.md 절대경로,
//          model?: A/B 실측 전용 모델 오버라이드(기본 sonnet),
//          emphasis?: 워커 프롬프트 끝에 덧붙일 강조 문안(재팬아웃·A/B 용, 기본 없음),
//          batches: [{ n: 7, path: "...batch_007.json", imgs: 23, count: 5 }...]  // pending만
//          budgetImgs?: 16, maxCount?: 10, retried?: false }
//
// 스크립트는 파일시스템이 없다 — pending 산출은 호출자가 한다:
//   run_options.py pending --run-dir <R>   → 이 args 를 그대로 찍는다.
// 정본은 디스크(results/result_NNN.json). 이 run 이 죽어도 재호출 시 호출자가 pending 을 다시 계산한다.
//
// catfix-fanout 에서 검증된 하네스 특성 2개를 그대로 따른다:
//  ① args 가 파싱 안 된 JSON 문자열로 도착할 수 있다 → 문자열이면 파싱.
//  ② tool_use 스키마의 property key 는 ASCII 만 허용(API 400) → 스키마는 ASCII,
//     사람이 읽는 최종 return 객체만 한글.
const args_ = (typeof args === 'string') ? JSON.parse(args) : args

// 워커 모델. 기본은 sonnet 이고 `args.model` 로만 가른다 — **사본 워크플로를 두 개 두면
// 지시서가 조용히 갈라진다**(2026-08-07 상품명·썸네일 A/B 에서 두 번 확인한 교훈).
const MODEL = args_.model || 'sonnet'
const BUDGET = (args_.budgetImgs || 16)
const MAXCOUNT = (args_.maxCount || 10)

// 빈패킹 — 큰 배치부터 first-fit. 예산 축은 catfix 처럼 이미지 장수인데(대표+옵션값),
// 옵션은 **텍스트도 크다**(상품당 판매행 4~28개) → 상품수 상한을 2차 제약으로 건다.
// 배치의 imgs 는 상한이지 실열람이 아니다(지시서 §0 열람 규율이 실비용을 억제한다).
// 이미지가 예산을 단독 초과하는 배치는 혼자 1워커(쪼갤 수 없다).
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
// 마지막 배치만 담으면 집계가 1/N 로 축소되고 앞 배치의 보류 pid 가 유실된다.
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

// 재팬아웃·A/B 강조 문안. 붙이는 위치·형식이 두 군에서 다르면 강조 효과가 그 차이에
// 섞인다(pname-fanout-ab 와 같은 관례로 맞춘다). 없으면 프롬프트가 바이트 단위로 종전과 같다.
const EMPHASIS = args_.emphasis ? `\n\n[강조]\n${args_.emphasis}` : ''

function prompt(bin) {
  return `너는 불사자 옵션 정리 워커다. 지시서 ${args_.promptPath} 를 Read 하고 그대로 따른다.\n` +
    `맡은 배치 파일 (각각 §0부터 §5까지 독립 수행, 순서대로):\n` +
    bin.items.map(b => `  - 배치 ${b.n}: ${b.path}  (상품 ${b.count}건 · 이미지 ${b.imgs}장)`).join('\n') +
    `\n\n산출물은 ${args_.runDir}/results/result_NNN.json (NNN=배치번호 3자리 0채움).\n` +
    `배치 하나당 Write 1회. 반환은 배치별 결과 배열(results)만.` + EMPHASIS
}

phase('판단')
// 이 팬아웃은 세션 기본 가이드라인(동시 에이전트 ≤15)을 스킬 지시로 덮어쓴다 —
// 워커는 디스크에만 쓰고 상호 간섭이 없다. 상한은 이미지예산과 하네스 동시성 캡이 관리한다.
const first = await parallel(bins.map((bin, i) => () =>
  agent(prompt(bin), {
    label: `옵션:${bin.items.map(b => b.n).join(',')}`,
    phase: '판단', schema: SCHEMA, model: MODEL, effort: 'low',
  })))

const rows = first.filter(Boolean).flatMap(r => r.results || [])
const done = new Set(rows.filter(r => !r.error).map(r => r.batch))

// 오디트 — 결과를 못 낸 배치(워커가 죽었거나 error 를 담은 것)를 1회만 다시 돌린다.
// 존재 파일 검증은 죽은 워커를 못 잡는다 — 배치번호로 대조해야 한다.
phase('오디트')
const missing = args_.batches.filter(b => !done.has(b.n))
let retryRows = []
if (missing.length && !args_.retried) {
  log(`미완 배치 ${missing.length}개 → 재팬아웃 1회 (${missing.map(b => b.n).join(',')})`)
  const rbins = missing.map(b => ({ imgs: b.imgs || 0, count: b.count || 0, items: [b] }))
  const again = await parallel(rbins.map(bin => () =>
    agent(prompt(bin), {
      label: `재판단:${bin.items[0].n}`,
      phase: '오디트', schema: SCHEMA, model: MODEL, effort: 'low',
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
  계획: ok.reduce((s, r) => s + (r.done || 0), 0),
  보류: ok.flatMap(r => r.held || []),
  오류: all.filter(r => r.error).map(r => ({ 배치: r.batch, 사유: r.error })),
  재팬아웃필요배치: stillMissing,
  다음: stillMissing.length
    ? `배치 ${stillMissing.join(',')} 미완 — run_options.py pending 으로 다시 확인 후 재호출`
    : `run_options.py apply --run-dir ${args_.runDir} 로 미리보기 → Claude 표본검수 → ` +
      `바로 --commit (승인 대기 없음, 2026-08-06 — 의심건은 보류로 빼고 종합보고).`,
}
