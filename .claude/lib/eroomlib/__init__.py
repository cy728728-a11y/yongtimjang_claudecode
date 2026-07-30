"""eroomlib — Eroom 워크스페이스 공용 인프라 라이브러리.

하이픈 폴더명(스킬)이라 import 불가 → scripts 통째 sys.path insert 하던 취약점을
언더스코어 없는 정식 패키지명(eroomlib)으로 소멸시킨다.

모듈:
  gsheets   — gws CLI(Google Workspace) 얇은 래퍼: sheets_get / sheets_update
  webdriver — 봇 감지 우회 Chrome 드라이버(create_driver / make_driver / close_driver)
  bulsaja   — 불사자 원격 HTTP MCP transport(BulsajaMCP: open/list_tools/call_tool/close)
  textnorm  — 텍스트 정규화 1벌(nows / cat_key / sanitize_part)
  envload   — .env 로더 1벌(load_env)
  runner    — 스킬 순회 러너. onestep(세로: 상품 1개 × 작업 전부) · signals · approval_log
  config    — 워크스페이스 설정 1벌(cfg / run_dir / group_sheet_name).
              경로·드라이브 폴더ID·시트ID·계정을 `workspace.toml` 로 뺀다.
              파일이 없으면 DEFAULTS(= 현행 하드코딩 값)로 동작하므로 무설정도 안전.

소비 규약: 상위로 `.claude` 앵커를 탐색해 `lib` 를 sys.path 에 1회 insert 한 뒤
  `import eroomlib.xxx`. 무거운 단계형 도구는 CLI(JSON in/out) subprocess 로 빌린다.

`import eroomlib`(패키지)는 하위 모듈을 eager import 하지 않으므로 표준 라이브러리만 필요하다.
개별 모듈의 무거운 의존은 필요 시에만 든다: selenium 은 webdriver 함수 안 지연 import,
requests 는 bulsaja 모듈 최상단 import(그 모듈을 import 할 때만 필요).
"""

__all__ = ["gsheets", "webdriver", "bulsaja", "textnorm", "envload", "config", "runner"]
