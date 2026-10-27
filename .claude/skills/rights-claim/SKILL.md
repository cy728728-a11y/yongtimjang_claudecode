---
name: rights-claim
description: 네이버 권리보호센터 소명요청 메일을 감지해 신고 상품을 불사자에서 삭제하고 고정 문구로 소명을 접수한 뒤 카톡 보고한다. 매일 09:00 예약 실행. "권리침해 메일 처리", "소명요청 처리", "권리보호센터", "소명 처리해줘" 등을 언급하면 자동 실행.
---

# 권리보호센터 소명요청 자동처리 (rights-claim)

`nv_shopping_ips@navercorp.com` 의 "[권리보호센터]권리침해로 인한 소명요청" 메일을 사람 손 없이 처리한다.
3일 안에 소명하지 않으면 상품 조치·몰 폐쇄 위험이 있다. 2026-10-27 수동으로 1회 성공한 절차를 그대로 옮겼다.
배경·허용 범위: 메모리 `rights-claim-auto-handling` (`~/.claude/projects/-Users-choiyongsmacbook-Documents-yongtimjang-claudecode/memory/rights-claim-auto-handling.md`)

## 무엇을 하나

1. **감지** — 수집함(cy728728) IMAP 전체보관함에서 최근 14일 발신 `nv_shopping_ips@navercorp.com` + 제목 `소명요청` 메일 → 신고자·권리명·권리번호·대표접수번호·소명링크·OTP 파싱 (읽음 표시 안 바꿈)
2. **신고대상 조회** — Aside 브라우저로 소명링크 열기 → OTP 입력 → `/explains/<개별접수번호>` 의 신고 상품번호·스토어명
3. **판매자상품코드** — 스토어명 → `~/.eroom/naver-commerce-stores.json` 마켓번호(불일치 시 전 마켓 폴백) → 커머스API `sellerManagementCode`. "원상품번호를 찾지 못함" = 이미 삭제됨
4. **불사자 삭제** — 계정 `부킹` 확인 → `find_by_code`(판매자코드) 원본 + `find_by_code`(불사자코드) 중 **상품명에 상표명이 들어간 복사본만** → `market_delete` MARKET_AND_SOURCE · scope ALL (확인키 2단계). 잠금 상품은 제외
5. **마켓삭제 확인** — 30초 간격 최대 40회(20분) 커머스 재조회 (미확인이어도 소명은 진행 → partial)
6. **소명 제출** — 고정 문구(`references/소명문구.txt`, 424자) 입력 → '서약 및 동의' 체크 → '소명 접수하기' → "권리 소명이 접수되었어요" 확인. 실패 시 스크린샷
7. **보고** — 카톡 나와의 채팅 + 대장 1행

## 실행

```bash
.venv/bin/python3 .claude/skills/rights-claim/scripts/run_rights_claim.py --dry-run          # 조회만 (기본)
.venv/bin/python3 .claude/skills/rights-claim/scripts/run_rights_claim.py --apply            # 예약 작업이 매일 09:00 실행
.venv/bin/python3 .claude/skills/rights-claim/scripts/run_rights_claim.py --dry-run --receipt 261022S506292 --no-browser
.venv/bin/python3 .claude/skills/rights-claim/scripts/run_rights_claim.py --mark-done 261022S506292
```

| 옵션 | 뜻 |
|---|---|
| `--dry-run` | 조회만. 삭제는 확인키 1단계(미리보기)까지만, 소명 제출·카톡·대장 쓰기 없음. 옵션이 없어도 dry-run |
| `--apply` | 삭제·소명·카톡·대장 실제 실행 |
| `--since-days N` | 수집함 조회 기간 (기본 14) |
| `--receipt X` | 대표접수번호 X 만 처리 (대장 done 이어도 처리) |
| `--mark-done X` | 대장에 X 를 done(수동) 으로 기록. 외부 호출 없음 |
| `--no-browser` | Aside 단계 전부 생략 (신고대상 없음으로 진행) |
| `--expect-nick` | 기대 불사자 계정 닉네임 (기본 `부킹`) |

