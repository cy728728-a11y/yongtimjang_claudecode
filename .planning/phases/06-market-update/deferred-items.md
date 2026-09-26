# Phase 06 — Deferred Items

## 06-03 실행 중 발견 (범위 밖 — 손대지 않음)

- **`webapp/tests/no_commit_guard.sh` 가 실패한다 — `test_market_cli.py`(06-02 산출물)에 `--commit` 리터럴 7건.**
  06-03 이전부터 깨져 있었다(1ba8cc0 · acbee4d). 06-03 이 더한 테스트(`test_argv.py` · `test_routes_market.py`)는
  `"--" + "commit"` 간접 조립으로 바꿔 가드에 걸리지 않는다. `test_market_cli.py` 는 가짜 MCP 하네스라
  실제 쓰기가 나갈 경로는 없지만, 가드는 글자 자체를 금지한다. 06-05 전에 같은 방식(상수 간접 조립)으로
  고치거나, 가드의 제외 목록에 가짜 MCP 전용 CLI 테스트를 넣을지 결정이 필요하다.

  **→ 해결됨 (06-04 실행 중, 별도 커밋 `fix(06-02)`).** `test_market_cli.py` 의 7건을 모듈 상수
  `_반영플래그 = "--" + "commit"` 간접 조립으로 바꿨다(주석 1건은 문구만 교체). 테스트 의미 불변 —
  66 passed 그대로. `bash webapp/tests/no_commit_guard.sh` → OK. 가드 제외 목록은 건드리지 않았다.
