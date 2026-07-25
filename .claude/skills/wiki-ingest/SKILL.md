---
name: wiki-ingest
description: |
  소스를 분석하여 30-knowledge/00-wiki 토픽 페이지를 자동 enrichment. 지식을 복리로 축적.
  단순 추가가 아니라: 기존 페이지 통합, 핵심 요약 갱신, 교차 참조 강화, 모순 감지.
  "wiki-ingest", "위키 업데이트", "위키에 반영", "wiki update", "지식 축적" 등을 언급하면 자동 실행.
allowed-tools:
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - Bash
  - WebFetch
  - AskUserQuestion
---

# Wiki Ingest

소스를 분석하여 `./30-knowledge/00-wiki/` 토픽 페이지에 지식을 **복리로 축적**.

**복리 = 단순 축적이 아닌 통합.** 새 소스가 들어오면:
- 기존 페이지의 근거가 두꺼워지고
- 핵심 요약이 더 정교해지고
- 페이지 간 교차 참조가 강화되고
- 모순이 감지되어 플래그됨

> "The knowledge is compiled once and then kept current, not re-derived on every query." — Karpathy

## 동작 방식

```
WIKI_PATH = ./30-knowledge/00-wiki
```

### Input 확인

- **파일 경로**: `Read`
- **URL**: `WebFetch` (사용 가능한 경우)
- **"이 세션"**: 현재 대화 맥락에서 파악

### Step 1: 소스 분석 및 핵심 추출

소스에서 추출:
- **주요 토픽** (1~5개): 이 소스가 다루는 핵심 주제
- **핵심 인사이트**: 축적할 가치가 있는 발견/패턴/원칙
- **구체적 사례/인용**: 인사이트를 뒷받침하는 증거
- **새로운 연결**: 기존에 별개로 보이던 개념 간 관계

**축적 가치 판단:**
- 다른 맥락에서 재사용 가능한가?
- 기존 지식에 새 근거/반례를 추가하는가?
- 반복적으로 나타나는 패턴인가?

가치 없으면 조용히 종료.

### Step 2: 기존 토픽 전수 검색

1. `$WIKI_PATH/index.md` 읽어서 전체 토픽 목록 파악
2. 추출한 토픽 키워드로 `$WIKI_PATH/*.md` Grep
3. 하나의 소스가 **여러 토픽에 관련**될 수 있음 — 모두 찾기

### Step 3: 통합 (Integration) — 핵심 단계

**각 관련 토픽 페이지에 대해:**

#### 3A. 근거 추가
- 새 근거/사례를 `## 근거` 섹션에 추가
- source 인용 형식: `[요약] [source: 파일명/URL, YYYY-MM-DD]`

#### 3B. 핵심 요약 갱신
- 새 근거가 기존 `## 핵심` 섹션의 이해를 바꾸거나 정교하게 만드는지 판단
- 바뀌면 → `## 핵심` 섹션 갱신
- 안 바뀌면 → 건드리지 않음

#### 3C. 모순 감지
- 새 내용이 해당 페이지의 기존 주장과 상충하는지 확인
- 상충하면 → 해당 위치에 `[!contradiction]` 플래그 추가:
  ```
  > [!contradiction] 기존: "X가 효과적" vs 새 근거: "X는 비효과적" [source: 출처, 날짜]
  > → 검증 필요
  ```
- 모순은 삭제하지 않음. 판단은 사용자

#### 3D. 교차 참조 강화 (Related + Infobox)
- 이번 ingest로 업데이트된 **모든 토픽 페이지**의 Related 섹션 점검
- 같은 소스에서 함께 enriched된 토픽 → 서로의 Related에 추가
- **Infobox 관련 줄도 동기화**: H1 바로 아래 `> **관련**:` 줄에 최대 6개 유지
- Infobox 없는 페이지라면 SCHEMA 형식대로 생성

#### 3D-1. Facets 갱신
- 새 축/키워드가 생겼으면 `> **Facets**:` 줄에 `·` 구분으로 append
- 70자 초과 시 약한 키워드 제거

#### 3E. 적용/Open Questions 갱신
- 새 적용 사례 → `## 적용` 섹션
- 새 질문 → `## Open Questions`
- 기존 Open Question이 해결됐으면 → 답변 추가 또는 제거

#### 3F. Footer 갱신
- `Last enriched` 날짜 갱신
- Sources 목록에 새 소스 추가

### Step 4: 새 토픽 생성 (매칭 안 될 때만)

기존 토픽과 매칭이 안 되는 내용에만 새 파일:

```markdown
# [토픽명]

> **관련**: [[관련-토픽-1]] · [[관련-토픽-2]]
> **Facets**: 축1 · 축2 · 축3

## 핵심
[소스에서 추출한 핵심 요약]

## 근거
- [구체적 내용] [source: 소스명, 날짜]

## 적용
(향후 추가)

## Open Questions
(향후 추가)

## Related
[[관련-토픽-1]]

---
Sources: [소스명]
Last enriched: [오늘 날짜]
```

**Infobox 2줄 필수**. Facets가 index의 한 줄 설명으로 문장화되면 Facets 줄 생략 가능.

파일명: 케밥케이스 (한글 또는 영어).

### Step 5: index.md 갱신

- 새 토픽이면 적절한 카테고리에 추가 (3개 이상 모이면 새 카테고리)
- 페이지 유형: concept / entity / synthesis
- **한 줄 설명은 완전한 문장 1개, 70자 이내**. 키워드 덤프 금지
- 메타데이터 갱신: sources 수, enriched 날짜
- 허브 블록 재계산 (indegree 변동 시)

### Step 6: log.md 기록

`$WIKI_PATH/log.md`에 append:

```markdown
## [YYYY-MM-DD] ingest | [소스명]
- source: [소스 경로 또는 URL]
- [created/enriched]: [[토픽명]] ([한 줄 요약])
- cross-refs: [[A]] ↔ [[B]] (새 연결)
- contradictions: [[토픽명]] (있을 때만)
```

### Step 7: 결과 보고

```
Wiki Ingest 완료:
- enriched: [[토픽A]] ← [한 줄 요약]
- created: [[토픽B]] (새 토픽, 있을 때만)
- cross-refs: [[A]] ↔ [[B]]
- contradictions: 없음 (또는 내용)
```

## Query 환류

대화 중 가치 있는 분석/비교/발견이 나오면 위키에 환류:

1. 비교 분석, 의사결정 근거, 새 연결 → synthesis 페이지로 저장
2. 기존 토픽에 enrichment 우선
3. log.md에 `## [YYYY-MM-DD] query | [질문 요약]` 기록

## Supervised vs Batch 모드

- **Supervised (기본)**: 한 소스씩 처리. 핵심 포인트 논의 후 반영
- **Batch**: 여러 소스 일괄 처리. 감독 최소화

## 핵심 원칙

- **통합이 축적보다 우선**: 근거 추가 → 핵심 갱신 → 교차 참조 → 모순 감지
- **기존 페이지 확장 우선**: 비슷한 토픽 있으면 새 파일 만들지 않음
- **source 인용 필수**: 모든 추가에 출처와 날짜
- **모순은 삭제하지 않음**: 플래그만. 판단은 사용자
- **과잉 추가 금지**: 양보다 질
