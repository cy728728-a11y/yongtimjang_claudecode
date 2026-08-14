# 불사자 카테고리 교정 스킬 — 배포본 (Aside 적용판 · 2026-08-11)

불사자 상품의 잘못된/미설정 카테고리를 **네이버 정답 카테고리**로 교정하고, 결과를 구글시트에
기록하는 Claude Code 스킬 묶음입니다.

> **Aside 적용판** — 카테고리 조회 엔진이 **셀하(셀레늄)에서 Aside 브라우저로 교체된 버전**입니다.
> 셀레늄 방식은 네이버 보안프로그램에 막혀 폐기됐습니다. 따라서 **macOS 15+ 에서만 동작**하고,
> Aside 앱과 불사자 확장이 전제입니다(아래 4번). 이전 셀하 배포본과 섞어 쓰지 마세요 —
> `aside-category` 스킬이 조회를 전담하고, `sellha-category` 는 더 이상 쓰지 않습니다.

### 2026-08-09 배포본에서 바뀐 것

| 파일 | 변경 |
|---|---|
| `skills/captcha-relay/SKILL.md` | **네이버 실물 캡챠 전 구간 통과(2026-08-10 실측)** — 미검증 → 검증 완료. Aside 루틴이 죽는 3가지 원인(경로·폴더·얼어붙은 세션) 진단표와 `--match` 를 검색어 인코딩까지 넣어 좁혀야 하는 이유 추가 |
| `lib/eroomlib/gdrive.py` · `gsheets.py` | 주석의 계정 하드코딩 제거 |
| `skills/bulsaja-category-fix/references/운영-트러블슈팅-버전.md` | run-dir 경로를 `<data_root>` 표기로 정리 |
| `skills/bulsaja-category-fix/scripts/category_gate.py` | 제외카테고리 게이트 최신본 |

> **먼저 알아둘 것** — 이 스킬은 폴더 하나로 끝나지 않습니다. 공용 라이브러리(`eroomlib`) ·
> 조회 엔진 스킬(`aside-category`) · 공유 계약 문서(`_shared`)에 의존하므로, 이 배포본은
> **그 전부를 함께 담고 있습니다.** `bulsaja-category-fix` 폴더만 복사하면 `ImportError` 로
> 즉시 죽습니다.

---

## 1. 이 배포본에 든 것

```
README.md                          ← 지금 이 파일
workspace.example.toml             ← 설정 예시. workspace.toml 로 복사해 채운다
.claude/
├── lib/eroomlib/                  ★ 공용 라이브러리 (없으면 전부 ImportError)
│   ├── __init__.py   config.py    설정 1벌 (경로·폴더ID·시트ID·계정)
│   ├── gsheets.py    matrix.py    구글시트 래퍼 · 현황판(원장)
│   ├── exclusion.py  gdrive.py    제외카테고리/블랙리스트 · 드라이브 입출력
│   └── snapshot.py   bulsaja.py   상품 스냅샷 캐시 · 불사자 MCP transport
├── skills/
│   ├── bulsaja-category-fix/      ★ 본체 (SKILL.md · references/ · scripts/)
│   ├── aside-category/            ★ 카테고리 조회 엔진 (이게 없으면 전건 조회실패)
│   ├── captcha-relay/             △ 캡챠 대응 프로토콜 (권장)
│   └── _shared/                   ★ 스킬 계약 · 불사자 안전규칙
├── workflows/catfix-fanout.js     △ 대량처리 팬아웃 (Step 3a)
└── agents/fanout-worker.md        △ 팬아웃 워커 에이전트 정의
```

★ = 필수 · △ = 대량처리/캡챠 때만 필요

**포함되지 않은 것**: 원 워크스페이스의 결정 노트·설계 스펙(`40-personal/…`, `00-system/04-specs/…`).
SKILL.md 안에서 이 문서들을 가리키던 링크는 "배포본 미포함"으로 바꿔 두었습니다. 동작에는 영향 없습니다.

**개인정보**: `eroomlib/config.py` 의 기본값(드라이브 폴더ID · 시트ID · 계정 주소 · 로컬 경로)은
**전부 비워** 두었습니다. 아래 3번에서 본인 값을 채워야 동작합니다.

---

## 2. 설치

기존 Claude Code 워크스페이스가 있다면 `.claude/` 아래 내용을 **병합**하면 됩니다.
새로 시작한다면 아무 폴더나 워크스페이스 루트로 잡고 통째로 풀면 됩니다.

```bash
cd <워크스페이스 루트>
unzip bulsaja-category-fix-dist.zip -d .
```

`.claude/lib`, `.claude/skills`, `.claude/workflows`, `.claude/agents` 가 이미 있다면
**같은 이름의 파일만** 덮어쓰기 여부를 확인하세요. 특히 `.claude/lib/eroomlib/config.py` 는
기존 것이 있으면 덮어쓰지 말고 본인 값을 유지하십시오.

### Python

```bash
python3 -m venv .venv          # 3.11 이상 (tomllib 필요)
.venv/bin/pip install requests
```

셀레늄은 쓰지 않습니다. `requests` 하나면 됩니다.

---

## 3. 설정 (필수 — 안 하면 KeyError 로 멈춥니다)

```bash
cp workspace.example.toml workspace.toml
```

`workspace.toml` 을 열어 채웁니다. **`.claude` 폴더의 부모**(워크스페이스 루트)에 두어야 찾습니다.

