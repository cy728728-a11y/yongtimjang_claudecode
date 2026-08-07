---
name: captcha-relay
description: 브라우저 작업 중 캡챠(보안 확인)를 만났을 때, 답변 '판단'만 Aside 에게 파일로 위임하고 입력·제출은 Claude 가 직접 하는 릴레이 프로토콜. "캡챠 떴어", "보안 확인 나왔어", "캡챠감지", "캡챠 풀어줘", "captcha" 를 언급하거나 카테고리 조회(aside-category·bulsaja-category-fix)가 `캡챠감지` 로 멈췄을 때 자동 실행.
allowed-tools:
  - Bash
  - Read
---

# 캡챠 릴레이 (captcha-relay)

캡챠를 만나면 **혼자 판단해서 풀지 않는다.** 화면을 찍어 Aside 에게 물어보고,
받은 답을 **Claude 가 직접** 입력·제출한다. Aside 는 파일만 읽고 쓸 뿐 탭을 건드리지
않으므로 탭 제어권이 겹치지 않는다.

공유 폴더: `~/.aside/u/0/captcha-relay/` (`requests/` → `responses/` → `processed/`)

## 언제 쓰나

| 상황 | 쓴다? |
|---|---|
| `aside-category` / `bulsaja-category-fix` 가 `캡챠감지` 로 멈췄다 | ✅ |
| 브라우저 작업 중 "보안 확인을 완료해 주세요" 화면을 만났다 | ✅ |
| 로그인 2FA·SMS 인증 | ❌ 이룸님 직접 |
| `차단감지`(접속 제한) | ❌ 캡챠가 아니다. 쉬었다 재개 |
| 같은 캡챠를 이미 2번 시도해 실패 | ❌ 이룸님에게 보고 |

## 전제 (2026-08-06 실측)

- **캡챠 탭은 Aside 앱 탭이어야 한다.** `aside repl` 의 `openTab()` 으로 연 탭은
  CLI 프로세스가 끝나면 사라져서, 요청↔응답 사이(수 분)를 못 버틴다.
  → 스크립트가 `open -a Aside <url>` 로 앱 탭을 띄운다.
- **응답까지 최대 5분**이 걸린다(Aside 가 `requests/` 를 주기적으로 훑는다).
  실측 왕복 3.5분. 그래서 기본 타임아웃이 **6분**이다 — 프로토콜 문서의 "2분"은
  Aside 감시 주기보다 짧아서 살아 있는 루프를 죽은 걸로 오판한다.
- `aside repl` 은 호출당 ~120초에서 끊긴다. 그래서 대기는 repl 안이 아니라
  **파이썬 쪽에서** 한다.

## 사용

```bash
PY=".venv/bin/python"
S=".claude/skills/captcha-relay/scripts/captcha_relay.py"

# 한 방에: 앱 탭 열기 → 캡처 → 요청 → 대기 → 입력·제출 → 검증
$PY $S solve --url "<캡챠가 뜨는 URL>" --match "search.shopping.naver.com" --submit

# 이미 앱 탭에 캡챠가 떠 있으면 --url 생략(활성 탭 또는 --match 로 지정)
$PY $S solve --match "search.shopping.naver.com" --submit
```

| 서브커맨드 | 하는 일 |
|---|---|
| `solve` | (열기 →) 캡처 → 요청 → 대기 → (`--submit` 이면) 입력·제출·검증 |
| `capture` | 캡챠 탭 스크린샷 + 질문 추출만 (요청 안 보냄) |
| `ask` | 요청 파일 쓰고 응답 대기 (`--no-wait` 면 쓰기만) |
| `submit` | 받은 답을 입력창에 넣고 제출 |
| `ping` | Aside 감시 루프 생존 확인 |
| `status` | 응답 안 온 요청 목록 |

주요 옵션: `--timeout`(기본 360초) · `--poll`(4초) · `--match`(붙을 탭 URL 부분문자열) ·
`--id`(기본 `YYYYMMDD-HHMMSS-rand4`). 나머지는 `--help`.

## 종료코드 = 다음 행동

| 코드 | 뜻 | 다음 행동 |
|---|---|---|
| `0` | `answered` — 답을 받았다 | `--submit` 이면 이미 제출됨. `submit.ok` 확인 후 원래 작업 `--resume` |
| `3` | `needs_human` — Aside 도 확신 못 함 | **재시도하지 않는다.** 이룸님에게 화면·질문을 알리고 물어본다 |
| `4` | `timeout` — 시간 안에 답이 없음 | 이룸님에게 알린다. `ping` 으로 루프 생존을 같이 확인 |
| `5` | 캡처/환경 실패 (탭 없음, aside CLI 없음 등) | 탭이 닫혔는지 확인. 원인 못 잡으면 이룸님에게 보고 |

