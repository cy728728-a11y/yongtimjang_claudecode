---
name: md-to-pdf
description: 마크다운 문서를 A4 PDF-ready HTML 핸드아웃으로 변환. Monochrome Dark 테마(미니멀 블랙/화이트, 브랜드 중립). 페이지 overflow 자동 방지. "핸드아웃", "handout", "PDF 만들어", "배포용", "md-to-pdf", "인쇄용", "A4 변환" 등을 언급하면 자동 실행.
allowed-tools:
  - Read
  - Write
  - Glob
  - Grep
---

# MD to PDF Handout Generator

> 마크다운 문서를 A4 PDF-ready HTML 핸드아웃으로 변환하는 스킬.
> 페이지 overflow 방지 + 모노크롬 테마 적용 + 컴포넌트 매핑을 자동으로 수행.
> 브라우저에서 열고 Cmd+P → PDF로 저장하면 완료.

---

## Workflow (6 Steps)

### Step 1: Read Source

1. 사용자가 지정한 마크다운 파일을 Read (`$ARGUMENTS` 또는 `@file` 참조)
2. 파일이 지정되지 않았으면 경로 요청
3. 파일이 있는 디렉토리를 출력 위치로 기억 (같은 디렉토리에 저장)

### Step 2: Analyze Structure

마크다운을 파싱하여 식별:
- **문서 메타데이터**: title, date, author, event 이름
- **섹션 계층**: h2 = major 섹션, h3 = subsection
- **콘텐츠 유형**: paragraph, list, quote (blockquote), table, code block
- **예상 분량**: 총 페이지 수 추정

### Step 3: 테마 적용

**기본값 (그리고 유일한 내장 테마)**: Monochrome Dark
→ [references/monochrome-theme.md](references/monochrome-theme.md) 참조

미니멀 블랙/화이트, Pretendard + Helvetica Neue 폰트 스택. 브랜드 중립이라 어떤 문서(강의록·회고·리포트·튜토리얼)에도 무난.

**커스텀 CSS 오버라이드**: 사용자가 `@styleguide.md` 같은 자체 스타일 가이드를 제공하면 그 CSS를 사용. 이 경우에도 본 스킬의 페이지 레이아웃 룰(A4, overflow 방지)은 유지.

### Step 4: Plan Pages (Content Budget)

구조 우선, 높이 검증. 높이 추정은 [references/content-budget.md](references/content-budget.md) 참조.

**Phase A — 논리 그룹 식별**

`---`와 `##` 경계를 기준으로 **분리 불가능한 논리 그룹**을 식별한다. 각 그룹의 예상 높이를 content-budget.md 기준으로 산출.

그룹 식별 규칙:
- **섹션 헤더 그룹**: `##` section-number + section-title — 반드시 바로 다음 콘텐츠 블록과 한 그룹
- **참여자/항목 블록**: `###` h3 + 본문 paragraphs + quote(s) — 다음 `---` 또는 다음 `###`까지가 한 그룹, 분할 불가
- **테이블 그룹**: 제목/설명 + 테이블 — 테이블만 단독으로 다음 페이지에 가면 맥락 없음, 직전 제목과 한 그룹
- **인용 그룹**: 연속된 blockquote들은 한 그룹
- **설명 그룹**: h3 + p (방법론 항목 등)

`---` (divider)는 그룹 간 **분리 가능 지점**.

**그룹 간 시각적 분리 규칙 (HTML 생성 시)**:
- 그룹 사이에 **반드시 `.divider` 삽입**. 원본 MD에 `---`가 있든 없든 그룹 경계 = divider
- 예외: 같은 페이지에서 섹션 헤더 그룹 바로 앞에는 divider 대신 **margin-top 6mm** 여백
- divider 높이 예산: **10mm** (margin 5mm + line + margin 5mm)

**Phase B — 그룹을 페이지에 배치**

1. 현재 페이지 누적 높이 + 다음 그룹 높이 ≤ **233mm** → 같은 페이지
2. 초과 → 새 페이지 시작
3. 섹션 헤더 그룹이 페이지 끝에 단독 금지 — 반드시 콘텐츠 그룹 최소 1개와 함께
4. **그룹 내부는 절대 분할 금지**
5. **빽빽하게 채우는 것이 기본**. 여백이 많으면 페이지를 줄일 수 있는지 먼저 검토

**Phase C — 높이 검증 (guardrail)**

- **≤ 233mm**: OK
- **233-240mm**: divider margin 축소(10→5mm) 등 미세 조정
- **> 240mm**: 마지막 그룹을 다음 페이지로 이동

**Page plan 예시** (internal, 사용자에게 보여주지 않음):
```
Groups: [G1: Overview(90mm)] [G2: P1(55mm)] [G3: P2(50mm)] ...
Page 1: G1 + G2 + G3 = ~195mm  ✓
Page 2: G4 + G5 = ~180mm  ✓
```

### Step 5: Generate HTML

1. 완전한 `<!DOCTYPE html>` 문서 작성
2. `<head>`에 Pretendard 폰트 CDN 로드
3. `<style>` 블록에 **monochrome 테마 CSS 전체를 인라인**으로 포함 (외부 CSS 파일 사용 X)
4. Cover page에 메타데이터 배치
5. 페이지 플랜 따라 content page 생성
6. 마지막 closing page 생성
7. 페이지 번호: `{NN} / {TOTAL}` (cover/closing 제외, content page만 카운트)

