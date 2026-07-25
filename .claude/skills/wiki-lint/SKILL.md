---
name: wiki-lint
description: |
  00-wiki 토픽 페이지 헬스체크. 모순, 고아 페이지, 오래된 정보, 누락된 교차 참조 점검.
  "wiki-lint", "위키 점검", "위키 헬스체크", "wiki health", "토픽 점검" 등을 언급하면 자동 실행.
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash
  - Edit
  - AskUserQuestion
---

# Wiki Lint

`./30-knowledge/00-wiki/` 토픽 페이지의 헬스체크.

## 동작 방식

### Step 1: 전체 토픽 페이지 수집

```
WIKI_PATH = ./30-knowledge/00-wiki
```

- Glob: `$WIKI_PATH/*.md` (SCHEMA.md, README.md, index.md, log.md 제외)
- 각 파일의 제목, Related 섹션, Last enriched 날짜 수집

### Step 2: 점검 실행 (A~M)

#### A. 고아 페이지 (Orphan Pages)
- index.md에 등재되지 않은 토픽 페이지
- 다른 토픽의 Related에서 한 번도 참조되지 않는 페이지
- **조치**: index.md에 추가 제안

#### B. 죽은 링크 (Dead Links)
- Related 섹션에서 참조하는 `[[토픽]]`이 실제 파일로 없음
- **조치**: 링크 제거 또는 새 토픽 생성 제안

#### C. 오래된 페이지 (Stale Pages)
- Last enriched가 90일 이상 경과
- **조치**: "이 토픽은 여전히 유효한가?" 플래그

#### D. 모순 탐지 (Contradictions)
- 서로 다른 토픽 페이지에서 동일 주제에 대해 상충하는 주장
- Grep으로 공통 키워드 가진 페이지 쌍을 찾고 내용 비교
- **조치**: `[!contradiction]` 플래그 + 최신 여부 표시

#### E. 누락된 교차 참조 (Missing Cross-References)
- 본문에서 다른 토픽명이 언급되지만 Related에 링크 없음
- **조치**: Related에 추가 제안

#### F. 누락된 토픽 (Missing Pages)
- 여러 페이지에서 참조되지만 전용 페이지 없음
- **조치**: 새 토픽 페이지 생성 제안

#### G. 비대한 페이지 (Oversized Pages)
- 특정 섹션이 전체의 50% 이상 또는 하위 항목 10개 이상
- **조치**: 독립 토픽으로 분리 제안

#### H. 데이터 갭 (Data Gaps)
- 주장은 있지만 source 인용 없음
- 반복 언급되지만 자체 근거 부족한 개념
- **조치**: 웹 검색으로 보강 가능한 갭 식별 → 리서치 제안

#### I. 활동 분석 (log.md 기반)
- 한 번도 enriched 안 된 시드 페이지
- 최근 30일간 ingest 없는 카테고리
- **조치**: ingest 필요성 제안

#### J. Infobox 누락/훼손
- H1 바로 아래 `> **관련**:` 줄 없음
- 관련 링크 6개 초과 (덤프)
- Infobox wikilink가 실제 파일로 없음
- **조치**: 누락 시 `## Related`에서 상위 6개 추출, 초과 시 indegree 약한 것 제거

#### K. index 한 줄 설명 품질
- 키워드 콤마 덤프 탐지 (쉼표 3개+ 또는 토큰 8개+)
- 70자 초과
- 문장이 아닌 명사구
- **조치**: `## 핵심` 첫 문장 기반 재작성 제안

#### L. Facets 비대/중복
- Infobox Facets 70자 초과
- Facets 키워드가 `## 근거`에서 더 이상 언급 안 됨
- **조치**: 약한 키워드 제거 제안

#### M. 허브 블록 표류
- index.md 상단 `> **허브 토픽**` 5개가 실제 indegree 상위 5개와 불일치
- indegree = 각 페이지 Infobox 관련 줄에 자기 토픽이 등장하는 횟수
- **조치**: 상위 5개로 재정렬 제안

### Step 3: 헬스 리포트

```markdown
# Wiki Health Report — YYYY-MM-DD

## 요약
- 총 토픽: N개
- 건강: X개 | 주의: Y개 | 조치 필요: Z개

## 상세

### 고아 페이지 (N개)
| 페이지 | 상태 | 제안 |
|--------|------|------|

### 죽은 링크 (N개)
...

(등)
```

### Step 4: 사용자 승인 후 수정

- AskUserQuestion으로 수정할 항목 확인
- 승인된 항목만 Edit (index.md, Related 등)
- 수정 내용 log.md에 기록:
  ```
  ## [YYYY-MM-DD] lint | Wiki Health Check
  - 고아 페이지 N개 → index.md에 추가
  - 누락된 교차 참조 N개 → Related에 추가
  ```

## 핵심 원칙

- **리포트 먼저, 수정은 승인 후**: 자동으로 고치지 않음
- **모순은 플래그만**: 판단은 사용자
- **과잉 제안 금지**: 확실한 문제만 리포트