종료코드: `0` 정상(새 메일 없음 포함) · `1` 실패/부분 건 있음 · `3` 불사자 계정 불일치 · `4` 다른 실행 중(락).

## 안전 규칙

- **메일 권리명으로 불사자를 검색하지 않는다.** '물레방아' 상표(테이프커터기) 신고에 키워드 검색은 물레방아 분수대 수십 건을 잡았다. 삭제 대상은 소명페이지 상품번호 → 커머스 판매자코드 → `find_by_code` 체인으로만 정한다. 복사본은 같은 불사자코드 + 상품명에 상표명 토큰이 있을 때만.
- **잠금(판매된) 상품은 삭제하지 않는다.** 보고의 "잠금 K" 로 따로 센다.
- **Aside 쓰기 예외는 right.naver.com 소명 페이지 한정.** 링크가 `https://right.naver.com/otp?code=` 로 시작하지 않으면 브라우저를 열지 않고 실패 처리한다(사칭 메일 방지). 다른 네이버 쓰기는 여전히 금지.
- 불사자 계정 확인이나 조회가 실패하면 **삭제도 소명도 하지 않는다** (소명 문구가 "즉시 삭제 조치"를 말하기 때문).
- 로그는 IMAP 비밀번호·커머스 시크릿/토큰·OTP·소명링크를 마스킹한다. 대장에는 링크·OTP 를 저장하지 않는다. 카톡 실패 보고의 OTP·링크는 수동 처리용으로 의도한 노출이다.

## 대장 — `<데이터루트>/rights-claim/ledger.jsonl`

append-only. 키는 **대표접수번호**(`261022S…`), 개별접수번호(`261026X…`)는 `explain_no` 기록용.

| status | 뜻 | 다음 09:00 |
|---|---|---|
| `done` | 삭제·마켓확인·소명 모두 완료 (또는 `--mark-done`) | 건너뜀 |
| `partial` | 소명은 접수됐지만 삭제 일부 실패·마켓삭제 미확인 | 재시도 — 저장된 신고대상으로 삭제·확인만 (소명 재제출 안 함) |
| `failed` | 메일 파싱·소명페이지 조회·불사자·소명 제출 중 실패 | 처음부터 재시도 |

산출물: 실패 스크린샷 `<데이터루트>/rights-claim/shots/<접수번호>_<시각>.png`, 락 `<데이터루트>/rights-claim/.lock`.

## 실패했을 때 (수동 처리)

카톡에 "수동 처리 필요 + 실패단계 + OTP" 가 오고 버튼 링크가 소명페이지다.
1. 링크를 열어 OTP 입력 → 신고 상품 확인 → 불사자에서 삭제 → 고정 문구로 소명 접수
2. 끝나면 `--mark-done <대표접수번호>` 로 대장에 기록해 다음날 재처리를 막는다

## Aside 구현 메모 (2026-10-27 실측)

- `aside mcp` 를 stdio JSON-RPC 로 직접 띄운다(`claude -p` 안 씀). tool `repl` 결과는 센티널 줄 `###RC###{json}` 만 읽는다.
- Aside 의 Playwright 판엔 `getByPlaceholder` 가 **없다**(not a function) → `locator('input[placeholder="…"]')` 로 쓴다. `getByRole`·`evaluateAll`·`check`·`isEnabled` 는 된다.
- Aside `fs` 는 세션 폴더 밖에 못 쓴다 → 실패 스크린샷은 base64 로 받아 파이썬이 저장한다.
- 소명 페이지 재사용은 같은 소명링크로 연 탭일 때만 한다(다른 건 페이지에 제출하는 사고 방지).

## 예약

`.claude/lib/eroom_scheduler.py` JOBS 의 `rights-claim` (daily 09:00, `--apply`, caffeinate — 마켓삭제 확인 폴링 최대 20분).
