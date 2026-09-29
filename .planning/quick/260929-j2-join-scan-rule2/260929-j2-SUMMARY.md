---
quick: 260929-j2
completed: 2026-09-29
commits: [fa11c74]
key-files:
  modified: [webapp/routes/jobs.py, webapp/tests/test_routes_jobs.py, .planning/phases/07-thumb-coupang/deferred-items.md]
---
# Quick 260929-j2: 조인 스캔 ② 추가 · 인덱스 ③⑤ 유지 Summary

조인 스캔 대상(②③⑤)과 인덱스 범위(③⑤)를 서로 다른 튜플로 쪼개 ② 행에도 불사자 조인이 붙게 했다. 인덱스 비용은 그대로다.

## 변경
- `webapp/routes/jobs.py`: `불사자_대상규칙` 제거 → `조인스캔_대상규칙 = (②썸네일교체, ③원인분석, ⑤효자확정)` · `인덱스_대상규칙 = (③원인분석, ⑤효자확정)`.
  공통 추출 `_규칙행키(판정, 규칙들)` + 얇은 래퍼 `_스캔대상키` / `_인덱스범위키`. 인덱스 라우트는 `_인덱스범위키` 로 행을 좁힌다.
  CLI(`bulsaja_scan.py`)는 규칙을 모르고 키만 받으므로 CLI 수정 없음(래핑 원칙).
- 테스트 3개 추가: 튜플 값 고정 + 인덱스 ⊂ 스캔 · ② 만 있는 회차도 스캔 200 · 인덱스는 ② 쪽 마켓그룹을 안 훑고 ② 만이면 400.
- 네거티브 확인: 인덱스가 스캔 원천을 쓰도록 되돌리면 인덱스 테스트가 실패함을 확인 후 원복.

## 검증
- `.venv-web/bin/pytest webapp/tests` → 935 passed · `no_commit_guard.sh` OK
- 불사자/gws 호출 0, 사용자 서버(PID 72246, :8765) 건드리지 않음.

## 남은 일
- 서버 재시작(도는 market_commit 잡이 끝난 뒤) → 회차 2026-09-20 조인 스캔 재실행(읽기·크레딧 0, 수 분). 그래야 ② 행에 조인이 붙어 썸네일 견적이 0 을 벗어난다.

## Deviations
- 판정 파일 모양이 깨졌을 때를 위한 `try/except AttributeError` 추가(대상 0건 → 호출부 400). 프로젝트 규칙(try-except 포함).

## Self-Check: PASSED