`--submit` 을 줘도 **`answered` 이고 `answer` 가 비어 있지 않을 때만** 제출한다.
`needs_human`·`timeout` 을 제출로 흘리면 캡챠를 한 번 더 태워 차단만 깊어진다.

## 카테고리 작업에 끼워 넣기

`aside_category.py` 는 `캡챠감지` 를 만나면 그 청크에서 멈추고 남은 청크를 돌지 않는다.
그때 이 순서로 잇는다.

1. 결과 JSON 에서 `상태 == "캡챠감지"` 인 건의 `url` 을 꺼낸다.
2. `solve --url "<그 url>" --match "search.shopping.naver.com" --submit`
3. 종료코드 `0` 이고 `submit.ok == true` → 원래 명령을 `--resume` 으로 이어서 돌린다.
4. 그 외 → **재조회하지 않고** 이룸님에게 보고한다.

캡챠를 푼 뒤 재개할 때는 `--rest-every 5 --rest-secs 120` 처럼 휴식을 같이 준다.
캡챠는 조회 **간격**이 아니라 누적 **총량**에 반응한다 — 간격만 늘리면 또 만난다.

## 레드 플래그 — 멈추고 이룸님에게

- 스스로 캡챠 답을 추론해서 입력하려 한다 → **금지.** 판단은 Aside, 입력은 Claude.
  Aside 가 답을 안 줬으면 답이 없는 것이다.
- 같은 캡챠에 3번째 요청을 보내려 한다 → 멈춘다. 2회가 상한.
- `needs_human` 을 받고 "그래도 6인 것 같으니 넣어보자" → 금지. 오답은 차단을 깊게 한다.
- 캡챠 이미지를 우회·자동해독하려 한다 → 이 스킬의 범위 밖. 사이트가 자동화를
  막겠다고 밝힌 표시다.
- 응답이 늦다고 타임아웃을 10분 이상으로 늘린다 → 루프가 죽은 것이다. `ping` 으로 확인.

## 함정

- **`page.screenshot({path})` 는 세션 디렉터리 밖을 막는다** (`escapes the session
  directory`). `fs.writeFile` 은 안 막히므로 버퍼로 받아서 직접 쓴다.
- **제출 후 검증에 URL 조건을 쓰면 안 된다.** 감지(`driver.js`)는 URL 에 `captcha` 가
  있으면 캡챠로 보지만, 검증은 화면이 이미 통과했는데도 URL 이 남아 있어 실패로 오판한다.
  → `submit` 은 본문 텍스트·입력창 표식만 본다.
- **앱 탭은 repl `closeTab()` 으로 안 닫힌다**(세션에서 분리될 뿐). 캡챠를 푼 탭은
  그대로 두는 게 낫다 — 세션이 풀린 상태가 유지된다.
- 입력창 후보가 여럿이면 `submit` 은 **아무 데도 넣지 않고** 스냅샷을 돌려준다.
  엉뚱한 칸에 넣으면 캡챠를 한 번 더 태운다. 그때는 스냅샷을 보고 직접 넣는다.

## 검증 상태 (2026-08-06)

| 구간 | 상태 |
|---|---|
| 단위 테스트 15건 (id·질문추출·요청스키마·폴링·종료코드) | ✅ `test_captcha_relay.py` |
| 앱 탭 열기 → 캡처 → PNG 저장 | ✅ 실측 |
| 요청 → Aside 응답 왕복 (영수증형 질문, 실제 Aside 루프) | ✅ 3.5분, 정답 반환 |
| 답 입력 → 제출 → `정상` 검증 | ✅ 모의 캡챠 페이지 |
| **네이버 실물 캡챠** | ❌ 미검증 — 실물을 만나야 확인된다 |

실물 첫 조우 때 확인할 것: 입력창 셀렉터가 잡히는지, Enter 로 제출되는지,
제출 후 원래 검색 결과로 돌아오는지. 안 맞으면 `SUBMIT_JS` 를 고친다.

## 관련

- `aside-category` — 캡챠를 감지하고 멈추는 쪽(`driver.js` 의 `PAGESTATE`)
- `bulsaja-category-fix` — 카테고리 교정 전체 흐름
- 프로토콜 원문: `~/.aside/u/0/captcha-relay/README.md`
