# 무아레(MOIRE) Design Guide

> 단일 출처 비주얼 아이덴티티. PDF 보고서·HTML 대시보드·랜딩·슬라이드 어떤 산출물이든
> 이 파일을 참조하면 무아레 톤이 즉시 적용된다.
> 무아레는 데모용 가상 홈·리빙 라이프스타일 브랜드(자사몰 카페24 기반)다.
> 아래 톤은 "따뜻한 오트 캔버스 + 결이 있는 텍스처 + 절제된 클레이 포인트"라는
> 홈·리빙 브랜드의 전형적 무드를 토큰으로 고정한 것 (Known Gaps 참조).

## Overview

무아레의 비주얼은 **따뜻한 리빙 매거진**이다. 브랜드명 무아레(moiré)는 실크에 이는 잔잔한 물결무늬 — "결"에서 왔다. 그래서 화면은 매끈한 광택이 아니라 **손에 닿는 질감**으로 말한다. 캔버스는 햇빛 머금은 오트/샌드 톤(`{colors.canvas}`)이고, 그 위에 **웜 잉크**(`{colors.ink}`)의 차분한 타이포와 리빙 오브제 사진이 매거진 지면처럼 얹힌다. 미니멀하되 차갑지 않다 — 집 안의 온기가 배어 있는 절제다.

브랜드 보이스는 "**결이 있는 하루**"에 압축돼 있다. 요란한 세일 문구가 아니라, 일상의 한 장면을 정돈해 보여주는 큐레이터의 말투다. 그래서 산출물도 **광고 전단의 소란이 아니라, 잘 편집된 리빙 화보의 차분함**으로 말한다. voltage(시각적 긴장)는 채도가 아니라 **넓은 여백 위에 놓인 한 장의 질감 사진, 그리고 한 번씩 등장하는 클레이 포인트**의 따뜻한 대비에서 나온다.

산출물에 적용할 때 핵심은 **웜 뉴트럴 베이스 + 절제된 포인트 한 색**이다. 색을 많이 쓰지 말고, 위계는 **잉크 농도 단계 + 부드러운 헤어라인 + 여백**으로 만들되, 강조가 꼭 필요한 한 곳에만 **클레이**(`{colors.clay}`)를 점처럼 얹는다. 데이터 보고서라면 오브제 사진 자리에 **큰 KPI 숫자**가 들어가고, 그 숫자의 방향(호전/악화)만 클레이·세이지로 물들인다.

**Key Characteristics:**
- 캔버스는 웜 오트/샌드(`{colors.canvas}`) — 햇빛 든 리빙룸. 다크 모드는 이 브랜드의 기본 톤이 아니다.
- **포인트 색은 클레이 하나로 절제.** 클레이(`{colors.clay}`)는 링크·핵심 수치·작은 밴드에만 점처럼. 세이지(`{colors.sage}`)는 보조·태그·호전 신호에만.
- 타이포는 **에디토리얼 세리프 + 정제된 산세리프** 2종 운용. 제목·리드는 세리프(리빙 매거진), 본문·UI·숫자는 산세리프.
- 위계는 채도가 아니라 **잉크 농도 + 헤어라인 + 여백**으로. 강조는 클레이 점 하나로.
- 여백을 넉넉하게 — 섹션 간 `{spacing.section}`, 카드 둘레 `{spacing.xl}`. 빽빽함은 매거진 톤이 아니다.
- 모서리는 **부드러운 라운드**(`{rounded.md}`)가 카드 기본 — 물결(무아레)의 유함. 단, 표·이미지 프레임은 `{rounded.sm}`로 절제.
- 그림자는 **아주 옅은 웜 소프트 섀도**까지 허용 — 집의 온기. 단 뚜렷한 드롭섀도는 금지.
- KPI 숫자는 크고 또렷하게, 웜 잉크로 — 방향(호전/악화)만 클레이·세이지로.

## Colors