| 항목 | 채울 값 | 어디서 얻나 |
|---|---|---|
| `[paths]` 전부 | 산출물이 쌓일 로컬 폴더 | 아무 데나. 썸네일이 그룹당 1000장 단위라 **레포 밖**을 권장 |
| `[drive] category_folder` | 그룹별 로그 시트가 생성될 드라이브 폴더 ID | 폴더 주소창 `.../folders/<여기>` |
| `[drive] blacklist_folder` | `keyword_blacklist.xlsx` 정본 폴더 ID | 위와 동일 |
| `[sheets] master_index` | 그룹 시트들의 인덱스 스프레드시트 ID | 시트 주소창 `.../spreadsheets/d/<여기>/edit` |
| `[accounts] gws` | gws CLI 로 인증한 구글 계정 | 폴더·시트를 만드는 주체 |

확인:

```bash
.venv/bin/python -c "import sys; sys.path.insert(0,'.claude/lib'); \
  from eroomlib import config; print(config.source()); print(config.load())"
```

`설정 소스` 가 `(defaults)` 로 나오면 `workspace.toml` 을 못 찾은 것입니다.
환경변수 `EROOM_WORKSPACE_TOML` 로 경로를 직접 지정할 수도 있습니다.

---

## 4. 외부 전제 — 코드로 해결 안 되는 것 5가지

하나라도 빠지면 그 단계에서 통째로 실패합니다.

| # | 전제 | 확인 방법 | 빠지면 |
|---|---|---|---|
| 1 | **Aside 브라우저** (macOS 15+ 전용) 실행 중 | `aside.com/download` · CLI 는 `~/.local/bin/aside` (다르면 `ASIDE_BIN` 환경변수) | 전건 `파싱실패` |
| 2 | Aside 에 **불사자 확장** 설치 | 카테고리는 네이버가 아니라 이 확장이 계산합니다 | 전건 `파싱실패(확장 패널 미검출)` |
| 3 | **네이버 로그인** 세션 유지 | Aside 에서 네이버 접속해 확인 | 전건 `파싱실패` |
| 4 | **불사자 MCP** 연동 (`mcp__bulsaja__*`) | Claude Code 에서 `/mcp` | 상품 조회·저장 전부 실패 |
| 5 | **gws CLI** 인증 | `gws drive files list --params '{"pageSize":1}'` | 시트 로그 기록 실패 |

> Aside 전용이라 **이 스킬은 macOS 에서만 돕니다.** 윈도우에서는 조회 엔진이 없습니다
> (구버전 셀레늄 방식은 보안프로그램에 막혀 폐기됨 — `references/운영-트러블슈팅-버전.md` 참조).

`aside repl` 은 호출당 약 120초에서 연결이 끊깁니다. 스크립트가 자동으로 ~7건씩 쪼개 돌므로
호출부는 신경 쓸 게 없지만, `결과가 비어 있다` 로 죽으면 이걸 먼저 의심하십시오.

---

## 5. 첫 실행

Claude Code 에서 자연어로 트리거합니다 (슬래시 커맨드 아님):

```
불사자 카테고리 교정해줘
```

**처음엔 3~5건으로 검증한 뒤 확대하십시오.** 이 스킬은 확신도 70% 이상이면
**승인 없이 자동 저장**하고, 저장은 **전 마켓 동시 반영**(쿠팡 포함)입니다.
소수 테스트로 정답률을 먼저 확인하는 게 안전합니다.

동작 흐름·상태값·시트 구조는 `.claude/skills/bulsaja-category-fix/SKILL.md` 가 정본입니다.
세부는 같은 폴더 `references/` 4개 문서로 나뉘어 있습니다:

| 찾는 것 | 파일 |
|---|---|
| 증거 4종 판별 기준 · 대표검색어 12규칙 | `references/대표검색어-도출.md` |
| 팬아웃 워커 실행 절차 | `references/판정-워커-프롬프트.md` |
| 저장 4단계 폴백 · 대량처리 스크립트 | `references/저장폴백-대량처리.md` |
| 조회 엔진 원리 · 트러블슈팅 · 버전 이력 | `references/운영-트러블슈팅-버전.md` |

---

## 6. 자주 나는 오류

| 증상 | 원인 | 조치 |
|---|---|---|
| `ModuleNotFoundError: eroomlib` | `.claude/lib/eroomlib/` 가 없음 | 이 배포본을 통째로 풀었는지 확인. 스크립트는 상위로 `.claude` 앵커를 찾아 `lib` 를 `sys.path` 에 넣습니다 |
| `KeyError: 설정 'sheets.master_index' 이(가) 비어 있다` | `workspace.toml` 미작성 | 3번 |
| 전건 `파싱실패` / `sellha조회실패` | Aside·확장·네이버로그인 중 하나 | 4번 표 1~3 |
| `aside CLI 를 찾지 못했다` | CLI 경로 다름 | `export ASIDE_BIN=/실제/경로/aside` |
| `RuntimeError: tomllib 이 없다` | Python 3.10 이하 | 3.11+ 로 venv 재생성 |
| gws `503` | 구글 일시 오류 | 재시도 내장. 반복되면 대상 그룹을 쪼개서 실행 |

---

## 7. 이름이 `sellha` 인 것들에 대해

파일명 `sellha.json`, 시트 열 `sellha경로`, 상태값 `sellha조회실패`, 플래그 `--skip-sellha` —
조회 엔진이 셀하에서 Aside 로 바뀐 뒤에도 **이름은 그대로 둡니다.** 기존 run-dir 의 `--resume`
로직과 시트 재개 로직이 그 이름에 물려 있어서입니다. 버그가 아닙니다.
