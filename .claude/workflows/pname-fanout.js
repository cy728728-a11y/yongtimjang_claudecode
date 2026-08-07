export const meta = {
  name: 'pname-fanout',
  description: '상품명 Step3 팬아웃 — pending 배치를 뷰예산으로 묶어 Sonnet 워커에 분배',
  whenToUse: 'product-name SKILL.md Step 3(Workflow 모드)이 지정한 경우에만',
  phases: [
    { title: '팬아웃', detail: '워커당 누적 뷰 ≤30KB 빈패킹', model: 'sonnet' },
    { title: '검증', detail: 'name_check 전수 → 실패 배치 1회 재팬아웃' },
  ],
}
// args = { runDir: 절대경로, promptPath: 배치-워커-프롬프트.md 절대경로,
//          batches: [{ n: 7, path: "...batch_007.json", viewKB: 12 }...]  // pending만
//          budgetKB?: 30, retried?: false,
//          emphasis?: "재작업 강조 문안(워커 프롬프트 끝에 덧붙임 — SKILL.md 재팬아웃 절)" }
// 압축형(1-1 회차: 배치 401개 인라인 args가 40KB): batches 대신
//          viewKB: [12, 8, ...] (+ batchNums: [7, 12, ...] — 생략 시 0..N-1)
//          를 주면 경로를 `${runDir}/batches/batch_%03d.json` 템플릿으로 합성한다.
// 스크립트는 파일시스템 접근이 없다 — pending 산출·뷰크기는 호출자가 args로 넘긴다.
// 정본은 디스크(named_*.json): 이 run이 죽어도 재호출 시 호출자가 pending을 다시 계산한다.
// 스모크(2026-07-29)에서 실측: 이 하네스는 args를 파싱 안 된 JSON 문자열로 넘긴다
// (문서와 다름 — object로 보낸 args가 여기선 string으로 도착, args.batches가 undefined).
// 방어적으로 문자열이면 파싱한다.
const args_ = (typeof args === 'string') ? JSON.parse(args) : args
const BUDGET = (args_.budgetKB || 30)

// 압축 args 복원 — viewKB 배열만 받고 경로는 템플릿으로 합성
const pad3 = (n) => String(n).padStart(3, '0')
const BATCHES = args_.batches || (args_.viewKB || []).map((kb, i) => {
  const n = args_.batchNums ? args_.batchNums[i] : i
  return { n, path: `${args_.runDir}/batches/batch_${pad3(n)}.json`, viewKB: kb }
})

// 뷰예산 빈패킹 — 큰 배치부터 first-fit. 워커 1명이 받는 배치 묶음의 뷰 합 ≤ BUDGET.
// 뷰가 예산을 단독 초과하는 배치는 혼자 1워커(쪼갤 수 없다).
const sorted = [...BATCHES].sort((a, b) => (b.viewKB || 0) - (a.viewKB || 0))
const bins = []
for (const b of sorted) {
  const fit = bins.find(x => x.kb + (b.viewKB || 0) <= BUDGET)
  if (fit) { fit.kb += (b.viewKB || 0); fit.items.push(b) }
  else bins.push({ kb: (b.viewKB || 0), items: [b] })
}
log(`배치 ${BATCHES.length}개 → 워커 ${bins.length}명 (뷰예산 ${BUDGET}KB)`)

// 워커 1명이 배치 여러 개를 받으므로 반환은 **배치별 배열** — 마지막 배치만 담으면
// 생성합계가 1/N로 축소되고 앞 배치 보류 pid가 유실된다(피어리뷰 #3).
// 스모크(2026-07-29)에서 실측: tool_use 스키마의 property key는 ASCII만 허용된다
// (API 400: `^[a-zA-Z0-9_.-]{1,64}$`) — 원안의 한글 키(생성·보류_실물불명 등)는 거부됨.
// 스키마 필드는 ASCII로, 사람이 읽는 최종 반환 객체(맨 아래 return)는 한글 유지.
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
// 이 팬아웃은 세션 기본 가이드라인(동시 에이전트 ≤15)을 스킬 지시로 덮어쓴다 —
// 워커는 디스크에만 쓰고 상호 간섭이 없다. 상한은 뷰예산과 하네스 동시성 캡이 관리한다.
// 재작업(2차 팬아웃) 강조 문안 — R4 1개짜리 제출 등 1차에서 몰린 위반을 명시하면
// 실패가 크게 준다(1-1 회차 실측 104→9). 표준 문안은 SKILL.md 재팬아웃 절.
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
      model: 'sonnet', effort: 'low', schema: SCHEMA })
))

phase('검증')
const done = results.filter(Boolean)
// ###CHECK### 는 상품·배치 수치를 모두 찍는다 — passed/failed 는 **배치** 수,
// products_* 가 **상품** 수다. 상품 수로 판단하고, 배치 목록은 재팬아웃 선정에 쓴다.
const check = await agent(
  `Bash로 다음을 실행하고 출력의 ###CHECK### 줄을 요약해 반환하라(다른 출력 금지).\n` +
  `그 줄의 "상품 통과/실패/보류"는 products_* 필드에, "배치 실패"는 passed/failed에 담는다:\n` +
  `python .claude/skills/product-name/scripts/run_names.py check --run-dir "${args_.runDir}"`,
  { label: 'name_check', phase: '검증', model: 'sonnet', effort: 'low',
    schema: { type: 'object', additionalProperties: false,
              properties: { passed: { type: 'integer' }, failed: { type: 'integer' },
                            products_passed: { type: 'integer' },
                            products_failed: { type: 'integer' },
                            products_held: { type: 'integer' },
                            failed_batches: { type: 'array', items: { type: 'integer' } } },
              required: ['passed', 'failed', 'products_passed', 'products_failed',
                         'products_held', 'failed_batches'] } })

const flat = done.flatMap(r => r.results || [])
return {
  워커수: bins.length, 완료워커: done.length,
  배치결과수: flat.length,                      // < args_.batches.length 면 죽은 워커가 있다
  생성합계: flat.reduce((s, r) => s + (r.created || 0), 0),
  보류: {
    실물불명: flat.flatMap(r => r.held_unclear || []),
    카테고리의심: flat.flatMap(r => r.held_category_doubt || []),
    키워드부족: flat.flatMap(r => r.held_few_keywords || []),
  },
  검증: check,
  재팬아웃필요배치: (check && check.failed_batches) || [],
  안내: '실패 배치는 named를 지우고 이 워크플로를 pending 재계산 후 1회만 재호출(retried:true)',
}