### Brand & Accent
- **Ink** (`{colors.ink}` — #241F1A): 로고·헤드라인·핵심 텍스트. 순흑보다 따뜻한 웜 잉크 브라운블랙.
- **Clay** (`{colors.clay}` — #B0654A): 시그니처 포인트. 머트 테라코타/클레이. 링크·핵심 수치 강조·작은 밴드·CTA에만 점처럼.
- **Clay Soft** (`{colors.clay-soft}` — #E7CDBF): 클레이의 옅은 배경 틴트. 강조 셀·칩 배경.
- **Sage** (`{colors.sage}` — #7C8666): 보조 자연 톤. 태그·호전 신호·서브 라벨. 클레이와 나란히 쓰되 면적 최소.

### Surface
- **Canvas** (`{colors.canvas}` — #F4F0E8): 기본 페이지 바닥. 웜 오트/샌드.
- **Surface Soft** (`{colors.surface-soft}` — #EDE7DB): 표 헤더·푸터 인접 스트립용 한 톤 낮은 면.
- **Surface Card** (`{colors.surface-card}` — #FBF9F4): 카드·오브제 매트. 캔버스보다 살짝 밝게 띄워 면 분리.
- **Ink Panel** (`{colors.ink-panel}` — #241F1A): 반전 강조 밴드(표지·핵심 인용). 위에 캔버스색 텍스트.

### Hairlines & Borders
- **Line** (`{colors.line}` — #DED6C7): 기본 1px 구분선·표 행·카드 외곽.
- **Line Strong** (`{colors.line-strong}` — #C8BCA6): 강조 구분선·표 헤더 하단·섹션 구획.

### Text
- **On Canvas** (`{colors.on-canvas}` — #241F1A): 캔버스 위 기본 텍스트 = Ink.
- **Body** (`{colors.body}` — #4A433B): 본문 러닝 텍스트.
- **Muted** (`{colors.muted}` — #8A8073): 캡션·메타·라벨·푸터.
- **On Ink** (`{colors.on-ink}` — #F4F0E8): 잉크 패널(반전) 위 텍스트 = 캔버스색.

### Semantic (절제 — 웜 톤 안에서)
- **Positive** (`{colors.positive}` — #5E7A54): 마진 양호·평점 호전·목표 달성. 세이지 계열 딥 그린, 면적 최소.
- **Negative** (`{colors.negative}` — #A5453A): 마진 누수·부정 리뷰 급증·재고 위험. 클레이 계열 딥 브릭, 수치 강조에만.
- **Warning** (`{colors.warning}` — #B08733): 수수료 과다·저효율 주의. 웜 머스터드, 셀 강조에만.
- 세 색은 **데이터 보고서 신호 전용**. 브랜드 표면(랜딩·표지)에는 시그니처 클레이/세이지만.

## Typography

### Font Family
세리프(매거진 제목) + 산세리프(본문·데이터) 2종 운용. 공식 서체 미지정이므로 시스템/오픈소스 대체 스택을 쓴다.
- 제목/리드(세리프): `"Nanum Myeongjo", "Noto Serif KR", "Apple SD Gothic Neo", serif` — 리빙 매거진 톤.
- 본문/UI(산세리프): `"Pretendard", "Noto Sans KR", -apple-system, "Segoe UI", sans-serif` — 가독·정밀.
- 숫자(KPI): 산세리프 스택 + `font-variant-numeric: tabular-nums` — 표·대시보드 정렬.

### Hierarchy
| 토큰 | 용도 | 크기/두께(데스크톱) |
|------|------|---------------------|
| `{typography.display-xl}` | 표지·히어로 타이틀 (세리프) | 44–54px / 400 |
| `{typography.display-lg}` | 섹션 대제목 (세리프) | 28px / 400 |
| `{typography.heading}` | 소제목 (산세리프) | 19px / 600 |
| `{typography.label-uppercase}` | 라벨·카테고리 (산세리프) | 11px / 600 / letter-spacing 0.12em / muted |
| `{typography.body-lg}` | 리드 문단 | 17px / 400 |
| `{typography.body-md}` | 기본 본문 | 15px / 400 |
| `{typography.caption}` | 캡션·메타 | 12px / 400 muted |
| `{typography.number}` | KPI 수치 | 32–42px / 600, tabular-nums, Ink |

### Principles
- **세리프는 제목·리드에만**, 본문·데이터는 산세리프. 두 종의 역할을 섞지 않는다.
- 라벨은 작게·자간 넓게(`{typography.label-uppercase}`) 매거진 캡션처럼, muted 색으로.
- 숫자(KPI)는 크게·tabular-nums, 기본은 잉크 — 방향(호전/악화)만 클레이·세이지로 물들인다.

### Note on Font Substitutes
무아레는 가상 브랜드로 지정 서체가 없다. 위 스택은 "웜 리빙 매거진(세리프 제목 + 산세리프 본문)" 무드를 시스템/오픈소스 폰트로 근사한 것.

## Layout

### Spacing System
- `{spacing.section}` — 72px (섹션 간 — 매거진 여백)
- `{spacing.xxl}` — 48px (표지 둘레 매트)
- `{spacing.xl}` — 32px (카드 내부·카드 사이)
- `{spacing.lg}` — 24px
- `{spacing.md}` — 16px
- `{spacing.sm}` — 8px

### Grid & Container
- 최대 콘텐츠 폭 1040–1160px, 중앙 정렬. 좌우 여백을 넉넉히 남겨 매거진 매트 효과.
- 오브제/이미지 그리드는 2–3열, 카드 사이 간격 `{spacing.xl}` 이상.

### Whitespace Philosophy
여백이 곧 톤이다. 채우려 하지 말고, 오트 지면 위에 오브제(또는 숫자) 하나가 숨 쉬게. 빽빽함이 보이면 요소가 아니라 여백을 늘린다.

## Elevation & Depth

| Level | 용도 | 처리 |
|-------|------|------|
| 0 | 캔버스 | 그림자 없음 |
| 1 | 카드/오브제 매트 | `{colors.surface-card}` 면 + 1px 라인(`{colors.line}`) + 아주 옅은 웜 소프트 섀도(0 2px 8px rgba(60,45,30,.05)) |
| 2 | 강조 밴드 | `{colors.ink-panel}` 반전 면 또는 `{colors.clay-soft}` 클레이 틴트 면 |

### Decorative Depth
깊이는 **잉크 농도 + 헤어라인 + 여백**이 1순위, 거기에 **아주 옅은 웜 소프트 섀도**로 집의 온기를 더한다. 뚜렷한 드롭섀도·강한 그라데이션은 금지 — 은은한 한 겹까지만.

## Shapes

### Border Radius Scale
| 토큰 | 값 | 용도 |
|------|----|----|
| `{rounded.none}` | 0px | 풀블리드 밴드·구분선 |
| `{rounded.sm}` | 6px | 표·이미지 프레임·버튼·칩 |
| `{rounded.md}` | 12px | 카드·KPI 타일 기본 — 물결(무아레)의 유함 |
| `{rounded.lg}` | 20px | 히어로 이미지·큰 패널 |
| `{rounded.full}` | 9999px | 상태 점·태그 칩·아이콘 버튼 |

### Photography Geometry
오브제·제품 이미지는 **웜 여백 안 라운드 프레임**(`{rounded.md}`). 라이프스타일 컷은 여백 두고 배치, 디테일 컷은 근접. 테두리는 없거나 `{colors.line}` 1px. 데이터 차트도 같은 원칙: 라운드 sm, 웜 그레이 스케일 + 신호색(클레이/세이지) 최소.

## Components

### Top Navigation
웜 오트 캔버스 위 잉크 텍스트. 로고 좌측(잉크 워드마크), 메뉴 우측. 하단 1px 라인(`{colors.line}`). 스크롤 시 surface-soft로 한 톤. 활성 메뉴만 클레이 언더라인.

### Buttons
- **Primary** (`{component.button-primary}`): 클레이 면(`{colors.clay}`) + 캔버스색 텍스트, `{rounded.sm}`. 호버 시 한 단계 딥.
- **Secondary**: 투명 배경 + 1px 라인 테두리 + 잉크 텍스트, `{rounded.sm}`. 호버 시 surface-soft.
- **Ghost**: 텍스트만, 클레이 밑줄 호버.

### Cards & Containers
`{colors.surface-card}` 배경 + `{colors.line}` 1px 테두리 + `{rounded.md}` + Level 1 소프트 섀도. KPI 카드는 큰 숫자(`{typography.number}`, 잉크) + 아래 해석 한 줄(muted). 방향 신호는 숫자 옆 작은 클레이/세이지 화살표·칩으로.

### Inputs & Forms
canvas 배경 + 라인 테두리 + `{rounded.sm}`. 포커스 시 클레이 테두리. 잉크 텍스트.

### Signature Components
- **Texture Band** (`{component.texture-band}`): 오브제/이미지/KPI를 웜 여백 안 라운드 프레임으로 놓는 시그니처. 무아레의 얼굴 — "결이 있는 지면 위 한 점".
- **KPI Row** (`{component.kpi-row}`): 캔버스 위 3–4 KPI를 라인+소프트 섀도 카드로 가로 배열. 큰 잉크 숫자 + muted uppercase 라벨 + 해석 한 줄. 방향만 클레이(악화)/세이지(호전) 칩으로.
- **Clay Band** (`{component.clay-band}`): `{colors.clay-soft}` 틴트 밴드 — 핵심 인사이트·경보(부정 리뷰 급증 등) 한 줄에. 강한 반전이 필요하면 Ink Band.
- **Ink Band** (`{component.ink-band}`): `{colors.ink-panel}` 반전 밴드 — 표지·슬로건("결이 있는 하루")에. 위에 캔버스색 세리프.

### Footer
`{colors.surface-soft}` 배경 + 잉크 워드마크 + 자사몰 주소(moire.co.kr)·연락처 + 상단 1px 라인. muted 텍스트. @moire.official.

## Do's and Don'ts

### Do
- 캔버스는 웜 오트/샌드로 — 햇빛 든 리빙룸.
- 포인트는 클레이 하나로 절제 — 링크·핵심 수치·작은 밴드에만.
- 위계는 잉크 농도 + 헤어라인 + 여백으로.
- 제목·리드는 세리프, 본문·숫자는 산세리프로 역할 분리.
- KPI 숫자는 크게·잉크로, 방향만 클레이(악화)/세이지(호전).
- 카드는 부드러운 라운드(`{rounded.md}`) + 아주 옅은 소프트 섀도로 온기.

### Don't
- 다크 배경을 기본으로 쓰지 않기 — 웜 오트가 무아레.
- **포인트 색을 여러 개 만들지 않기** — 클레이 + (보조)세이지 + 신호색만.
- 뚜렷한 드롭섀도·강한 그라데이션 쓰지 않기 — 은은한 한 겹까지만.
- 직각(`{rounded.none}`)으로 카드를 각지게 만들지 않기 — 무아레는 물결의 유함.
- 요소를 빽빽이 채우지 않기 — 여백이 톤.
- 세리프를 본문 전체에 쓰지 않기 — 제목·리드 전용.

## Responsive Behavior

### Breakpoints
| 이름 | 폭 |
|------|----|
| Mobile | < 640px |
| Tablet | 640–1024px |
| Desktop | > 1024px |

### Touch Targets
버튼·링크 최소 44×44px.

### Collapsing Strategy
KPI 3–4열 → 모바일 1–2열. 표는 가로 스크롤 또는 카드형 전환. 오브제 그리드 3열 → 모바일 1열(웜 여백 유지).

### Image Behavior
오브제·차트는 비율 유지, 웜 여백 두고 축소. 모바일에서도 여백을 지나치게 줄이지 않는다(매거진 톤 유지).

## Iteration Guide
1. 새 산출물은 캔버스(웜 오트) + 잉크 본문에서 시작.
2. 강조가 필요하면 채도가 아니라 크기·굵기·여백으로 먼저 풀고, 그래도 필요하면 클레이 점 하나.
3. 구획은 1px 라인 또는 클레이 틴트/잉크 밴드.
4. 표지·슬로건엔 Ink Band(반전), 인사이트·경보엔 Clay Band(틴트).
5. 숫자(KPI)는 크게·tabular-nums·잉크. 방향만 클레이/세이지.
6. 깊이는 헤어라인 + 여백 + 아주 옅은 소프트 섀도.
7. 이미지·오브제·카드는 웜 여백 안 라운드 프레임으로.
8. 포인트 색을 하나 더 추가하고 싶으면 멈추고 여백·무게·크기로 먼저 해결한다 — 색은 클레이 하나면 충분.

## Known Gaps
- **가상 브랜드**: 무아레는 AX 데모용 가공 브랜드다. 실제 브랜드 가이드라인이 아니라, "웜 리빙 매거진 미니멀"이라는 홈·리빙 카테고리 전형 무드를 토큰으로 고정한 것.
- **정확한 Hex는 무드 근사값**: 위 오트/잉크/클레이/세이지 값은 카테고리 전형에서 도출한 근사값. 실제 클라이언트 브랜드에 적용할 땐 자사몰 CSS(F12)·로고·인스타에서 확인된 실제 시그니처 컬러로 교체.
- **공식 서체명 없음**: 시스템/오픈소스 대체 스택(Nanum Myeongjo / Pretendard) 사용.
- 모션/인터랙션 가이드 미스코프(정적 산출물 우선).