### Step 6: Save & Report

1. 같은 디렉토리에 `{원본이름}_handout.html` 저장
2. 사용자 리포트:
   - 총 페이지 수 (cover + content + closing)
   - 테마: Monochrome Dark (또는 custom)
   - 분량 조정이 있었으면 어떤 섹션을 축약/재배치 했는지

---

## Component Mapping (Markdown → HTML)

| Markdown | HTML Component | Class | 비고 |
|----------|---------------|-------|------|
| `# Title` | Cover title | `.cover-title` | 문서 제목 1회만 |
| `## Section` | Section title | `.section-number` + `.section-title` | 자동 번호: Section 01, 02... |
| `### Subsection` | Subheading | `h3` | Bold sans-serif |
| `#### Sub-sub` | Card/inline heading | `h4` | 카드·블록 내부 |
| Paragraph | Paragraph | `p` | 8pt body text |
| `> blockquote` | Dark quote | `.quote` | 어두운 배경 |
| `> **name**: text` | Light quote | `.quote-light` | 인용자 표시 포함 |
| `- item` (ul) | Bullet list | `ul > li` | 기본 리스트 |
| `1. item` (ol) | Numbered flow | `ol.flow > li` | 원형 번호 |
| `---` | Divider | `.divider` | 얇은 선 분리 |
| Table | Table | `table > tr > th/td` | 어두운 헤더 행 |
| `**bold key**: value` list | Principles list | `ul.principles > li` | 번호·테두리 |
| 인접 짧은 항목 (2-4개) | Card grid | `.card-grid` / `.card-grid-3` | 2개 = 2열, 3개 = 3열 |
| 단계별 지침 | Steps block | `.steps` | 어두운 배경, 번호 |
| 평행 두 리스트/내용 | Two column | `.two-col` | 나란히 |
| 중요 callout | Highlight box | `.highlight-box` | accent 테두리 |
| 강조 블록 | Dark inline | `.dark-inline` | 어두운 배경 인라인 |
| Code block | Dark inline with mono | `.dark-inline` | monospace |

### Mapping 판단 규칙

1. **발화자 속성 있는 blockquote** ("-- name" 등) → `.quote` (dark)
2. **팁/인사이트 blockquote** → `.quote-light`
3. **제목+설명 2-4개 리스트** → `.card-grid` / `.card-grid-3`
4. **5개 이상 번호·원칙 리스트** → `.principles`
5. **단계별 지침** → `.steps` (formal) 또는 `.flow` (inline)
6. **나란한 비교** → `.two-col`
7. **중요 수식/개념** → `.highlight-box`
8. **코드 예시/파일 구조** → `.dark-inline` + monospace

---

## Page Overflow Prevention Rules

1. **구조 우선**: Phase A에서 논리 그룹 먼저 식별 → Phase B에서 그룹 단위 배치
2. **그룹 내부 분할 금지**: 참여자 블록, 테이블+제목, 섹션 헤더+첫 콘텐츠는 분리 불가
3. **233mm target per page**: 사용 가능 243mm에서 10mm 안전 마진
4. **Split only between groups**: `---`가 유일한 분리 가능 지점
5. **단일 그룹이 233mm 초과**: 그룹 내 요소 축약 (divider margin 축소, 텍스트 압축)
6. **빽빽하게 채우되 잘리지만 않으면 됨**: 여백 낭비 < 컴팩트 배치

---

## Section Title Formatting (선택)

핵심 개념을 영어 한 단어로 뽑아 `<em>`으로 강조하는 스타일을 쓸 수 있다:

```html
<div class="section-number">Section 01</div>
<h2 class="section-title">AI-Friendly <em>File</em> Management</h2>
```

- 섹션 헤딩에서 핵심 개념 추출
- 영어 단어로 번역 후 `<em>`으로 감싸기
- 나머지는 원문 언어 그대로 또는 자연스럽게 번역

한국어 전용 문서면 이 스타일을 쓰지 않고 일반 제목으로 둬도 됨.

---

## Validation Checklist

HTML 저장 전 확인:

- [ ] 전체 CSS가 `<style>`에 embedded (외부 파일 X)
- [ ] `<head>`에 Pretendard CDN 링크
- [ ] Cover page: title, subtitle, date, author/instructor, 문서 식별자
- [ ] 모든 content page: page-header (식별자 + 페이지 번호) + page-footer
- [ ] 페이지 번호 순차, 총합 정확
- [ ] 어떤 페이지도 233mm 초과 추정 없음
- [ ] Closing page: 문서명, 요약 메시지, 이벤트 정보
- [ ] `.page`에 `overflow: hidden`
- [ ] `.page`와 `.cover`에 `page-break-after: always`
- [ ] `body`에 `-webkit-print-color-adjust: exact` + `print-color-adjust: exact`
- [ ] `<em>`은 accent 강조용만 (일반 이탤릭 X)
- [ ] 파일명: `{원본}_handout.html`

---

## Examples

### 호출 예시

```
"이 MD 파일로 핸드아웃 만들어줘" + @file.md
"배포용 PDF 준비해줘" + @session-notes.md
"핸드아웃 만들어, 내 스타일가이드 써서" + @doc.md @my-styleguide.md
```

### Output

```
{source_dir}/{원본이름}_handout.html
```

브라우저에서 열고 Cmd+P (Mac) / Ctrl+P (Linux/Windows) → "PDF로 저장".
