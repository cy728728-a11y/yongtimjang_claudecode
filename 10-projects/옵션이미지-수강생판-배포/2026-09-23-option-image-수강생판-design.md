# 옵션이미지 스킬 수강생판 — 설계

> 작성 2026-09-23 · 대상 저장소 `bulsaja/yongteam-skills` (Write 권한: `eroom1986`)
> 원본: 내 워크스페이스 `.claude/skills/bulsaja-option-image/` (2026-09-16 실전 검증본)

## 목표

용팀장 개인 스킬로 만든 **불사자 옵션 이미지 교체**를 수강생 플러그인
(`yongteam-skills`)의 6번째 스킬로 내보낸다. 수강생이 자기 OpenAI 키로 돌리고,
개인 정보·개인 경로는 하나도 따라가지 않는다.

### 왜 필요한가 (수강생 입장)

옵션 이미지는 타오바오 원본(중국어 배지·중국 브랜드 로고)이 그대로 남는다.
쿠팡 썸네일 모드가 "옵션 이미지 사용"인 상품은 **옵션 이미지 = 쿠팡 썸네일**이라,
그대로 두면 중국어 썸네일이 노출된다.

## 결정 사항 (2026-09-23 용팀장 승인)

| 항목 | 결정 | 근거 |
|---|---|---|
| 작업 단위 | **1상품** (마켓그룹 배치 없음) | 수강생 본인 과금이라 체감하며 써야 함. 사고나도 한 상품에서 멈춤 |
| 이미지 생성 | **OpenAI `gpt-image-2` 키 필수** | 한국어 스펙 문구 합성은 편집 API 아니면 품질이 안 나옴. 불사자 내부 AI 대체 안 함 |
| 품질 파라미터 | **보내지 않음(OpenAI 기본값)** | 2026-09-16 검수 통과분이 이 설정. 바꾸면 결과가 달라짐 |
| 비용 게이트 | **고지만 하고 진행** (승인 안 받음) | 용팀장 지시. 기존 스킬 계약의 "반영은 기본 자동"과 결 맞춤 |
| 키 저장 위치 | `~/bulsaja-작업/.env` | 플러그인 폴더 안에 두면 버전 업데이트마다 날아감 |

## 구조

```
skills/option-image/
├── SKILL.md                    Step 0 은 기존 5개와 동일 문구
├── references/
│   ├── spec-작성법.md
│   ├── 검수-판정기준.md
│   └── OpenAI-키-발급.md
└── scripts/
    ├── run.py                  inspect / generate / apply / restore
    ├── option_rules.py         순수 규칙 (네트워크 없음)
    ├── gen_image.py            gpt-image-2 편집 호출
    ├── onboard.py              키 점검·검증·저장
    ├── test_option_rules.py
    └── test_onboard.py
```

- MCP 전송은 저장소의 `lib/bulsajalib/bulsaja.py` `BulsajaMCP` 를 상속한다.
  원본이 들고 있던 `bulsaja_client.py` · `mcp_transport.py` 벤더링 사본은 버린다.
- `sys.path` 부트스트랩은 `skills/thumbnail/scripts/run_thumbs.py` 와 같은 형태
  (스크립트에서 위로 올라가며 `lib/bulsajalib` 를 찾는다).

## 걷어내는 개인 흔적

| 원본 | 수강생판 |
|---|---|
| `C:/Users/workspace/.venv/Scripts/python.exe` | `$PY` (Step 0 부트스트랩이 정함) |
| `C:/python_work/data/option-image/` | `~/bulsaja-작업/option-image/` |
| `DEFAULT_ACCOUNT_KEY = "bulsaja"` · `--account` · `BULSAJA_ACCOUNT_KEY` | 삭제 — 수강생은 연결키 하나 |
| `load_config_by_key()` (전역 `BULSAJA_MCP_TOKEN` 우회) | 삭제 — 용팀장 PC 전용 문제 |
| 키 폴백 `smartstore-brand/scripts/.env` | 삭제 — 수강생에겐 없는 스킬 |
| `ledger.jsonl` 을 `C:/python_work/...` 에 | `~/bulsaja-작업/option-image/ledger.jsonl` |

시트는 원본이 쓰지 않는다(1상품 단위 · 로컬 원장). 구글 계정 정보가 새어 갈 자리가 없다.

## 키 온보딩 (신규 — `onboard.py`)

### 수강생이 밟아야 하는 절차

1. OpenAI 플랫폼 가입
2. 결제수단 등록·충전
3. **API Organization Verification (신분증)** ← `gpt-image-2` 가 이 뒤에 열린다
4. API 키 발급 (`sk-...`)
5. 스킬에 입력

