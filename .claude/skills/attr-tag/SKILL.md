---
name: attr-tag
description: sold-lock 이 잠근 판매상품(new_locks.json)에 스마트스토어 속성과 공식 태그(태그사전 code 포함)를 커머스API로 넣는다. 판단(어떤 태그·속성 값)은 Claude 가 prep 재료를 보고 plan.json 으로 쓰고, 도구는 재료 수집·검증·저장·재조회 확인·되돌리기를 맡는다. "속성 태그 넣어줘", "판매상품 태그", "공식 태그 입력", "속성 입력", "attr-tag", "태그사전 태그로 바꿔줘" 등을 언급하면 자동 실행.
---

# 판매상품 속성·태그 입력 (attr-tag)

불사자로 넣은 스스 태그는 사전번호(code)가 없는 평문이라 검색에 안 걸린다. 팔린 상품부터
**태그사전에 있는 공식 태그**와 **카테고리 속성**을 채워 넣는다.

## 흐름

```
sold-lock new_locks.json ─▶ prep (판단 재료) ─▶ Claude 가 plan.json 작성 ─▶ apply (dry-run) ─▶ apply --commit
                                                                                         └─▶ revert (필요 시)
```

```bash
PY=.venv/bin/python3; S=.claude/skills/attr-tag/scripts/attr_tag.py
$PY $S prep --date 2026-10-16                                  # 그날 new_locks 전체
$PY $S prep --date 2026-10-16 --market 13-2 --channel-no 13265084103
$PY $S apply --plan <run-dir>/plan.json                        # dry-run (기본) — 쓰기 0
$PY $S apply --plan <run-dir>/plan.json --commit
$PY $S revert --market 13-2 --channel-no 13265084103 [--commit]
```

## 1. prep — 판단 재료

대상: `<data_root>/sold-lock/<날짜>/new_locks.json` 의 (마켓번호, 스스상품번호=채널상품번호). `--input` 으로 직접 지정 가능.
이미 처리된 상품(어느 날짜든 `after_<마켓>_<번호>.json` 존재)은 건너뛴다 — `--force` 로 재처리.

`prep_<마켓>_<번호>.json`: 상품명 · 카테고리ID·경로 · 옵션명 · 현재 태그(`has_code`) · 현재 속성(이름=값) ·
**입력 가능 속성**(이름·유형·주요/부가·선택지 텍스트·max_select) · 상세 텍스트(3000자) · 이미지 URL.
`todo.json` 에 판단 대기 목록이 쌓인다.

## 2. plan.json (Claude 가 쓴다)

```json
[{"market": "13-2", "channel_no": "13265084103",
  "tags": ["호텔용품", "식당용품", "보온접시"],
  "attributes": [{"name": "용도", "values": ["업소용"]}, {"name": "품목", "values": ["워머"]}],
  "keep_existing_attributes": true}]
```

- `tags` 를 빼면 태그는 안 건드린다. 검증 통과가 0개면 기존 태그를 유지한다(지우지 않음).
- `attributes` 의 name·values 는 prep 의 `available_attributes[].choices` 텍스트 **그대로** 써라. 한 글자라도 다르면 탈락.
- 판단 기준: 태그는 상품을 실제로 찾을 검색어(용도·장소·대상·형태). 상품명에 이미 있는 단어 반복보다 연관 검색어. 속성은 상세·옵션 근거가 있는 것만.

## 3. apply — 검증 규칙

| 대상 | 규칙 | 탈락 사유 |
|---|---|---|
| 태그 | `recommend-tags` 접두 자동완성에서 **text 정확일치**의 code 만 | `not_in_dictionary` |
| 태그 | `restricted-tags` 가 True 면 제외 (뷔페·보온·워머·업소용 같은 일반어도 걸린다) | `restricted` · 조회 실패 시 전부 미입력 |
| 태그 | 중복 제거 후 최대 10개 | `duplicate` · `over_limit` |
| 속성 | 카테고리 선택지에 정확히 있는 값만 seq 로 | `unknown_attribute` · `value_not_in_choices` |
| 속성 | 선택형 1개, 복수선택형은 `max_select`(0=무제한) | `over_select_limit` |
| 속성 | 범위형은 이번 버전에서 입력 안 함 | `range_type_unsupported` |
| 속성 | `keep_existing_attributes`(기본 true): plan 에 나온 attributeSeq 만 교체, 나머지(범위형 포함) 보존. false 면 통째로 교체 | |

- **dry-run(기본)**: 전/후 diff 를 출력하고 `apply_dryrun.json` 에 남긴다. 쓰기 0.
- **--commit**: 상품마다 `before_<마켓>_<번호>.json` 백업(이미 있으면 덮지 않음 = 최초 원본 보존) → 조회 응답 전체에서 태그·속성만 고친 본문으로 PUT →
  재조회로 태그 code·속성 seq 반영 확인 + 이름·판매가·재고·상세 길이·상태·카테고리·옵션 수/가격 불변 검사 → `after_…json` · `result.json` 누적.
  상태: `ok` · `unverified`(저장은 됐는데 확인 실패 — `problems` 참조) · `failed`. 한 상품 실패가 전체를 멈추지 않는다. 변경이 없으면 PUT 생략.

## 4. revert

before 백업(기본: 가장 이른 날짜)의 `seoInfo.sellerTags` · `productAttributes` 만 현재 상품에 되돌려 PUT 한다. 다른 필드는 현재값 유지.
dry-run 은 `revert_dryrun_*.json`, 실행은 `reverted_*.json` (오늘 날짜 run-dir). 확인 실패 시 종료코드 4.

## 업무판

`--commit` 끝에 workspace.toml `sheets.work_board` '오늘' 탭 1행 (sold-lock 과 같은 형식):
번호 · 실행일 · 확인(전건 ok 일 때만) · `⑥ 속성·태그 <날짜>` · ⑥ · Claude · 자동 · `상품 N · 태그 평균 t개 · 속성 a개 · 실패 f`.
시트 쓰기가 실패해도 `result.json` 은 남는다(`board.status=failed`).

## 산출물 — `<data_root>/attr-tag/<날짜>/`

| 파일 | 내용 |
|---|---|
| `prep_<마켓>_<번호>.json` · `todo.json` | 판단 재료 · 대기 목록 |
| `plan.json` | Claude 판단 결과 (여기 두면 apply 가 이 폴더 날짜를 run-dir 로 쓴다) |
| `apply_dryrun.json` | dry-run diff·탈락 사유 |
| `before_*.json` / `after_*.json` | 저장 전 원본(덮지 않음) / 저장 후 재조회 |
| `result.json` | 상품별 상태 누적 + 업무판 기록 결과 |

## 키·레이트리밋

- 키·토큰은 sold-lock `CommerceClient`(키 시트 `사업자정리` → `~/.eroom/naver-commerce-stores.json` 캐시 폴백) 재사용. 시크릿·토큰은 출력·산출물에 안 남는다(`safe_json`/`redact`).
- 커머스API GW.RATE_LIMIT — 호출 간 ≥1초, 429·5xx·`RATE_LIMIT` 응답은 지수백오프(최대 5회).
- 카테고리 속성 표·태그 사전 조회는 실행 1회 안에서 캐시.

## 범위 밖

- 태그 후보(마누태그) 수집 — 네이버 로그인이 필요해 Aside 몫.
- plan 작성 자동화(claude -p 등) — 미정.

## 테스트

```bash
cd .claude/skills/attr-tag/scripts && ../../../../.venv/bin/python3 -m unittest test_attr_tag
```
