---
quick_id: 260929-g1
subsystem: webapp/market-gate
tags: [htmx, oob, market, gate]
key-files:
  created:
    - webapp/templates/_market_commit_next.html
    - webapp/templates/_market_gate_response.html
  modified:
    - webapp/templates/_market_result_table.html
    - webapp/routes/jobs.py
    - webapp/tests/test_routes_market.py
completed: 2026-09-29
---

# Quick 260929-g1: 게이트 정상 직후 반영 실행 버튼 즉시 표시 Summary

게이트 판정 응답이 결과 표 아래 반영 버튼 자리(`#market-commit-next`)를 hx-swap-oob 로 같이 갈아끼워, '정상' 직후 "반영 실행 (최대 N건)" 이 새로고침 없이 뜬다.

## 변경
- `_market_commit_next.html`: 버튼 자리 조각. **자리는 항상 그린다**(빈 div 포함) — oob 대상이 DOM 에 없으면 htmx 가 버리기 때문. 버튼은 정상 · preview_job_id · 남은반영가능>0 일 때만.
- `_market_result_table.html`: 기존 조건부 `<p id="market-commit-next">` → 조각 include.
- `_market_gate_response.html`: 패널 + 조각(oob=True). `POST /market/gate` 가 이걸 렌더.
- 상한·대상 결정은 그대로 `_게이트패널ctx` → `_마켓반영상한()`. '이상' 이면 버튼 없는 빈 자리가 oob 로 덮인다.
- 버튼 클릭은 board.js 위임 리스너(`.market-commit-btn`)라 새로 들어온 버튼도 바로 동작.

## 검증
- 테스트 4건 추가: 정상 응답 oob 조각에 버튼·preview id·최대 7건(상한 monkeypatch) / 이상 응답 oob 빈 자리·버튼 없음 / 결과 표는 자리 상시·oob 속성 없음 / 새 템플릿 safe 없음.
- `.venv-web/bin/pytest webapp/tests -q` 통과(exit 0) · `no_commit_guard.sh` OK.
- 불사자 호출 0 · 마켓 쓰기 0 · 사용자 서버(:8765) 미접촉.

## Deviations
None. 서버 재시작 전까지 실행 중 서버에는 반영되지 않는다(템플릿·라우트 변경).

## Commits
- 79d68d9 fix(260929-g1): 게이트 정상 직후 반영 실행 버튼을 oob 로 바로 띄운다

## Self-Check: PASSED
