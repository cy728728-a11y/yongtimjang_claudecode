---
name: kc-claim
description: 네이버 쇼핑 안전거래센터 "KC인증 소명접수 안내" 메일을 감지해 신고 상품을 불사자·마켓에서 삭제한다(같은 불사자코드 복사본 전부). 소명 메일은 보내지 않는다. 매일 09:00 예약 실행. "KC 메일 처리", "KC인증 소명", "KC 민원", "안전거래센터 메일" 등을 언급하면 자동 실행.
---

# KC인증 민원 자동처리 (kc-claim)

`help_safety_shopping@navercorp.com` 의 "[네이버 쇼핑 안전거래센터] KC인증 소명접수 안내" 메일 처리.

## 결정 (2026-11-19 용팀장)
- **삭제만 하고 소명 메일은 안 보낸다.** 미소명 불이익(구매불가 → 30일 뒤 판매금지)은 상품에 걸리는데, 지워지면 걸 대상이 없다. 소명은 그 스토어 계정 메일로만 가능하고 수집함(cy728728)으로는 못 보낸다.
- 구매대행이라 KC 인증서가 없고, "대상 아님" 소명은 거의 안 받아준다 → 따지지 않는다.
- 같은 불사자코드 복사본은 **상품명과 무관하게 전부** 지운다(같은 물건 = 같은 인증 문제). 첫 건: 라디오 원본 2 + 복사본 29 삭제.
- 판매돼 잠긴 상품은 지우지 않는다 → status `locked` + 폰 알림(ntfy). 사람 판단.

## 흐름
1. 수집함 IMAP(읽기전용) 최근 14일 → 상품번호·소명기한 파싱
2. 상품번호 → 커머스API 전 마켓 조회(12-1 제외) → 판매자상품코드. 전 마켓에 없으면 이미 삭제(done). 조회 오류 난 마켓이 있으면 단정 안 하고 failed
3. 불사자 `부킹` 계정 확인 → `find_by_code` 원본 + 같은 불사자코드 전부 → `market_delete` MARKET_AND_SOURCE · ALL (rights-claim 함수 재사용)
4. 스마트스토어 재조회로 삭제 확인(최대 20분)
5. 대장 기록 + **검수기준 반영 대기열** `inspect_queue.jsonl` 에 상품명 추가 → sourcing-inspect 가 검수 시작 때 규칙에 넣는다

## 실행
```bash
.venv/bin/python3 .claude/skills/kc-claim/scripts/run_kc_claim.py              # dry-run (삭제 미리보기)
.venv/bin/python3 .claude/skills/kc-claim/scripts/run_kc_claim.py --apply      # 예약 작업이 매일 09:00
.venv/bin/python3 .claude/skills/kc-claim/scripts/run_kc_claim.py --apply --no 13809792787
```
종료코드 `0` 정상 · `1` 실패/부분/잠금 있음 · `4` 다른 실행 중.

## 파일 — `~/python_work/data/kc-claim/`
- `ledger.jsonl` — 상품번호별 1행. status `done`(재처리 안 함) · `locked`(재처리 안 함, 사람 몫) · `partial`/`failed`(다음날 재시도)
- `inspect_queue.jsonl` — 검수기준 반영 대기열. `reflected:false` 를 sourcing-inspect 가 처리

## 함정
- 메일 제목 키워드로 불사자를 검색하지 않는다 — 상품번호 → 판매자코드 → find_by_code 체인만.
- 소명기한은 메일 받은 날 +3일. 실패 알림이 오면 그날 안에 수동으로 지워야 한다.
