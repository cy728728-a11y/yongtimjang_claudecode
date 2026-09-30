---
quick: 260930-m3
completed: 2026-09-30
commit: db19e3f
key-files:
  modified: [webapp/routes/jobs.py, webapp/templates/_market_gate_panel.html, webapp/templates/_market_preview_table.html, webapp/tests/test_routes_market.py]
---

# Quick 260930-m3: 형제 미리보기 이중 반영 방지 Summary

같은 회차 `web/market_*/market_status.json` 의 손댄 항목(taskId·접수·대기·성공·실패)을 합쳐, 새 미리보기에서도 옛 반영분을 `반영됨(성공)` 으로 보이고 반영 대상에서 뺀다.

## 바뀐 것
- `webapp/routes/jobs.py` — `_마켓체크포인트_합침` 신설. 미리보기 표 · `post_market_commit` 대상 산정 · 게이트 패널 남은 수가 합집합 기준.
  게이트 닫힘(상한 1)인데 형제 미리보기가 이미 1건 냈으면 새 미리보기 반영 400(판정 전 2건 방지). 형제 체크포인트 깨짐 → 400/에러 표시.
- 템플릿 — 게이트 패널: 남은 0건이면 "남은 반영 대상 0건" (옛 "나머지를 진행해라" 제거). 미리보기 표: '나머지는 다음 회차' 는 남은 > 상한일 때만.
- CLI(`market_update.py`) 무변경 — 서버엔 "마켓 반영됨" 신호가 없고(workdata = 채널상품번호·상세만), 대상 산정은 원래 라우트 몫.

## 테스트
- 추가 6개(형제 성공 → 반영됨+대상 제외 재현 포함), 기존 `test_미리보기ctx_정상이면_최대N과_다음회차` 는 버그를 굳힌 기대값(zz01 이번 반영)이라 수정.
- `pytest webapp/tests` 941 passed · `no_commit_guard.sh` OK.

## Deviations
- [Rule 2] 게이트 닫힘 + 형제 손댐 이월 시 400 추가 — 합집합이 없으면 판정 전 두 번째 1건이 나갈 수 있음.

## 운영
**서버(:8765) 재시작 필요** (라우트·템플릿 변경). 도는 잡이 없을 때 재시작.

## Self-Check: PASSED
