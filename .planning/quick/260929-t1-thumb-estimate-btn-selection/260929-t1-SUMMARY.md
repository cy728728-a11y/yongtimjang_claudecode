---
quick: 260929-t1
completed: 2026-09-29
key-files:
  modified: [webapp/static/thumb.js]
---
# Quick 260929-t1 Summary: 썸네일 견적 버튼이 ② 체크박스 선택에 반응

thumb.js 가 `Tabulator.findTable("#board")[0].on("rowSelectionChanged", 버튼갱신)` 으로 선택 변화를 직접 구독한다. board.js 무수정(D-19 유지). click/keyup 리스너는 보조로 남김.

## 검증
- `node --check webapp/static/thumb.js` OK
- `.venv-web/bin/pytest webapp/tests -q` 전부 통과(rc=0)
- `no_commit_guard.sh` OK
- 격리 헤드리스 크롬(임시 포트·임시 data_root·임시 jobs.db, 합성 ② 3행 zz*): CDP `Input.dispatchMouseEvent` 로 행 체크박스 클릭
  - 수정 전 코드: 선택 1건인데 버튼 disabled → FAIL (버그 재현)
  - 수정 후: 선택 1건 → 버튼 enabled, 해제 → disabled → PASS
- 실서버 PID 72246(:8765)·실 DB·불사자/gws 무접촉

## 곁가지
- coupang.js: `#coupang-preview-btn` 을 선택과 무관하게 즉시 켜므로 같은 버그 없음 — 수정 안 함.

## Deviations
None.

## 반영
정적 JS 만 바뀌었다 — 서버 재시작 불필요, 브라우저 새로고침(캐시 남으면 강력 새로고침)만 하면 된다.
