---
name: sold-lock
description: 전날(KST) 결제완료 주문이 들어온 상품을 52개 스마트스토어 커머스API로 모아, 불사자에서 '잠금'(= MCP 숨김) 처리해 물갈이 삭제에 휩쓸리지 않게 한다. 매일 00:01 맥북 launchd 로 자동 실행된다. "판매상품 잠금", "팔린 상품 잠가줘", "sold-lock", "주문상품 잠금 돌려줘" 등을 언급하면 자동 실행.
---

# 판매상품 자동잠금 (sold-lock)

팔린 상품이 물갈이 삭제로 사라지는 사고를 사람 손 없이 막는다.
흐름은 [bulsaja-product-lock](../bulsaja-product-lock/SKILL.md) 과 같은 hide 2단계이고, 앞에 **판정 가드**가 붙는다.

## 무엇을 하나

1. 불사자 계정이 `부킹` 인지 확인 (다르거나 조회 실패 → 종료코드 3, 아무것도 안 함)
2. 키 정본 시트(★마진율계산기★ `사업자정리` 탭)에서 마켓별 커머스 키 로드 → 실패 시 로컬 캐시
3. 52마켓(1-1~4-3 · 11-1~11-3 · 13-1~24-3 · 25-1) 전날 결제완료 주문 수집, 마켓 안에서 판매자상품코드 기준 중복제거
4. 불사자 `find_by_code` → `workdata(full)` 의 스스 상품번호로 대조 → 판정
5. 통과분만 `bulsaja_product_hide hide:true` → confirmationToken 재제출 → **재조회로 잠금 확인된 것만** 신규잠금으로 센다

## 판정 규칙

정확히 1건 + 스스 상품번호 일치 + 마켓그룹에 `용쌤{마켓번호}`(숫자 경계) — 셋 다 맞을 때만 잠근다.

| 사유 코드 | 뜻 |
|---|---|
| `not_found` | 불사자에서 코드로 조회 안 됨 |
| `multiple` | 같은 코드 상품이 2건 이상 |
| `ss_lookup_failed` | 스스 상품번호 조회 실패 |
| `productno_mismatch` | 불사자의 스스 상품번호 ≠ 주문 상품번호 (미업로드 포함) |
| `market_mismatch` | 마켓그룹이 주문 마켓과 다름 (`용쌤1-1` 은 `용쌤11-1`·`용쌤1-12` 에 안 걸림) |
| `lock_state_unknown` | 잠금 상태(`숨김`/`잠금` bool)를 못 읽음 |
| `lookup_error` | find_by_code 호출 오류 (0건으로 접지 않는다) |
| `lock_failed` | 잠금 호출 실패 |
| `lock_unverified` | 잠금 후 재조회에서 잠금 확인 안 됨 |
| (`already_locked`) | 이미 잠김 — 쓰기 없음. 같은 날 재실행해도 여기로 빠져 멱등 |

## 실행

```bash
.venv/bin/python3 .claude/skills/sold-lock/scripts/run_sold_lock.py                    # 어제치
.venv/bin/python3 .claude/skills/sold-lock/scripts/run_sold_lock.py --date 2026-10-15 --dry-run
.venv/bin/python3 .claude/skills/sold-lock/scripts/run_sold_lock.py --markets 1-1,2-1
```

종료코드: 0 정상(스킵 있어도) · 2 키 로드 불가 · 3 계정 불일치.

## 산출물 — `<데이터루트>/sold-lock/<대상날짜>/`

| 파일 | 내용 |
|---|---|
| `orders.json` | 중복제거된 주문 (시크릿 없음) |
| `result.json` | 마켓별 상태·주문수·키 출처(sheet/cache), totals, 항목별 판정·사유, 업무판 기록 결과 |
| `new_locks.json` | 신규잠금 목록. 재실행 시 덮지 않고 병합 |

데이터루트는 `workspace.toml` 의 `paths.data_root`. 업무판 시트는 `sheets.work_board`, 키 시트는 `sheets.orders` — ID 는 코드·문서에 적지 않는다.

## 업무판 기록

'업무판' 시트 `오늘` 탭에 1행: 번호(최댓값+1) · 실행일 · 확인(스킵 0 + 실패마켓 0 일 때만 체크) · `⑥ 판매상품 잠금 <대상날짜>` · ⑥ · Claude · 자동 · 요약메모.
dry-run 이면 할 일 앞에 `[dry-run] `. 시트 쓰기가 실패해도 `result.json` 은 남는다(`board.status=failed`).

## 키·시크릿

- 정본은 키 시트. 성공할 때마다 `~/.eroom/naver-commerce-stores.json` (0600) 에 캐시, 시트 장애 시 캐시로 폴백.
- 시크릿·토큰은 stdout·로그·산출물 어디에도 안 나온다 (전부 `safe_json`/`redact` 경유, 테스트로 단언).
- 15-3 처럼 정지된 마켓은 토큰 발급이 400 → `token_failed` 로 기록하고 나머지 마켓은 계속 간다.

## 자동 스케줄 (launchd, 매일 00:01 · `caffeinate -i`)

설치:
```bash
WS="$(pwd)"   # 워크스페이스 루트에서 실행
mkdir -p "$HOME/python_work/data/sold-lock/logs"
sed -e "s#__WORKSPACE__#$WS#g" -e "s#__HOME__#$HOME#g" \
  .claude/skills/sold-lock/launchd/com.eroom.sold-lock.plist > "$HOME/Library/LaunchAgents/com.eroom.sold-lock.plist"
plutil -lint "$HOME/Library/LaunchAgents/com.eroom.sold-lock.plist"
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.eroom.sold-lock.plist"
```
해제: `launchctl bootout gui/$(id -u)/com.eroom.sold-lock`
로그: `~/python_work/data/sold-lock/logs/launchd.{out,err}.log` · 상태: `launchctl print gui/$(id -u)/com.eroom.sold-lock`

## 반영은 기본 자동

사용자 실제 잠금 승인 2026-10-16. [_shared/스킬-계약.md](../_shared/스킬-계약.md) §반영은 기본 자동이다 — 판정 가드를 통과한 것만 묻지 않고 잠근다. 잠금은 삭제만 막고 노출·업로드에는 영향이 없다.