3번은 사람이 직접 해야 한다. 여기서 못 넘어오는 수강생이 나온다 —
`references/OpenAI-키-발급.md` 가 이 단계를 화면 그대로 설명한다.

### 검증은 돈이 들지 않아야 한다

키를 받으면 **생성 호출 전에** `GET /v1/models/gpt-image-2` 로 확인한다.

| 응답 | 판정 | 안내 |
|---|---|---|
| 200 | 통과 | `.env` 에 저장하고 진행 |
| 401 | 키가 틀림 | 키를 다시 확인 (`sk-` 로 시작) |
| 403 / 404 | 조직 인증 미완료 | 3단계를 먼저 끝내야 한다 — 가장 흔한 실패 |
| 429 / 5xx | 일시 오류 | 잠시 후 재시도 |

생성 단계에서 `insufficient_quota` 가 오면 **잔액 부족**으로 따로 구분해 알린다
(키 문제로 오해하면 엉뚱한 데를 고치게 된다).

### 저장 형식

`~/bulsaja-작업/.env` 에 `OPENAI_API_KEY=sk-...` 한 줄.
읽기는 `bulsajalib/envload.py` 의 `load_env()` (환경변수 우선).
키는 **화면에 절대 다시 찍지 않는다** — 앞 7자리 + 길이만 보여준다.

## 비용 고지

`generate` 직전 한 줄:

```
[비용] 옵션 4장 생성 — 장당 약 $0.1 (원본 첨부 편집), 예상 약 $0.4 (약 580원)
```

승인을 묻지 않고 바로 진행한다. 끝난 뒤 보고에 **실제 생성 장수(재시도 포함)** 를 싣는다.

## 흐름 (원본과 동일 — 4단계)

1. `inspect --code <판매자상품코드>` → 판매 중 옵션·현재 이미지·기작업 여부 → `options.json`
2. **Claude 가 `cur_<번호>.*` 를 전부 열어** 실물·스펙 확인 후 `spec.json` 작성
3. `generate` → `gen_<번호>.png` (동시 3장, 1회 자동 재시도)
4. **Claude 가 `gen_*.png` 를 전부 열어 검수** → `apply` → 재조회 검증 → 원장 기록

`restore --run-dir <R>` 로 `before_apply.json` 기준 복원.

## 유지되는 안전선 (원본에서 그대로)

- **1차원 옵션만.** 복합옵션은 `inspect` 가 거부한다.
- 옵션값 이미지와 가격탭 이미지가 **함께** 바뀐다. `before_apply.json` 은 둘을 따로 저장하고,
  `restore` 는 원래 달랐던 옵션만 가격탭을 별도로 되돌린다.
- `apply` 는 성공 응답을 믿지 않고 **재조회로 검증**한다.
- 업로드 주소는 내용 해시 → 같은 그림 재업로드는 `변경 0건`(멱등). 실패가 아니다.
- 기작업(`/mcp-assets/`) 옵션은 `--force` 나 `source` 없이는 건너뛴다. 가공본 위에 또 가공하지 않는다.
- `--force` 를 `--vids` 없이 주면 전 옵션 재생성(전부 과금) — 경고를 찍는다.
- 문구는 **원본에 있는 것만.** 없는 스펙을 지어내면 CS 로 돌아온다.

## 테스트

네트워크 없이 도는 것만 (배포 검사에서 전체 실행됨):

- `test_option_rules.py` — 옵션 추리기 · 기작업/번역본 판별 · spec 검증 · 프롬프트 조립 (원본 이식)
- `test_onboard.py` — 키 판정 분기: 없음 / 형식오류 / 401 / 403 / 200 / 잔액부족 메시지

## 배포

1. `main` 에 커밋·푸시 (버전을 올리지 않으면 수강생에게 나가지 않는다)
2. `.claude-plugin/plugin.json` 설명 **5종 → 6종**
3. `CHANGELOG.md` 에 2.5.0 항목
4. Actions **"새 버전 내보내기"** → `2.5.0` (기능 추가 = 가운데 +1)
   → 초록 체크 = 수강생 반영 완료

**배포 버튼은 용팀장이 확인한 뒤 누른다.** 커밋·푸시까지만 미리 해 둔다.

## 미확인 · 위험

- **수강생 등급에서 옵션 이미지 교체 도구가 열리는지** — 용쌤 계정(`수강생: true`)으로
  2026-09-16 실제 반영이 성공했으므로 열릴 가능성이 높다. 다만 그 계정은 플랜을 여러 개
  보유해서 완전한 확증은 아니다. **하우제로님께 한 번 확인받는 것이 안전하다.**
- 조직 인증을 못 넘는 수강생 비율은 예측 불가. 문의가 몰리면 `OpenAI-키-발급.md` 를 보강한다.
