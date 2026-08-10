export const meta = {
  name: 'pname-fanout-ab',
  description: '상품명 팬아웃 A/B — pname-fanout 과 워커 프롬프트가 같고 모델만 args 로 받는다',
  whenToUse: '모델 A/B 실측 전용(팬아웃-비용.md §모델 A/B). 실전 런은 pname-fanout 을 쓴다.',
  phases: [
    { title: '팬아웃', detail: '워커당 누적 뷰 ≤budgetKB 빈패킹 · 모델은 args.model' },
  ],
}
// args = { runDir, promptPath, batches:[{n,path,viewKB}], budgetKB?:30,
//          model:'sonnet'|'haiku', emphasis?:'워커 프롬프트 끝에 덧붙일 강조 문안' }
//
// pname-fanout.js 와의 차이는 **딱 둘**이다 — 이 둘 말고는 워커 프롬프트·빈패킹·스키마가
// 바이트 단위로 같아야 A/B 가 성립한다:
//   ① 워커 model 이 args 로 온다 (사본을 두 개 두면 조용히 갈라진다 — 한 파일로 묶는다)
//   ② '검증' 스테이지(name_check 를 부르는 sonnet 에이전트 1명)를 뺐다.
//      두 군에 똑같이 실려도 워커 실측에 섞여 들어오는 잡음이라, 호출자가 Bash 로 직접 돌린다.
const args_ = (typeof args === 'string') ? JSON.parse(args) : args
const BUDGET = (args_.budgetKB || 30)
const MODEL = args_.model || 'sonnet'

const pad3 = (n) => String(n).padStart(3, '0')
const BATCHES = args_.batches || (args_.viewKB || []).map((kb, i) => {
  const n = args_.batchNums ? args_.batchNums[i] : i
  return { n, path: `${args_.runDir}/batches/batch_${pad3(n)}.json`, viewKB: kb }
})

// 뷰예산 빈패킹 — 큰 배치부터 first-fit (pname-fanout.js 와 동일 로직 = 같은 묶음이 나온다)
const sorted = [...BATCHES].sort((a, b) => (b.viewKB || 0) - (a.viewKB || 0))
const bins = []
for (const b of sorted) {
  const fit = bins.find(x => x.kb + (b.viewKB || 0) <= BUDGET)
  if (fit) { fit.kb += (b.viewKB || 0); fit.items.push(b) }
  else bins.push({ kb: (b.viewKB || 0), items: [b] })
}
log(`[${MODEL}] 배치 ${BATCHES.length}개 → 워커 ${bins.length}명 (뷰예산 ${BUDGET}KB)`)

const BATCH_RESULT = {
  type: 'object', additionalProperties: false,
  properties: {
    batch: { type: 'integer' }, created: { type: 'integer' },
    held_unclear: { type: 'array', items: { type: 'string' } },
    held_category_doubt: { type: 'array', items: { type: 'string' } },
    held_few_keywords: { type: 'array', items: { type: 'string' } },
    error: { type: 'string' },
  },
  required: ['batch', 'created', 'held_unclear', 'held_category_doubt', 'held_few_keywords', 'error'],
}
const SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: { results: { type: 'array', items: BATCH_RESULT } },
  required: ['results'],
}

phase('팬아웃')
// pname-fanout.js 와 동일한 위치·형식으로 덧붙인다 — 다르면 강조 효과가 그 차이에 섞인다.
const EMPHASIS = args_.emphasis ? `\n\n[강조]\n${args_.emphasis}` : ''
const results = await parallel(bins.map((bin, i) => () =>
  agent(
    `너는 상품명 생성 워커다. 지시서 ${args_.promptPath} 를 Read 하고 그대로 따른다.\n` +
    `맡은 배치 파일 (각각 §0부터 §5까지 독립 수행, 순서대로):\n` +
    bin.items.map(b => `- ${b.path}`).join('\n') +
    `\n산출물은 ${args_.runDir}/named/named_NNN.json (NNN=배치번호 3자리 0채움, batch_007→named_007). ` +
    `배치 하나당 Write 1회. 반환 스키마의 results 배열에 **배치마다 항목 하나씩** 담아 반환한다.` +
    EMPHASIS,
    { label: `pname:${bin.items.map(b => b.n).join(',')}`, phase: '팬아웃',
      model: MODEL, effort: 'low', schema: SCHEMA, agentType: 'fanout-worker' })
))

const done = results.filter(Boolean)
const flat = done.flatMap(r => r.results || [])
return {
  모델: MODEL,
  워커수: bins.length, 완료워커: done.length, 배치결과수: flat.length,
  생성합계: flat.reduce((s, r) => s + (r.created || 0), 0),
  보류: {
    실물불명: flat.flatMap(r => r.held_unclear || []),
    카테고리의심: flat.flatMap(r => r.held_category_doubt || []),
    키워드부족: flat.flatMap(r => r.held_few_keywords || []),
  },
  안내: '검증은 호출자가 run_names.py check 로 직접 돌린다(이 워크플로에는 없다)',
}
