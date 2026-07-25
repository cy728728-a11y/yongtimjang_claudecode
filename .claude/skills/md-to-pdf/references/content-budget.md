# Content Budget Calculator

> A4 페이지 높이 추정 휴리스틱. overflow 방지를 위한 mm 단위 예산 관리.
> CSS 실측 기반. 추정을 과대하게 잡아서 여백을 낭비하지 않는다.

---

## Page Budget

| Item | Value |
|------|-------|
| A4 Height | 297mm |
| Top padding | 18mm |
| Bottom padding | 20mm |
| **Printable height** | **259mm** |
| Page header (brand + number) | 16mm (height + margin-bottom) |
| Page footer (absolute, bottom 12mm) | 0mm (doesn't consume flow) |
| **Available content height** | **243mm** |
| Safety margin | **10mm** |
| **TARGET per page** | **233mm** |

> 추정값은 CSS 실측 기반. 안전마진은 10mm이면 충분하다. 여백 낭비보다 빽빽한 페이지가 낫다.

---

## Element Height Estimates (CSS 실측 기반)

### Text Elements

| Element | Height | Notes |
|---------|--------|-------|
| `section-number` | 3mm | mono label, margin 1.5mm |
| `section-title` (h2, 1줄) | 12mm | font 17pt + margin-bottom 6mm |
| `section-title` (h2, 2줄) | 17mm | + line-height 1.2 |
| `h3` | 8mm | margin-top 5mm + text + margin-bottom 2.5mm |
| `h3:first-of-type` | 5mm | no margin-top |
| `h3` (2줄 래핑) | 11mm | 긴 한국어 제목 |
| `p` (1줄) | 6mm | 8pt × line-height 1.65 + margin-bottom 2.5mm |
| `p` (2줄) | 10mm | |
| `p` (3줄) | 14mm | |
| `p` (4줄) | 18mm | |
| `li` (1줄) | 5mm | 8pt + margin-bottom 1mm |
| `li` (2줄) | 9mm | |
| `divider` | 10mm | margin 5mm × 2 |
| `divider-sm` | 10mm | same as divider |

### Block Components

| Component | Height | Notes |
|-----------|--------|-------|
| `quote` (1줄) | 17mm | padding 4.5mm×2 + text 4mm + margin 4mm |
| `quote` (2줄) | 21mm | + 4mm per line |
| `quote` (3줄) | 25mm | |
| `quote-light` (1-2줄) | 14mm | less padding |
| `highlight-box` (title + 2줄) | 25mm | |
| `highlight-box` (title + 4줄) | 33mm | |
| `dark-inline` (small) | 22mm | padding 5mm×2 + content |
| `dark-inline` (medium) | 35mm | |
| `steps` (4-5 items) | 35mm | |
| `steps` (7+ items) | 48mm | |

### Grid & Table Components

| Component | Height | Notes |
|-----------|--------|-------|
| `card-grid` (2 cards, short) | 30mm | |
| `card-grid` (2 cards, medium) | 42mm | |
| `card-grid-3` (3 cards) | 38mm | |
| `two-col` | 35mm | |
| `table` (header + 3 rows) | 22mm | |
| `table` (header + 5 rows, 2열) | 33mm | |
| `table` (header + 5 rows, 3열) | 40mm | 셀 래핑 |
| `table` (header + 7 rows) | 42mm | |

### List Components

| Component | Height | Notes |
|-----------|--------|-------|
| `flow` (ol, 4 items) | 24mm | |
| `flow` (ol, 6 items) | 34mm | |
| `principles` (4 items) | 26mm | |
| `principles` (6 items) | 38mm | |
| `ul` (4 items, 1줄) | 22mm | |
| `ul` (4 items, 2줄) | 38mm | |
| `ul` (5 items, 2줄) | 47mm | |
| `ul` (6 items) | 32mm | |

### Special Pages

| Component | Height | Notes |
|-----------|--------|-------|
| Cover page | FULL PAGE | 297mm, standalone |
| Closing page | FULL PAGE | 297mm, standalone |
| Page header | 16mm | brand + page number + border + margin |

---

## 페이지 배치 규칙 — 구조 우선, 높이 검증

> 높이 추정값은 위 테이블 참조. 이 섹션은 **배치 방법**을 정의한다.

### Phase A — 논리 그룹 식별

마크다운의 `---`와 `##` 경계를 기준으로 분리 불가능한 논리 그룹을 먼저 식별한다.

**그룹 유형:**
- **섹션 헤더 그룹**: section-number + section-title — 반드시 다음 콘텐츠와 함께
- **참여자 블록**: h3 + Before/After + quote(s) — 절대 분할 불가
- **테이블 그룹**: 직전 제목/설명 + 테이블
- **인용 그룹**: 연속된 blockquote들
- **설명 그룹**: h3 + p (방법론 항목 등)

각 그룹의 예상 높이를 위 테이블 기준으로 산출한다.

**그룹 간 시각적 분리 규칙**:
- 그룹 사이에는 **반드시 `.divider`를 삽입**한다. 원본 MD에 `---`가 있든 없든, 그룹 경계 = divider.
- 예외: 섹션 헤더 그룹 바로 앞에는 divider 대신 margin-top으로 대체 가능. 단 시각적 분리 필수.
- divider 높이 예산: **10mm**

### Phase B — 그룹을 페이지에 배치

1. 현재 페이지 누적 + 다음 그룹 ≤ **233mm** → 같은 페이지
2. 초과 → 새 페이지 시작
3. 섹션 헤더 그룹은 반드시 최소 1개 콘텐츠 그룹과 같은 페이지
4. **그룹 내부는 절대 분할하지 않는다**
5. **빽빽하게 채우는 것이 기본**. 여백이 많으면 페이지를 줄일 수 있는지 먼저 확인

### Phase C — 높이 검증 (guardrail)

- **≤ 233mm**: OK
- **233-240mm**: divider margin 축소 등 미세 조정
- **> 240mm**: 마지막 그룹을 다음 페이지로 이동

### 그룹 패턴 레퍼런스

| 그룹 패턴 | 예상 높이 |
|-----------|----------|
| 섹션 헤더 + overview table(5행) | ~48mm |
| 참여자 블록 (h3 + Before 2줄 + After 3줄 + quote 1개) | ~52mm |
| 참여자 블록 (h3 + Before 2줄 + After 3줄 + quote 2개) | ~73mm |
| 참여자 블록 (h3 + Before 2줄 + After 4줄 + quote 3개) | ~95mm |
| 참여자 블록 (h3 + Before + After, no quote) | ~32mm |
| 설명 그룹 (h3 + p 2-3줄) | ~20mm |
| 테이블 그룹 (section header + table 5행) | ~48mm |
| 인용 그룹 (quote 3개) | ~57mm |
| divider (그룹 사이) | ~10mm |

---

## Overflow Prevention Checklist

- [ ] Phase A에서 논리 그룹을 먼저 식별했는가
- [ ] 그룹 내부가 분할되지 않았는가
- [ ] 섹션 헤더가 단독으로 페이지 끝에 남지 않았는가
- [ ] 각 페이지 예상 높이가 233mm 이하인가
- [ ] 233mm 초과 시 마지막 그룹을 다음 페이지로 이동했는가
- [ ] Cover/Closing은 항상 독립 전체 페이지인가
- [ ] **빽빽하게 채우되 잘리지만 않으면 된다**
