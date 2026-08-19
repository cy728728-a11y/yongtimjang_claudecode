#!/usr/bin/env python3
"""상품명 배치 오케스트레이터 — 파이프라인 ⑤ product-name.

마켓그룹 하나(≈1000 상품)를 받아 썸네일·카테고리·키워드 후보를 모아 청크로 내고,
Claude가 만든 상품명을 검증→시트기록→불사자 반영까지 잇는다.

흐름:
  prep   : 마켓그룹 → 상품목록 → workdata(카테고리+썸네일) → 썸네일 다운로드
           → 카테고리 프리필터 → 계단 후보 청크(candidates/chunk_*.json)
  [Claude] 청크별로 썸네일 Read + 후보 대조 → 키워드 2~5개 선택 → 상품명 조립
           → named/named_*.json
  append : name_check 검증 → 상품명 탭 append (보류/실패도 마커로 남김)
  rename : 시트 상태=생성완료 건을 불사자에 실제 반영 (--commit 없으면 미리보기)

기존 자산을 빌려 쓴다(신규 구현 없음):
  bulsaja-category-fix/scripts : collect_group.py · bulsaja_mcp.py · fetch_thumbs.py
  keyword-pick/scripts         : cat_prefilter.py · batch_candidates.py · sheet_io.py

설계: keyword-pick/references/상품명-설계결정.md + 2026-07-23 확정 6개 결정
Usage:
  python run_names.py prep   --group-id 1001115 --run-dir <R> --source-date 260712 [--limit 20]
  python run_names.py append --run-dir <R> [--dry-run]
  python run_names.py rename --run-dir <R> [--commit]
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time
from datetime import date

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", ".."))
BULSAJA_SCRIPTS = os.path.join(SKILLS_DIR, "bulsaja-category-fix", "scripts")
KEYWORD_SCRIPTS = os.path.join(SKILLS_DIR, "keyword-pick", "scripts")

sys.path.insert(0, KEYWORD_SCRIPTS)
sys.path.insert(0, BULSAJA_SCRIPTS)
sys.path.insert(0, SCRIPT_DIR)

# gws 시트 래퍼는 eroomlib.gsheets 1벌을 쓴다(구 gws_util 차용 제거).
# `.claude` 앵커(= lib/eroomlib)를 찾아 lib 를 1회 insert.
_d = SCRIPT_DIR
while _d and _d != os.path.dirname(_d):
    _lib = os.path.join(_d, "lib")
    if os.path.isdir(os.path.join(_lib, "eroomlib")):
        if _lib not in sys.path:
            sys.path.insert(0, _lib)
        break
    _d = os.path.dirname(_d)

import sheet_io  # noqa: E402  (keyword-pick 소유)
import name_check  # noqa: E402  (이 스킬 소유 — 키워드 열 파싱 공유)
import spec_match  # noqa: E402  (이 스킬 소유 — 규격어↔옵션 정합 판정)
from eroomlib import config as _cfg  # noqa: E402  (경로·폴더ID·시트ID 1벌)
from eroomlib import snapshot  # noqa: E402  (공용 상품 스냅샷 — rename 후 상품명 되쓰기)
from eroomlib import matrix  # noqa: E402  (현황판 00_진행 — 상품명 열 갱신)
import category_gate  # noqa: E402  (bulsaja-category-fix 소유 — 삭제대기 판정 1벌)

# --- 고정 설정 -------------------------------------------------------------
# 출력은 **그룹별 카테고리교정 로그 시트의 '상품명' 탭**이다(2026-07-23 결정).
# 작업 단위(마켓그룹)와 파일 단위가 일치하고, 입력(검색어(사용))과 출력이 한 파일에 모인다.
# 고정 기본 시트를 두지 않는다 — 그룹이 바뀌는데 시트가 안 바뀌면 다른 그룹 로그에 섞인다.
# 드라이브 폴더 id 는 workspace.toml 로 뺐다(배포본 대비). 없으면 DEFAULTS = 현행 값.
CATFIX_FOLDER = _cfg.cfg("drive.category_folder", required=True)
SHEET_PREFIX = _cfg.cfg("naming.group_sheet", "카테고리교정_{group}").split("{")[0]
NAME_TAB = "상품명"
# 카테고리 교정이 기록하는 데이터 탭(A 상품id … J 실물판정 K 썸네일URL). 상품명 탭과 다르다.
# collect_targets.py·sheet_log.py 와 같은 기본값 '시트1' 을 쓴다.
CATFIX_TAB = "시트1"
# 2026-07-24: 키워드별 상품수·검색량을 남긴다(이룸님 요구). 나중에 어떤 키워드가 먹혔는지
# 되짚으려면 선택 당시의 좌표가 있어야 한다 — 통다운은 매번 갱신되므로 사후 복원이 안 된다.
# 같은 날 후속: term 목표를 6~7로 올리며 키워드를 5개까지 붙이게 돼 키워드4·5 열을 추가.
MAX_KW_COLS = 5
NAME_HEADER = (
    ["상품id", "작업일", "마켓그룹", "카테고리", "원본상품명", "새상품명"]
    + [f"키워드{i}{suf}" for i in range(1, MAX_KW_COLS + 1)
       for suf in ("", "_상품수", "_검색량")]
    + ["term분해", "term수", "중복어", "반증", "상태", "메모"]
    # 2026-07-27: term 7 상한에 밀린 검증 키워드를 폐기하지 않고 여기 남긴다(SKILL.md §3-6).
    # 불사자 MCP에 속성·태그 저장 API가 없어 자동 반영은 불가 — 이룸님이 스마트스토어
    # 센터에서 직접 입력하는 용도다. 기존 27열 뒤에 붙였으므로 앞 열의 위치는 그대로다.
    + ["속성제안", "태그제안"]
    # 2026-08-05: 규격어 키워드(`3단서빙카트`)를 쓸 때 그 규격에 해당하는 판매행을
    # 지정한다 — `<판매행id> | <근거키워드>`. 옵션정리(`run_options.read_spec_main`)가
    # 읽어 대표옵션으로 세운다. 최저가가 아니어도 수용한다.
    # 비어 있으면 지정 없음 = 종전대로 최저가가 대표.
    + ["대표지정"]
)

# 관련어 탭 — 채택하지 않은 것까지 남긴다. 재검수의 근거이자 "안 본 것"과
# "보고 버린 것"을 구분하는 유일한 기록이다(2026-07-24 결정).
REL_TAB = "관련어"
REL_HEADER = ["상품id", "작업일", "카테고리", "관련어", "상품수", "검색량", "채택", "사유"]

# 배치 크기 — 카테고리 1개 = 배치 1개. 단 이 수를 넘으면 쪼갠다.
# 카테고리교정 846건에서 검증된 청크 크기이고, 한 컨텍스트에서 상품을 너무 많이
# 순차 처리하면 뒤로 갈수록 앞의 판단에 끌려간다.
MAX_PER_BATCH = 10

_PROJECT_ROOT = os.path.normpath(os.path.join(SKILLS_DIR, "..", ".."))
VENV_PYTHON = os.path.join(_PROJECT_ROOT, ".venv", "Scripts", "python.exe")


def _py():
    return VENV_PYTHON if os.path.exists(VENV_PYTHON) else sys.executable


def _run(args, label, timeout=None):
    """서브 스크립트 실행. stdout은 흘려보내고, 실패 시 중단."""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        r = subprocess.run(args, env=env, capture_output=True, text=True,
                           encoding="utf-8", timeout=timeout)
    except OSError as e:
        raise RuntimeError(f"{label} 실행 실패(프로세스 시작 불가): {e}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{label} 시간 초과({timeout}s)")
    if r.stdout:
        print(r.stdout)
    if r.returncode != 0:
        if r.stderr:
            print(r.stderr, file=sys.stderr)
        raise RuntimeError(f"{label} 실패 (returncode={r.returncode})")
    if r.stderr:
        print(r.stderr, file=sys.stderr)
    return r.stdout


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _dump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _named_files(run_dir):
    """named/ 의 최종본만 돌려준다 — named_NNN.json 형식 그대로.

    워커가 남기는 중간산출물(named_NNN.chal.json, draft_*.json)이 glob 에 섞이면
    challenge 이전 스냅샷이 집계를 오염시킨다(1-1 회차에서 두 번째 재발 — 허수 실패 161).
    문서 주의가 아니라 코드로 막는다: 숫자 3자리 최종본만 잡는다.
    """
    return sorted(glob.glob(os.path.join(run_dir, "named", "named_[0-9][0-9][0-9].json")))


def _checked_files(checked_dir):
    """checked/ 의 최종본만 — _named_files 와 같은 이유(checked_NNN.chal.json 배제)."""
    return sorted(glob.glob(os.path.join(checked_dir, "checked_[0-9][0-9][0-9].json")))


def _mk_product(pid, cat, tgt_by_id, wd_by_id, jk_by_id, thumb_map):
    """배치에 실을 상품 1건. 대상에 없는 id 면 None.

    카테고리 뷰가 있든(정상 경로) 없든(무키워드 경로) 같은 모양이어야 한다 —
    워커 지시서가 이 키들을 이름으로 읽기 때문이다. 그래서 한 곳에서만 만든다.
    """
    t = tgt_by_id.get(pid)
    if not t:
        return None
    wd = wd_by_id.get(pid) or {}
    jk = jk_by_id.get(pid) or {}
    return {
        "productId": pid,
        "원본상품명": t.get("상품명", ""),
        "카테고리": cat,
        "썸네일경로": thumb_map.get(pid, ""),      # 다운로드된 로컬(K열 있으면 비어 있음)
        # 카테고리교정이 넘긴 증거 — J열 있으면 믿고, 없으면 원문명·옵션명으로 직접 판정
        "실물판정": jk.get("실물판정", ""),          # J열. 있으면 이게 실물
        "썸네일URL": jk.get("썸네일URL", ""),        # K열. 로컬 없을 때 여기서 fetch
        "원문명": wd.get("원문명", ""),              # 중국어 원문(가공 전)
        "옵션명": wd.get("옵션명", []),              # 실제 판매 단위(가공 전)
        # 색상 예외 규칙(2026-07-30)의 유일한 기계적 근거 — 워커는 옵션 '가격'을
        # 볼 수 없으므로(배치의 `옵션명`은 문자열뿐) 여기서 계산해 넘긴다.
        "옵션동일가": _same_price_options(pid),
        # 옵션 전량(2026-08-05). 위 `옵션명` 은 정체판별용 앞 8개 요약이라
        # **규격을 판단할 수 없다** — 발단 사례에서 실물 라인(收碗车 11개)이 앞 8개에
        # 하나도 없어 워커가 제목의 `三层` 만 보고 3단이라 결론냈다.
        "옵션구성": _spec_view(pid),
    }


def _batch_for(run_dir, named_path):
    """named_NNN.json → 짝이 되는 batch_NNN.json 경로(없으면 "").

    R10(근거 없는 term)이 원문명·옵션명·옵션구성을 보려면 배치가 필요하다 —
    named 는 워커 산출이라 가공 전 증거를 담지 않는다. 번호가 1:1이라 이름으로 찾는다.
    """
    stem = os.path.basename(named_path)[len("named_"):]
    p = os.path.join(run_dir, "batches", "batch_" + stem)
    return p if os.path.exists(p) else ""


def _is_subseq(short, full):
    """`short` 가 `full` 에서 글자 몇 개를 뺀 것인가 (순서 유지).

    워커의 id 훼손은 **글자 누락** 형태로 나타난다 — 뒤가 잘리기도 하고
    (`…JC6QWZ2J` → `…JC6QW`) 가운데 한 글자가 빠지기도 한다
    (`…BMFQP4W` → `…BMFQ4W`). 접두 매칭만으로는 후자를 못 잡아서 부분수열로 본다.
    """
    it = iter(full)
    return all(c in it for c in short)


def _audit_named(run_dir, repair=True):
    """워커 산출물(named/)을 배치 정본(batches/) 대비 대조한다 (2026-08-15).

    옵션정리 `run_options._audit_results` 와 같은 역할인데 **상품명 축에는 없었다.**
    그래서 이번 4-1 에서 워커가 자른 id 가 감사 없이 append 를 통과해 시트 A열에
    26자 짜리가 들어갔다(옵션 축은 같은 사고가 감사에 걸려 `--commit` 이 막혔다).

    `repair=True` 면 훼손된 id 를 **같은 배치 안에서 유일하게 일치하는 진짜 id 로 고친다** —
    정본이 배치 파일이고 후보가 5건 안팎이라 유일 매칭이면 사람이 하던 판단과 같다.
    유일하지 않으면 손대지 않고 환각으로 보고한다.

    반환: (경고 리스트, 누락 여부, 고친 수).
    """
    exp = {}
    for bf in sorted(glob.glob(os.path.join(run_dir, "batches", "batch_[0-9][0-9][0-9].json"))):
        n = int(os.path.basename(bf)[6:9])
        exp[n] = {p.get("productId") for p in (_load(bf) or {}).get("products", [])
                  if p.get("productId")}
    if not exp:
        return [], False, 0        # 구형 run-dir — 대조할 정본이 없다

    warns, fixed, got, bad_num = [], 0, set(), []
    for nf in _named_files(run_dir):
        n = int(os.path.basename(nf)[6:9])
        doc = _load(nf) or {}
        n_doc = doc.get("batch", doc.get("배치"))
        if n_doc is not None and int(n_doc) != n:
            bad_num.append(f"{os.path.basename(nf)} 내부 batch={n_doc}")
        want = exp.get(n, set())
        items = doc.get("products") or []
        seen = {p.get("productId") for p in items if p.get("productId")}
        if repair and want:
            for p in items:
                pid = p.get("productId")
                if not pid or pid in want:
                    continue
                cand = [w for w in want - seen if _is_subseq(pid, w)]
                if len(cand) == 1:
                    print(f"  [감사] id 훼손 교정 {os.path.basename(nf)}: "
                          f"{pid}({len(pid)}자) → {cand[0]}")
                    p["productId"] = cand[0]
                    seen.discard(pid)
                    seen.add(cand[0])
                    fixed += 1
            if fixed:
                _dump(nf, doc)
        got |= {p.get("productId") for p in items if p.get("productId")}

    want_all = {pid for pids in exp.values() for pid in pids}
    missing = sorted(want_all - got)
    unknown = sorted(got - want_all)
    done = {n for n, pids in exp.items() if pids and pids <= got}
    miss_batches = sorted(set(exp) - done)
    if miss_batches:
        warns.append(f"미완 배치 {len(miss_batches)}개: {miss_batches[:10]}")
    if missing:
        warns.append(f"누락 상품 {len(missing)}건: {missing[:5]}")
    if unknown:
        warns.append(f"미지의 상품id {len(unknown)}건(워커 환각 — 고치지 못했다): {unknown[:5]}")
    for m in bad_num:
        warns.append(f"파일명↔내부 배치번호 불일치: {m}")
    return warns, bool(missing), fixed


def resolve_sheet(args):
    """기록 대상 스프레드시트 id를 확정한다.

    --sheet 를 직접 준 경우 그대로, 아니면 --group-name 으로 카테고리교정 폴더에서
    '카테고리교정_<그룹명>' 시트를 찾는다. 못 찾으면 즉시 중단 —
    엉뚱한 그룹 로그에 상품명이 섞이는 것보다 멈추는 게 낫다.
    """
    if getattr(args, "sheet", None):
        return args.sheet
    group_name = (getattr(args, "group_name", "") or "").strip()
    if not group_name:
        raise RuntimeError("--sheet 또는 --group-name 중 하나는 필요합니다 "
                           "(그룹명으로 '카테고리교정_<그룹>' 시트를 찾습니다).")

    name = f"{SHEET_PREFIX}{group_name}"

    def _find(clause):
        q = f"'{CATFIX_FOLDER}' in parents and {clause} and trashed = false"
        try:
            d = sheet_io._run_gws(["drive", "files", "list", "--params",
                                   json.dumps({"q": q, "fields": "files(id,name)"},
                                              ensure_ascii=False)])
        except Exception as e:
            raise RuntimeError(f"시트 조회 실패({name}): {e}")
        return d.get("files", [])

    # 정확일치 우선. 초기에 만든 시트 중 '25-2_카테고리교정_5번_용쌤25-2' 처럼
    # 접두가 붙은 예외가 있어 못 찾으면 부분일치로 한 번 더 찾는다.
    files = _find(f"name = '{name}'") or _find(f"name contains '{name}'")
    if not files:
        raise RuntimeError(
            f"'{name}' 시트를 카테고리교정 폴더에서 찾지 못했습니다. "
            f"그룹명을 확인하거나 --sheet 로 직접 지정하세요.")
    if len(files) > 1:
        names = ", ".join(f["name"] for f in files)
        raise RuntimeError(f"'{name}' 에 걸리는 시트가 {len(files)}개입니다({names}) "
                           f"— --sheet 로 직접 지정하세요.")
    print(f"  시트: {files[0]['name']} ({files[0]['id']})")
    return files[0]["id"]


def _done_ids(sheet, tab=None):
    """상품명 탭 A열의 처리완료 id 집합. 탭이 아직 없으면 빈 집합(최초 실행)."""
    try:
        return sheet_io.read_done_ids(sheet, tab or NAME_TAB)
    except Exception as e:
        print(f"  (재개 조회 생략 — 탭 미존재로 간주: {str(e)[:80]})")
        return set()


def _redo_exempt(redo_hit, auto_redo):
    """prep 이 `redo.json` 으로 append 에 넘길 **A열 중복 면제** 목록.

    두 출처를 합친다 — 손으로 준 `--ids --redo`(`redo_hit`)와 현황판 재작업 자동 편입
    (`auto_redo`). **한쪽이 비어도 다른 쪽은 남아야 한다**: 전에는 자동 편입이 있을 때만
    파일을 써서, 현황판 flag 없는 `--ids --redo` 는 면제가 통째로 사라졌다(→ append 가
    전건 `스킵(이미처리)`, 워커 비용만 쓰고 시트 0행).
    """
    return sorted(set(redo_hit or ()) | set(auto_redo or {}))


def _fill_workdata(run_dir, workdata_path, pending, py, sleep):
    """캐시된 `workdata.json` 에 **없는 대상만** 조회해 덧붙인다.

    **왜 필요한가** (2026-08-15 용쌤2-1 3회차 실측). `workdata.json` 은 캐시 재사용이라
    거기 없는 상품id 는 뒤 단계가 통째로 못 본다 — `[4/6] 대상 0건 / 카테고리미설정 스킵
    1건` 으로 떨어지고 "카테고리 교정을 먼저 하세요"로 멈춘다. 그룹 목록 API 가 빼먹은
    17건을 `group.json` 에 손으로 넣어도 여기서 다시 막혔다(2회차 인계는 group.json 만
    넣으면 된다고 적었는데 부족했다).

    `--force` 는 전건 재수집이라 이 경로를 안 탄다. 스냅샷이 적중하면 MCP 호출은 0회다.
    """
    have = {w.get("productId") for w in _load(workdata_path)}
    miss = [p for p in pending if p.get("productId") not in have]
    if not miss:
        return
    print(f"  캐시에 없는 대상 {len(miss)}건 → 그 건만 조회해 덧붙인다: "
          + ", ".join(p["productId"] for p in miss[:3])
          + (f" 외 {len(miss) - 3}건" if len(miss) > 3 else ""))
    tmp_in = os.path.join(run_dir, "workdata_missing_in.json")
    tmp_out = os.path.join(run_dir, "workdata_missing_out.json")
    _dump(tmp_in, miss)
    _run([py, os.path.join(BULSAJA_SCRIPTS, "bulsaja_mcp.py"), "workdata",
          "--input", tmp_in, "--output", tmp_out, "--sleep", str(sleep)],
         "bulsaja_mcp.py workdata(누락분)")
    got = _load(tmp_out)
    if not got:
        print("  [경고] 누락분 조회 결과가 비었다 — 뒤 단계가 그 건을 못 본다.",
              file=sys.stderr)
        return
    _dump(workdata_path, _load(workdata_path) + got)
    print(f"  workdata.json 에 {len(got)}건 덧붙였다 (총 {len(have) + len(got)}건)")


def _merge_exempt(run_dir, exempt):
    """이번 회차 면제분을 **기존 `redo.json` 위에 합친다** (덮어쓰지 않는다).

    **왜 필요한가 — 이게 제일 비싼 결함이다** (2026-08-15 용쌤2-1 3회차 실측).
    `redo.json` 은 append 가 A열 중복 검사에서 면제할 목록이고, prep 은 현황판 재작업분을
    자동 편입(`_matrix_redo`)해 그 목록을 남긴다. 그런데 `--ids <2건>` 으로 몇 건을 덧붙이면
    `auto_redo` 가 그 2건 범위에서만 계산돼 파일이 **2건으로 덮어써졌다.** 앞서 편입된 14건이
    면제에서 빠지고 `append` 가 전부 `스킵(이미처리)` 로 버린다 — **워커 비용은 다 쓰고
    시트엔 2행만** 들어간다. `###APPEND### 총 N행` 을 세지 않으면 그대로 사라진다.

    **소진분(`redo.json.done`)은 다시 넣지 않는다.** append 가 이미 행을 쓴 건이라
    되살리면 같은 상품이 두 줄 들어간다. 면제는 1회용이라는 SKILL.md §prep 규칙 그대로다.
    """
    prev_path = os.path.join(run_dir, "redo.json")
    prev = set(_load(prev_path)) if os.path.exists(prev_path) else set()
    done_path = prev_path + ".done"
    done = set(_load(done_path)) if os.path.exists(done_path) else set()
    merged = sorted((set(exempt or ()) | prev) - done)
    kept = len(merged) - len(set(exempt or ()) - done)
    if kept > 0:
        print(f"  기존 면제 {kept}건을 유지한 채 합쳤다 (redo.json 총 {len(merged)}건)")
    return merged


def _read_jk_map(sheet, tab=CATFIX_TAB):
    """카테고리교정 시트에서 productId별 J(실물판정)·K(썸네일URL)을 읽는다.

    A열=상품id, J열=실물판정, K열=썸네일URL. 카테고리 교정 v1.7.0~ 이 남긴 값이다.
    구버전 그룹은 J·K가 통째로 비어 있다(그 경우 상품명 스킬이 직접 판정 후 J열을 backfill).
    시트/탭이 없으면 빈 맵(치명적이지 않음 — 증거 4종으로 직접 판정하면 된다).
    """
    if not sheet:
        return {}
    from eroomlib.gsheets import sheets_get  # noqa: E402
    try:
        rows = sheets_get(sheet, f"'{tab}'!A2:K")
    except Exception as e:
        print(f"  (카테고리 J·K 조회 생략 — {str(e)[:80]})")
        return {}
    m = {}
    for r in rows:
        r = list(r) + [""] * (11 - len(r))  # A~K = 11열
        pid = str(r[0]).strip()
        if not pid:
            continue
        # B열(교정 당시 상품명)도 함께 담는다 — `_drop_stale_jk` 가 이걸로 J열이
        # 이 상품 것이 맞는지 대조한다(2026-08-17).
        m[pid] = {"실물판정": str(r[9]).strip(), "썸네일URL": str(r[10]).strip(),
                  "시트상품명": str(r[1]).strip()}
    return m


def _bigram(s):
    """한글·영숫자만 남긴 뒤 인접 2글자 집합. 띄어쓰기·조사 차이를 흡수한다."""
    s = re.sub(r"[^가-힣A-Za-z0-9]", "", str(s or ""))
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _name_overlap(a, b):
    """두 상품명의 bigram 자카드 유사도(0~1). 한쪽이 비면 None(판정 불가)."""
    A, B = _bigram(a), _bigram(b)
    if not A or not B:
        return None
    return len(A & B) / len(A | B)


# J열을 버리는 임계. 아래로 잡을수록 "확실히 다른 것"만 버린다.
# 실측(25-2, 2294건 대조)에서 0.08 미만이 162건이었고 그 구간에 진짜 오염이 몰려 있었다.
# 0.10 은 그보다 살짝 넉넉하다 — **비대칭을 의도한 값이다**: 멀쩡한 J를 버려도
# 워커가 증거 4종으로 직접 판정하면 그만이지만(구버전 그룹이 원래 그 경로다),
# 오염된 J를 믿으면 **완전히 다른 물건의 이름**이 나간다.
JK_STALE_THRESHOLD = 0.10


def _drop_stale_jk(jk_by_id, m, threshold=JK_STALE_THRESHOLD):
    """카테고리교정 시트 J열이 **다른 상품 것**이면 버린다 (2026-08-17 25-2 실측).

    **무슨 일이 있었나.** 상품명 워커 3명이 각각 독립적으로 "J열 실물판정이 원문명·
    옵션명과 전면 상충한다"고 보고했다. 전수 대조해 보니 카테고리교정 시트의 상품명(B열)과
    현황판의 상품명이 **완전히 다른 물건**인 행이 162건이었다:

    | 상품id | 불사자 현재 | 카테고리시트 J열 |
    |---|---|---|
    | …FW9848P2C… | 모니터 받침대 | 2인용 패브릭 소파 |
    | …FW7M2BEE… | 캠핑카 테이블 다리 | 로보락 직배수 키트 |
    | …FW7BXR9B… | 접이식 사다리 | 지하수위 측정기 |

    전부 `U01KN93FW…` 대역에 몰려 있어 **상품id 재할당**으로 보인다(옛 상품이 지워지고
    그 id 가 새 상품에 다시 붙었는데, 카테고리교정 시트는 옛 기록을 그대로 들고 있다).

    **왜 위험한가.** 워커 지시서는 "J열이 있으면 그게 실물"이라는 신뢰 원칙을 두고 있다.
    그대로 따르면 모니터 받침대에 소파 이름이 붙는다. 이번엔 워커가 모순을 눈치채고
    **보류**로 뺐지만(그래서 3건이 작업 손실), 그건 워커 재량이지 장치가 아니다.

    **여기서 하는 일은 판정이 아니라 격리다.** J를 버리면 그 상품은 구버전 그룹과 같은
    경로(증거 4종으로 직접 판정)를 탈 뿐이라 손해가 없다. 지시서 쪽 방어(J열이 원문·
    옵션과 모순되면 J를 버리고 증거로 짓되 보류하지 말 것)와 이중으로 건다.

    대조축은 **현황판 `상품` 열**이다(수집 당시 이름이라 rename 후에도 안 바뀐다).
    현황판에 행이 없거나 어느 한쪽이 비면 판정하지 않고 그대로 둔다.

    반환: (걸러낸 맵, 버린 [(pid, 시트상품명, 현황판상품명)] 리스트).
    """
    if not jk_by_id or not m:
        return jk_by_id, []
    dropped = []
    for pid, v in jk_by_id.items():
        if not (v.get("실물판정") or v.get("썸네일URL")):
            continue
        rec = m.get(pid)
        if not rec:
            continue
        live = (rec.get("상품") or "").strip()
        sheet_name = (v.get("시트상품명") or "").strip()
        ov = _name_overlap(live, sheet_name)
        if ov is None or ov >= threshold:
            continue
        dropped.append((pid, sheet_name, live))
        # J·K 둘 다 버린다 — 행 자체가 다른 상품 것이므로 썸네일URL 도 못 믿는다.
        v["실물판정"] = ""
        v["썸네일URL"] = ""
        v["대조불일치"] = True
    return jk_by_id, dropped


def _backfill_jcol(sheet, tab, updates):
    """구버전 그룹의 빈 J열에 상품명 스킬이 판정한 실물을 되쓴다.

    updates = {productId: 실물판정}. 카테고리 시트 A열에서 행번호를 찾아 J{row} 한 셀만
    update 한다 — sheet_log 의 B:K 통짜 덮어쓰기와 달리 다른 열(B~I·K)을 건드리지 않는다.
    """
    if not sheet or not updates:
        return 0
    from eroomlib.gsheets import sheets_get, sheets_update  # noqa: E402
    try:
        col_a = sheets_get(sheet, f"'{tab}'!A2:A")
    except Exception as e:
        print(f"  (J열 backfill 생략 — A열 조회 실패: {str(e)[:80]})")
        return 0
    row_of = {}
    for i, r in enumerate(col_a):
        pid = str(r[0]).strip() if r else ""
        if pid and pid not in row_of:
            row_of[pid] = i + 2  # 헤더 1행
    n = 0
    for pid, ident in updates.items():
        row = row_of.get(pid)
        if not row or not str(ident).strip():
            continue
        try:
            sheets_update(sheet, f"'{tab}'!J{row}", [[ident]])
            n += 1
        except Exception as e:
            print(f"  J열 backfill 실패({pid}): {str(e)[:80]}", file=sys.stderr)
    return n


def _load_pooled_targets(path):
    """targets_<작업>.json → pending 형식([{productId, 상품명}])으로 변환.
    상품명은 빈 문자열 — 3단계 workdata(스냅샷 적중)가 실명으로 채운다."""
    data = _load(path)
    return [{"productId": t["productId"], "상품명": ""} for t in data.get("targets", [])]


def _route_by_sheet(rows_by_pid, sheet_map):
    """{pid: 행} → {sheetId: [행...]}. sheet_map 에 없거나 시트가 빈 pid 는 즉시 중단
    (조용히 다른 시트로 가면 로그 오염 — SKILL.md '못 찾으면 즉시 중단'과 같은 계약)."""
    out = {}
    for pid, row in rows_by_pid.items():
        ent = sheet_map.get(pid) or {}
        sid = (ent.get("sheet") or "").strip()
        if not sid:
            raise RuntimeError(f"sheet_map 에 시트가 없는 상품: {pid}")
        out.setdefault(sid, []).append(row)
    return out


# ---------------------------------------------------------------------------
# prep
# ---------------------------------------------------------------------------

def cmd_prep(args):
    run_dir = os.path.abspath(args.run_dir)
    os.makedirs(run_dir, exist_ok=True)
    py = _py()

    # 뷰·배치만 다시 만든다 (cat_view 규칙을 고친 뒤 재생성할 때. MCP·통다운을 다시 안 탄다)
    if getattr(args, "views_only", False):
        targets_path = os.path.join(run_dir, "targets.json")
        if not os.path.exists(targets_path):
            raise RuntimeError(f"targets.json이 없습니다({targets_path}) — prep을 먼저 돌리세요.")
        targets = _load(targets_path)
        skipped = _load(os.path.join(run_dir, "skipped.json")) \
            if os.path.exists(os.path.join(run_dir, "skipped.json")) else []
        wd_path = os.path.join(run_dir, "workdata.json")
        wd_by_id = {w.get("productId"): w for w in _load(wd_path)} \
            if os.path.exists(wd_path) else {}
        jk_path = os.path.join(run_dir, "jk_map.json")
        jk_by_id = _load(jk_path) if os.path.exists(jk_path) else {}
        print(f"[views-only] 대상 {len(targets)}건으로 뷰·배치 재생성")
        _tm = _restore_thumb_map(run_dir)
        _shrink_thumbs(_tm.values(), args.thumb_px)  # 기존 원본 썸네일도 여기서 축소된다
        _build_views_and_batches(run_dir, targets, _tm,
                                 args.no_parent, len(skipped),
                                 wd_by_id=wd_by_id, jk_by_id=jk_by_id,
                                 nokw_mode=getattr(args, 'nokw_mode', False))
        return

    targets_json = getattr(args, "targets_json", None)
    if not targets_json and not args.group_id:
        raise RuntimeError("--group-id 또는 --targets-json 중 하나는 필요합니다.")
    if targets_json and (args.group_id or args.ids or args.redo):
        # 대표는 targets 산출이 이미 미착수로 골라낸 것이라 단건 애드혹 경로(--ids/--redo)와
        # 단일 그룹 경로(--group-id)가 조용히 뒤섞이면 안 된다(피어리뷰 지적: 무시되던 결함).
        raise RuntimeError("--targets-json 은 --group-id/--ids/--redo 와 함께 쓸 수 없습니다.")

    # 현황판은 그룹 경로에서 1회만 읽는다(재작업 편입·미아 회수·삭제 게이트가 공유).
    # `--targets-json` 경로는 그룹 경계가 없어 안 읽으므로 여기서 빈 값으로 열어 둔다 —
    # 뒤쪽 `_drop_stale_jk` 가 분기 밖에서 이걸 참조한다.
    _m = {}

    group_path = os.path.join(run_dir, "group.json")
    workdata_path = os.path.join(run_dir, "workdata.json")
    targets_path = os.path.join(run_dir, "targets.json")
    thumbs_json = os.path.join(run_dir, "thumbs.json")
    thumbs_dir = os.path.join(run_dir, "thumbs")

    sheet_map = {}
    if targets_json:
        # 유니크 풀링(대량다듬기 M3b): 단계 1(collect_group)·단계 2(done_ids 대조)를
        # 건너뛴다 — 대표는 targets 산출(inventory.py targets)이 이미 미착수로 골라낸
        # 것이라 시트 재개 판정이 불필요하다. 그룹 경계가 없어 여러 그룹의 대표가
        # 한 run-dir 에 풀링된다(배치 밀도 개선, 팬아웃-비용.md).
        sheet_map_path = getattr(args, "sheet_map", None)
        if not sheet_map_path:
            raise RuntimeError("--targets-json 은 --sheet-map 과 함께 써야 합니다.")
        sheet_map = _load(sheet_map_path)
        _dump(os.path.join(run_dir, "sheet_map.json"), sheet_map)  # append가 같은 파일을 쓰도록
        pending = _load_pooled_targets(targets_json)
        if args.limit:
            pending = pending[: args.limit]
            print(f"  --limit {args.limit} 적용 → {len(pending)}건")
        print(f"[1-2/6] 유니크 풀링 대상 {len(pending)}건 (targets-json)")
        if not pending:
            print("처리할 상품이 없습니다.")
            return
        _dump(os.path.join(run_dir, "pending.json"), pending)
    else:
        # 1) 마켓그룹 → 상품목록
        if os.path.exists(group_path) and not args.force:
            print(f"[1/6] group.json 재사용 ({group_path})")
        else:
            print(f"[1/6] 마켓그룹 {args.group_id} 상품목록 수집 중...")
            _run([py, os.path.join(BULSAJA_SCRIPTS, "collect_group.py"),
                  "--group-id", str(args.group_id), "-o", group_path], "collect_group.py")
        group = _load(group_path)

        # --ids: 특정 상품만. 1건~몇 건 애드혹 작업용(신규 상품 건별 등록·보류 재작업).
        want = set()
        if args.ids:
            want = {i.strip() for i in args.ids if i.strip()}
            group = [g for g in group if g.get("productId") in want]
            print(f"  --ids {len(want)}건 지정 → 그룹에서 {len(group)}건 매칭")
            missing = want - {g.get("productId") for g in group}
            if missing:
                print(f"  [경고] 마켓그룹에 없는 상품id {len(missing)}건: {', '.join(sorted(missing))}")

        if args.limit:
            group = group[: args.limit]
            print(f"  --limit {args.limit} 적용 → {len(group)}건")

        # 2) 이미 처리된 상품 제외 (상품명 탭 A열 = 상태 저장소)
        done_ids = set() if args.no_resume else _done_ids(args.sheet, args.tab)
        # --redo: 카테고리가 바뀌어 상품명을 다시 만들어야 하는 건. A열에 이미 있어도 재대상으로 넣는다.
        # 옛 행은 지우지 않는다 — E열 원본상품명이 되돌리기 경로다(SKILL.md §재교정).
        redo_hit = set()
        if args.redo:
            if not want:
                print("[중단] --redo 는 --ids 와 함께만 쓴다(전건 재작업 방지).")
                return
            redo_hit = want & done_ids
            done_ids = done_ids - want
            if redo_hit:
                print(f"  --redo: 이미 기록된 {len(redo_hit)}건을 재대상으로 넣습니다 "
                      f"→ {', '.join(sorted(redo_hit))}")
                print("  옛 `생성완료` 행은 append 가 자동으로 재작업으로 내립니다"
                      "(중복 반영 방지 — `_retire_stale_rows`).")
        # 현황판 `상품명` 열의 `재작업(옵션: …)` **자동 편입** (2026-08-06 이룸님).
        #
        # 다른 축은 현황판이 원장이라 `pending(include_redo=True)` 이 재작업을 자동으로
        # 집는데, 상품명만 원장이 `상품명` 탭이라 A열에 행이 있으면 **다시 부르는 신호가
        # 닿지 않았다** — 옵션정리가 `flag` 를 찍어도 집는 쪽이 없어 사람이 `--ids --redo`
        # 를 손으로 돌려야 했고, 안 돌리면 그냥 사라졌다.
        #
        # 현황판은 여기서 **1회만** 읽는다 — 재작업 자동 편입과 삭제대기 게이트가 같이 쓴다.
        try:
            _m = matrix.read(args.sheet)
        except Exception as e:  # noqa: BLE001
            print(f"  [경고] 현황판 읽기 실패: {str(e)[:120]}", file=sys.stderr)
            _m = {}
        auto_redo = _matrix_redo(
            args.sheet,
            _redo_candidates({g.get("productId") for g in group}, done_ids, redo_hit),
            read=lambda _s: _m)
        if auto_redo:
            done_ids = done_ids - set(auto_redo)
            _dump(os.path.join(run_dir, "redo_reasons.json"), auto_redo)
            print(f"  현황판 재작업 {len(auto_redo)}건 자동 편입 — "
                  + " · ".join(f"{p}({r[:24]})" for p, r in list(auto_redo.items())[:3])
                  + (f" 외 {len(auto_redo) - 3}건" if len(auto_redo) > 3 else ""))

        # 면제 목록은 **auto_redo 유무와 무관하게** 남긴다 (2026-08-07).
        #
        # 전에는 이 `_dump` 가 `if auto_redo:` 안에 있어서, 현황판 flag 없이 `--ids --redo`
        # 만 쓰면 redo.json 이 아예 안 만들어졌다. prep 은 대상에 넣어 워커까지 다 돌리는데
        # append 가 시트 A열을 다시 읽어 전건 `스킵(이미처리)` 로 버렸다 — **워커 비용을 다
        # 쓰고 시트에 0행**이 되고, 로그의 `###APPEND### 총 0행` 을 놓치면 조용히 사라진다
        # (3-2 재교정 11건 실측). SKILL.md 는 "면제는 1회용(append 가 redo.json 소진)"이라
        # 적혀 있었으니 문서가 맞고 코드가 틀렸다.
        exempt = _merge_exempt(run_dir, _redo_exempt(redo_hit, auto_redo))
        if exempt:
            _dump(os.path.join(run_dir, "redo.json"), exempt)

        # 그룹 목록이 빠뜨린 미아를 편입한다 (`_recover_group_orphans` 주석 참조).
        # `--ids` 로 콕 집어 준 건도 그룹에 없으면 여기서 들어온다 — 종전엔 경고만 찍고
        # "대상 0건" 으로 끝났다.
        orphans = _recover_group_orphans(group, _m, want, done_ids)
        if orphans:
            group = group + orphans
            print(f"  그룹 목록 밖 미아 {len(orphans)}건 편입 — "
                  + " · ".join(o["productId"] for o in orphans[:3])
                  + (f" 외 {len(orphans) - 3}건" if len(orphans) > 3 else ""))

        pending = [g for g in group if g.get("productId") not in done_ids]
        # 삭제대기 게이트 — A열 멱등만으로는 안 걸린다(`_drop_gone` 주석 참조).
        pending, gone = _drop_gone(pending, _m)
        if gone:
            print(f"  삭제대기·삭제완료 {len(gone)}건 제외 (현황판 게이트)")
            # 그중 `상품명` 열만 안 찍혀 회차마다 되살아나는 건을 여기서 종결시킨다.
            n_mark = _mark_gone_column(args.sheet, _m, gone)
            if n_mark:
                print(f"    └ 현황판 `상품명` 열 {n_mark}건 삭제상태 마킹 "
                      "(다음 회차 pending 에서 빠진다)")
        for g in pending:
            if g.get("productId") in auto_redo:
                g["재작업사유"] = auto_redo[g["productId"]]
        print(f"[2/6] 그룹 {len(group)}건 / 이미처리 {len(done_ids)}건 / 대상 {len(pending)}건")
        if not pending:
            print("처리할 상품이 없습니다.")
            return
        _dump(os.path.join(run_dir, "pending.json"), pending)

    # 3) workdata — 현재 카테고리 + 썸네일 (대화 밖에서 소비)
    if os.path.exists(workdata_path) and not args.force:
        print(f"[3/6] workdata.json 재사용 ({workdata_path})")
        _fill_workdata(run_dir, workdata_path, pending, py, args.sleep)
    else:
        print(f"[3/6] 카테고리·썸네일 조회 중 ({len(pending)}건, 시간 소요)...")
        # 조회는 공용 스냅샷을 먼저 본다(카테고리 교정이 이미 받아둔 그룹이면 MCP 0회).
        # --force = 캐시 무시하고 재수집 → 스냅샷도 함께 무시한다.
        _run([py, os.path.join(BULSAJA_SCRIPTS, "bulsaja_mcp.py"), "workdata",
              "--input", os.path.join(run_dir, "pending.json"),
              "--output", workdata_path, "--sleep", str(args.sleep)]
             + (["--refresh"] if args.force else []),
             "bulsaja_mcp.py workdata")
    workdata = _load(workdata_path)
    wd_by_id = {w.get("productId"): w for w in workdata}

    # 3b) 카테고리교정 시트 J·K — 실물판정·썸네일URL. 있으면 배치에 실어 재활용,
    #     없으면(구버전 그룹) 상품명 스킬이 증거 4종으로 직접 판정한다.
    #     풀링 모드는 대표가 여러 그룹 시트에 흩어져 있으므로 시트별로 조회해 합친다.
    #     --limit 이후의 pending 에 실제 등장하는 시트만 읽는다(피어리뷰 지적 —
    #     sheet_map 전체를 읽으면 --limit 파일럿에서도 최대 52시트를 다 훑게 된다).
    if sheet_map:
        pending_sids = sorted({(sheet_map.get(p["productId"]) or {}).get("sheet")
                               for p in pending} - {None, ""})
        jk_by_id = {}
        for sid in pending_sids:
            jk_by_id.update(_read_jk_map(sid, CATFIX_TAB))
    else:
        jk_by_id = _read_jk_map(args.sheet, CATFIX_TAB)
    # 상품id 재할당으로 **다른 상품 것이 된 J열**을 버린다(`_drop_stale_jk` 주석 참조).
    jk_by_id, stale = _drop_stale_jk(jk_by_id, _m)
    if stale:
        print(f"  [경고] 카테고리 J·K {len(stale)}건이 현황판 상품과 대조 불일치 — "
              "J열을 버리고 증거 4종으로 직접 판정하게 한다")
        for pid, sheet_name, live in stale[:5]:
            print(f"    {pid}  시트'{sheet_name[:24]}' ↔ 현황판'{live[:24]}'")
        if len(stale) > 5:
            print(f"    … 외 {len(stale) - 5}건")
        _dump(os.path.join(run_dir, "jk_stale.json"),
              [{"productId": p, "시트상품명": s, "현황판상품명": l} for p, s, l in stale])
    _dump(os.path.join(run_dir, "jk_map.json"), jk_by_id)
    n_ident = sum(1 for v in jk_by_id.values() if v.get("실물판정"))
    n_kurl = sum(1 for v in jk_by_id.values() if v.get("썸네일URL"))
    print(f"  카테고리 J·K: 실물판정 {n_ident}건 / 썸네일URL {n_kurl}건")

    # 4) targets.json 조립 — 카테고리 미설정은 대상에서 제외(스킵 마커로 남김)
    targets, skipped = [], []
    for g in pending:
        pid = g.get("productId")
        wd = wd_by_id.get(pid) or {}
        # 가결정 우선 — 세로 러너(onestep)가 상품 단위 게이트를 쓸 때, 카테고리는
        # 승인 전이라 불사자에 아직 저장되지 않았지만 키워드 선택은 그 값으로 해야 한다.
        # (스냅샷 `가결정카테고리`. 가로 배치에는 이 필드가 없으므로 동작 변화 없음)
        cat = (wd.get("가결정카테고리") or wd.get("기존카테고리") or "").strip()
        name = (wd.get("상품명") or g.get("상품명") or "").strip()
        if not cat or cat == "미설정":
            skipped.append({"productId": pid, "상품명": name, "사유": "카테고리미설정"})
            continue
        t = {
            "productId": pid,
            "상품명": name,
            "대표키워드": "",          # 마켓그룹 진입점에는 없음 (cat_prefilter는 카테고리만 사용)
            "카테고리": cat,
            "썸네일": (wd.get("썸네일") or [])[:1],
        }
        # 왜 다시 하는지를 워커에게 실어 보낸다 — 사유 없이 다시 시키면 같은 이름이 또 나온다.
        if g.get("재작업사유"):
            t["재작업사유"] = g["재작업사유"]
        targets.append(t)
    _dump(targets_path, targets)
    _dump(os.path.join(run_dir, "skipped.json"), skipped)
    print(f"[4/6] 대상 {len(targets)}건 / 카테고리미설정 스킵 {len(skipped)}건 -> {targets_path}")
    if not targets:
        print("카테고리가 설정된 상품이 없습니다. 카테고리 교정을 먼저 하세요.")
        return

    # 5) 썸네일 다운로드 — K열(썸네일URL)이 이미 있는 상품은 건너뛴다.
    #    신버전 그룹은 카테고리 교정이 이미 실물을 판정(J열)했으므로 썸네일은 확인용이고,
    #    필요할 때만 배치의 썸네일URL 로 받으면 된다(전건 다운로드 5~8분 절약).
    #    구버전 그룹은 K열이 비어 있어 그대로 전건 다운로드된다(직접 판정에 필요).
    thumb_items = [{"productId": t["productId"], "url": t["썸네일"][0]}
                   for t in targets
                   if t.get("썸네일")
                   and not jk_by_id.get(t["productId"], {}).get("썸네일URL")]
    _dump(thumbs_json, thumb_items)
    thumb_map = {}
    if args.skip_thumbs:
        print("[5/6] --skip-thumbs: 썸네일 다운로드 건너뜀")
    elif not thumb_items:
        print("[5/6] 썸네일 URL이 있는 상품이 없습니다.")
    else:
        print(f"[5/6] 썸네일 {len(thumb_items)}장 다운로드 중...")
        os.makedirs(thumbs_dir, exist_ok=True)
        # 축소는 fetch_thumbs 쪽에서 이미 일어난다(공용 materialize_image). `--thumb-px` 를
        # 그대로 넘겨야 `0`(원본 유지)을 지정했을 때 뜻이 뒤집히지 않는다.
        out = _run([py, os.path.join(BULSAJA_SCRIPTS, "fetch_thumbs.py"),
                    "--input", thumbs_json, "--out-dir", thumbs_dir,
                    "--max-px", str(args.thumb_px)], "fetch_thumbs.py")
        # fetch_thumbs 는 입력 순서대로 한 줄씩(성공=절대경로 / 실패='FAIL\t...') 출력한다.
        # 파일명은 productId 를 24자로 잘라 쓰므로(불사자 id는 27자) 이름 매칭이 아니라
        # 출력 줄 순서로 매핑한다.
        lines = [ln for ln in (out or "").splitlines() if ln.strip()]
        for i, ln in enumerate(lines):
            if i >= len(thumb_items) or ln.startswith("FAIL"):
                continue
            if os.path.exists(ln.strip()):
                thumb_map[thumb_items[i]["productId"]] = os.path.abspath(ln.strip())
        print(f"  로컬 확보: {len(thumb_map)}/{len(thumb_items)}장")
        _shrink_thumbs(thumb_map.values(), args.thumb_px)

    # 6) 카테고리 프리필터 + 계단 후보 청크
    raw_dir = args.raw_dir
    if not raw_dir:
        # 통다운 원본은 구글드라이브가 보관처다(2026-08-01 이관). 로컬 runs 에 있으면
        # 그대로 쓰고, 없으면 드라이브에서 캐시로 내려받는다. 레이아웃 2종
        # (`<날짜>/raw/` 또는 `<날짜>/` 바로 아래 xlsx+zip)은 resolve_raw_dir 가 흡수한다.
        # --source-date 를 안 주면 최신을 고르고 7일 규칙(낡으면 새로 받기)이 적용된다.
        from eroomlib import gdrive
        raw_dir = gdrive.resolve_raw_dir(args.source_date)
    if not os.path.isdir(raw_dir):
        raise RuntimeError(f"통다운 raw-dir가 없습니다: {raw_dir}")

    print(f"[6/7] 카테고리 프리필터 (raw-dir={raw_dir}, 통다운 스캔이라 시간 소요)...")
    pf_args = [py, os.path.join(KEYWORD_SCRIPTS, "cat_prefilter.py"),
               "--targets", targets_path, "--out-dir", run_dir, "--raw-dir", raw_dir]
    if args.zip:
        pf_args += ["--zip", args.zip]
    if not args.no_parent:
        pf_args += ["--parent-fallback"]
    _run(pf_args, "cat_prefilter.py")

    # `--ids` 는 기존 run-dir 에 몇 건을 **덧붙이는** 애드혹 경로다 — 배치를 이어붙인다.
    # (전량 prep·`--targets-json`·`--views-only` 는 종전대로 1번부터 새로 만든다.)
    _build_views_and_batches(run_dir, targets, thumb_map, args.no_parent, len(skipped),
                             wd_by_id=wd_by_id, jk_by_id=jk_by_id,
                             nokw_mode=getattr(args, 'nokw_mode', False),
                             append=bool(getattr(args, "ids", None)))


def _shrink_thumbs(paths, max_px):
    """썸네일을 긴 변 max_px 로 축소한다 (0 이하면 건너뜀). 집계만 여기서 하고
    장별 축소는 공용 `snapshot.shrink_image` 가 한다 — 네 스킬이 같은 방식을 쓴다.

    실물 정체 판별(§Step 3-1)에는 512px 로 충분하다. 이미지에 인쇄된 글자를 읽어야
    하는 판정은 더 큰 값이 필요한데, 상품명 스킬엔 그런 축이 없다.
    """
    if not max_px or max_px <= 0:
        return
    try:
        import PIL  # noqa: F401 — 없으면 축소가 전부 no-op 이므로 미리 알린다
    except ImportError:
        print("  (Pillow 없음 — 썸네일 축소 건너뜀. pip install Pillow 권장)")
        return
    done = saved = 0
    for p in list(paths):
        try:
            before = os.path.getsize(p)
            if snapshot.shrink_image(p, max_px):
                done += 1
                saved += before - os.path.getsize(p)
        except Exception as e:  # 한 장 실패가 prep 전체를 막지 않는다
            print(f"  썸네일 축소 실패({os.path.basename(p)}): {e}")
    if done:
        print(f"  썸네일 축소: {done}장 → 긴 변 {max_px}px ({saved/1e6:.1f}MB 절감)")


def _restore_thumb_map(run_dir):
    """views-only 재실행용 — thumbs/ 파일명(productId 앞 24자)으로 매핑을 복원한다."""
    thumbs_json = os.path.join(run_dir, "thumbs.json")
    thumbs_dir = os.path.join(run_dir, "thumbs")
    if not (os.path.exists(thumbs_json) and os.path.isdir(thumbs_dir)):
        return {}
    files = {}
    for fn in os.listdir(thumbs_dir):
        files[os.path.splitext(fn)[0]] = os.path.abspath(os.path.join(thumbs_dir, fn))
    out = {}
    for item in _load(thumbs_json):
        pid = item.get("productId", "")
        for stem, path in files.items():
            if pid.startswith(stem) or stem.startswith(pid[:24]):
                out[pid] = path
                break
    return out


def _same_price_options(pid, load=None):
    """판매 옵션이 **전부 같은 가격**인가 — 색상 예외 규칙(2026-07-30 이룸님)의 근거.

    이룸님 규칙: 옵션이 전부 추가금 0원이고 색상만 다르면 상품명에 컬러명을 안 넣어도 된다
    (대표옵션의 색은 썸네일이 보여주므로 대표상품 지칭이 깨지지 않는다).
    그런데 **워커는 이걸 판단할 수 없다** — 배치의 `옵션명`은 문자열 리스트뿐이고 가격이 없다
    (`snapshot.sku_evidence` 가 `text` 만 뽑는다). 그래서 여기서 계산해 배치에 싣는다.

    옵션 전량(`옵션`)은 workdata.json 투영(`snapshot.WD_FIELDS`)에서 파일 비대 때문에
    일부러 빠져 있다 → 스냅샷 레코드를 직접 읽는다(설계상 의도된 경로).

    보수적으로 판정한다 — 판매 가능한 행이 2개 미만이거나 가격이 하나라도 비면 False.
    (구분할 대상이 없거나 근거가 불완전하면 색상을 생략할 이유가 없다.)

    `load` 는 테스트 주입점(기본 `snapshot.load`).
    """
    if load is None:
        load = snapshot.load
    try:
        rec = load(pid) or {}
    except Exception:  # noqa: BLE001  스냅샷이 없거나 깨져도 prep 을 멈추지 않는다
        return False
    rows = [r for r in ((rec.get("옵션") or {}).get("판매행") or [])
            if not r.get("exclude")]
    prices = [r.get("sale_price") for r in rows]
    if len(rows) < 2 or not all(isinstance(p, (int, float)) for p in prices):
        return False
    return len(set(prices)) == 1


def _spec_view(pid, load=None):
    """규격 판단용 옵션 구성 — 축분포·가격범위·옵션 전량(원문 포함).

    `옵션명`(앞 8개 요약, `snapshot._OPT_MAX`)과 목적이 다르다. 그건 "이게 무슨 물건인가"를
    보는 증거고, 이건 "규격이 옵션을 가르는가"를 보는 재료다. 발단 사례에서 44개 중 앞
    8개가 전부 `餐车`(2층·3층 식당카트)라 실물 라인 `收碗车` 가 보이지 않았고, 워커는
    제목의 `三层` 을 상품 전체의 규격으로 읽었다.

    `_same_price_options` 와 같은 경로(스냅샷 레코드 직독)를 쓴다 — workdata 투영에는
    옵션 전량이 파일 비대 때문에 일부러 빠져 있다.
    """
    if load is None:
        load = snapshot.load
    try:
        rec = load(pid) or {}
    except Exception:  # noqa: BLE001  스냅샷이 없어도 prep 을 멈추지 않는다
        return {}
    opt = rec.get("옵션") or {}
    rows = opt.get("판매행") or []
    if not rows:
        return {}
    out = spec_match.analyze([], opt.get("차원") or [], rows,
                             상품명=rec.get("상품명", ""), 원문명=rec.get("원문명", ""))
    out.pop("규격축", None)   # 키워드는 아직 안 골랐다 — 지정은 append 단계에서 계산한다
    return out


def _next_batch_no(run_dir):
    """`batches/` 에 이미 있는 번호 다음 값 (없으면 1)."""
    hi = 0
    for bf in glob.glob(os.path.join(run_dir, "batches", "batch_[0-9][0-9][0-9].json")):
        try:
            hi = max(hi, int(os.path.basename(bf)[len("batch_"):-len(".json")]))
        except ValueError:
            continue
    return hi + 1


def _build_views_and_batches(run_dir, targets, thumb_map, no_parent, skipped_n=0,
                             wd_by_id=None, jk_by_id=None, nokw_mode=False,
                             append=False):
    """카테고리 뷰(D) 생성 + 카테고리 단위 배치.

    후보 생성기(batch_candidates)를 더 이상 쓰지 않는다 — 그 필터가 카테고리 전용어를
    죽여서 직결어가 경쟁 진입 전에 전멸했기 때문이다(2026-07-24, 상세는 SKILL.md).

    wd_by_id: workdata.json 맵(원문명·옵션명 = 가공 전 증거). jk_by_id: 카테고리교정 시트
    J·K 맵(실물판정·썸네일URL). 둘 다 배치 product dict 에 실어 상품명 스킬이 재활용한다.
    """
    wd_by_id = wd_by_id or {}
    jk_by_id = jk_by_id or {}
    manifest = _load(os.path.join(run_dir, "manifest.json"))
    print(f"[7/7] 카테고리 뷰 생성 ({len(manifest.get('categories', {}))}개)...")

    views_dir = os.path.join(run_dir, "views")
    batches_dir = os.path.join(run_dir, "batches")
    os.makedirs(views_dir, exist_ok=True)
    os.makedirs(batches_dir, exist_ok=True)

    import cat_view  # noqa: E402  (이 스킬 소유)

    tgt_by_id = {t["productId"]: t for t in targets}
    parents = manifest.get("parents", {})
    batches, view_fail = [], []

    for cat, info in sorted(manifest.get("categories", {}).items()):
        cat_xlsx = os.path.join(run_dir, info["file"].replace("/", os.sep))
        stem = os.path.splitext(os.path.basename(cat_xlsx))[0]
        view_path = os.path.join(views_dir, stem + ".txt")
        try:
            text = cat_view.render(cat_xlsx)
            with open(view_path, "w", encoding="utf-8") as f:
                f.write(text)
        except (OSError, ValueError) as e:
            view_fail.append(f"{cat}: {e}")
            continue

        # 상위 카테고리 뷰 — leaf에 직결어가 없을 때만 여는 구명줄. 항상 읽지 않는다
        parent_view = ""
        pinfo = None if no_parent else parents.get(info.get("parent") or "")
        if pinfo:
            p_xlsx = os.path.join(run_dir, pinfo["file"].replace("/", os.sep))
            p_stem = "상위_" + os.path.splitext(os.path.basename(p_xlsx))[0]
            p_path = os.path.join(views_dir, p_stem + ".txt")
            if not os.path.exists(p_path):
                try:
                    with open(p_path, "w", encoding="utf-8") as f:
                        f.write(cat_view.render(p_xlsx))
                except (OSError, ValueError):
                    p_path = ""
            parent_view = p_path

        prods = [_mk_product(pid, cat, tgt_by_id, wd_by_id, jk_by_id, thumb_map)
                 for pid in info.get("productIds", [])]
        prods = [p for p in prods if p]
        if not prods:
            continue

        # 카테고리 1개 = 배치 1개. 단 MAX_PER_BATCH 초과분은 쪼갠다
        def _kb(p):
            return f"{os.path.getsize(p) // 1024}KB" if p and os.path.exists(p) else ""

        for i in range(0, len(prods), MAX_PER_BATCH):
            batches.append({
                "카테고리": cat,
                "카테고리뷰": view_path,
                "카테고리파일": cat_xlsx,
                # 상위뷰는 leaf에 직결어가 없을 때만 여는 구명줄이고 leaf보다 훨씬 크다
                # (실측 평균 30KB · 최대 105KB) — 열기 전에 크기를 알 수 있게 적어둔다
                "상위뷰": parent_view,
                "뷰크기": {"leaf": _kb(view_path), "상위": _kb(parent_view)},
                "분할": f"{i // MAX_PER_BATCH + 1}/{(len(prods) - 1) // MAX_PER_BATCH + 1}",
                "products": prods[i:i + MAX_PER_BATCH],
            })

    # 무키워드 모드 (2026-08-06 이룸님) — 카테고리 재교정까지 소진하고도 직결어가 0인
    # 잔여분 전용. 워커는 이 플래그가 있을 때만 키워드 없이 원본 단어로 짓는다.
    # 배치에 실어 보내는 이유 = 워커 지시서는 전 라운드 공용이라 문서로 켤 수 없다.
    if nokw_mode:
        for b in batches:
            b["무키워드모드"] = True

        # ★ 뷰가 아예 없는 대상도 배치에 싣는다 (2026-08-14 이룸님).
        #   **이게 없으면 `--nokw-mode` 가 정작 제 대상에 안 걸린다.** 위 루프는
        #   `manifest.categories` 를 도는데, 통다운밖(`not_found`) 상품은 카테고리 항목
        #   자체가 만들어지지 않아 뷰도 배치도 0개가 된다 — 2-1 회차 12건이 이 구멍으로
        #   빠져 손으로 배치를 만들어야 했다. 무키워드 경로는 **뷰가 비어도 되는 규칙**
        #   (워커 지시서 §직결어가 0개일 때)이므로, 여기서 뷰 없는 배치를 만들어 준다.
        #   평상시 라운드에는 절대 만들지 않는다 — 직결어 0은 원래 카테고리 신호다(Step 5 ②).
        covered_ids = {p["productId"] for b in batches for p in b["products"]}
        rest = [_mk_product(t["productId"], t.get("카테고리", ""),
                            tgt_by_id, wd_by_id, jk_by_id, thumb_map)
                for t in targets if t["productId"] not in covered_ids]
        rest = [p for p in rest if p]
        if rest:
            # 뷰가 없어 판단이 전부 증거 읽기라 배치를 작게 쪼갠다(워커 1명당 부담 균일).
            step = max(1, MAX_PER_BATCH // 2)
            for i in range(0, len(rest), step):
                batches.append({
                    "카테고리": "(통다운밖 — 카테고리 뷰 없음)",
                    "카테고리뷰": "", "카테고리파일": "", "상위뷰": "",
                    "뷰크기": {"leaf": "", "상위": ""},
                    "분할": f"{i // step + 1}/{(len(rest) - 1) // step + 1}",
                    "무키워드모드": True,
                    "products": rest[i:i + step],
                })
            print(f"  무키워드: 뷰 없는 대상 {len(rest)}건을 배치에 실었다 "
                  f"(통다운에 그 카테고리 키워드가 0건)")

    # **번호를 이어붙인다** (2026-08-15 용쌤2-1 3회차 실측). 종전엔 항상 1부터 다시
    # 매겨서, 배치 14개가 있는 run-dir 에 `prep --ids <1건>` 을 치면 batch_001 을
    # 통째로 덮어썼다 — 거기 있던 2건이 조용히 사라진다. `###PREP### 배치 1개` 만
    # 찍히고 기존 배치를 지웠다는 말은 어디에도 없다. 인덱스도 같이 이어붙인다.
    start = _next_batch_no(run_dir) if append else 1
    if append and start > 1:
        print(f"  기존 배치 {start - 1}개를 보존하고 batch_{start:03d} 부터 이어붙인다.")
    new_index = [{"batch": f"batch_{i:03d}.json", "카테고리": b["카테고리"],
                  "상품수": len(b["products"]), "뷰": b["카테고리뷰"]}
                 for i, b in enumerate(batches, start)]
    for i, b in enumerate(batches, start):
        _dump(os.path.join(batches_dir, f"batch_{i:03d}.json"), b)

    index_path = os.path.join(run_dir, "batches_index.json")
    if append and os.path.exists(index_path):
        prev = _load(index_path)
        new_index = (prev if isinstance(prev, list) else []) + new_index
    _dump(index_path, new_index)

    covered = sum(len(b["products"]) for b in batches)
    print(f"\n###PREP### 배치 {len(batches)}개 / 대상 {len(targets)}건(배치 수록 {covered}건) / "
          f"카테고리미설정 {skipped_n}건 / 통다운밖 {len(manifest.get('not_found', []))}건")
    if view_fail:
        print(f"  뷰 생성 실패 {len(view_fail)}건:")
        for x in view_fail[:5]:
            print(f"    - {x}")
    if covered < len(targets):
        print(f"  주의: 배치에 안 실린 상품 {len(targets) - covered}건 "
              f"— 통다운에 카테고리가 없거나 뷰 생성 실패분입니다")
    print(f"  배치: {batches_dir}")
    print(f"  뷰:   {views_dir}")
    print(f"  썸네일: {os.path.join(run_dir, 'thumbs')} (배치 수록 "
          f"{sum(1 for b in batches for p in b['products'] if p.get('썸네일경로'))}건)")


# ---------------------------------------------------------------------------
# append
# ---------------------------------------------------------------------------

def _kw_stat(p, kw):
    """관련어 목록에서 그 키워드의 (상품수, 검색량)을 찾는다. 없으면 빈칸."""
    for r in p.get("관련어") or []:
        if str(r.get("키워드", "")).strip() == kw:
            return r.get("상품수", ""), r.get("검색량", "")
    return "", ""


def _spec_designation(p):
    """채택 키워드에 규격어가 있으면 그 규격의 판매행을 지정한다 → `<판매행id> | <키워드>`.

    2026-08-05 이룸님 확정. 저상품수 1순위는 그대로고, **고른 키워드에 규격어가 있을 때만**
    발동하는 조건 분기다. 규격이 옵션을 가르는 값일 때(가)만 지정하고, 전 옵션 공통이거나
    (나) 근거가 없으면(다) 지정하지 않는다 — 그러면 종전대로 최저가가 대표다.

    워커가 아니라 여기서 계산한다. 워커는 옵션 '가격'을 볼 수 없고(배치는 이름만 준다),
    규격 표기가 한/중 제각각이라(`3단`·`3층`·`三层`) 사람 눈보다 표가 정확하다.
    실패해도 append 를 멈추지 않는다 — 지정이 없으면 종전 동작이다.
    """
    pid = p.get("productId", "")
    kws = [k for k in name_check.collect_keywords(p) if k]
    if not (pid and kws):
        return ""
    try:
        rec = snapshot.load(pid) or {}
        opt = rec.get("옵션") or {}
        rows, dims = opt.get("판매행") or [], opt.get("차원") or []
        if not rows:
            return ""
        out = spec_match.analyze(kws, dims, rows,
                                 상품명=rec.get("상품명", ""), 원문명=rec.get("원문명", ""))
        for ax in out["규격축"]:
            if ax["판정"] != "가":
                continue
            # 유지 집합은 옵션정리가 정한다 — 여기선 아직 모른다. 판매 가능한 행 중
            # 최저가를 지정하고, 그 옵션이 나중에 제외되면 옵션정리가 `보류(대표충돌)` 로 세운다.
            sellable = [r for r in rows if not r.get("exclude")]
            rid = spec_match.pick_main(ax["값키"], sellable or rows)
            if rid:
                kw = next((k for k in kws if ax["규격"] in spec_match.extract(k)), ax["규격"])
                return f"{rid} | {kw}"
    except Exception as e:  # noqa: BLE001  지정 실패가 원장 기록을 막지 않는다
        print(f"  [경고] 대표지정 계산 실패({pid}): {str(e)[:100]}", file=sys.stderr)
    return ""


def _memo_with_kw1(p):
    """키워드 예외 경로면 메모 앞에 태그 + 사유를 박는다 (2026-08-05~06).

    직결어가 부족해도 원본 단어로 채워 내보내는 예외(R4)를 열었으므로, **왜 그랬는지가
    시트에서 보여야 한다.** 증빙이 디스크(named_*.json)에만 있으면 표본검수·사후 추적에서
    "확장을 안 해본 것"과 "다 해봤는데 없던 것"을 구분할 수 없다.

    `[무키워드]` 는 특히 중요하다 — 그 행은 **검색 적합도 기대값이 낮은** 상품명이라
    나중에 통다운이 갱신되면 1순위로 다시 돌려볼 대상이다.
    """
    memo = str(p.get("메모") or "").strip()
    n_kw = len(name_check.collect_keywords(p))
    if str(p.get("원본유지사유") or "").strip():
        # 원본을 그대로 둔 행 — 나중에 "왜 안 바꿨나"를 시트에서 바로 읽을 수 있어야 한다.
        tag = f"[원본유지] {str(p['원본유지사유']).strip()}"
    elif n_kw == 0 and str(p.get("무키워드사유") or "").strip():
        tag = f"[무키워드] {str(p['무키워드사유']).strip()}"
    elif n_kw == 1 and str(p.get("키워드확장") or "").strip():
        tag = f"[키워드1개] {str(p['키워드확장']).strip()}"
    else:
        return memo
    return f"{tag} | {memo}" if memo else tag


def _build_row(p, group_name):
    """named 상품 1건 -> 상품명 탭 행 (NAME_HEADER 순서)."""
    terms = p.get("term분해") or []
    if isinstance(terms, list):
        terms = " / ".join(str(t) for t in terms)
    kws = list(name_check.collect_keywords(p)) + [""] * MAX_KW_COLS
    row = [
        p.get("productId", ""),
        date.today().isoformat(),
        group_name,
        p.get("카테고리", ""),
        p.get("원본상품명", ""),
        p.get("새상품명", ""),
    ]
    for k in kws[:MAX_KW_COLS]:
        pc, sv = _kw_stat(p, k) if k else ("", "")
        row += [k, pc, sv]
    row += [
        terms,
        p.get("term수", ""),
        p.get("중복어", ""),
        str(p.get("반증", ""))[:200],
        p.get("상태", ""),
        _memo_with_kw1(p),
        _joinlist(p.get("속성제안")),
        _joinlist(p.get("태그제안")),
        p.get("대표지정") or _spec_designation(p),
    ]
    return row


def _extend_header(sheet, tab, header):
    """이미 있는 탭의 헤더가 짧으면 뒤에 빠진 열만 채운다.

    `ensure_tab` 은 탭이 없을 때만 헤더를 쓴다 — 기존 그룹 시트(27열)에 나중에 추가된
    속성제안·태그제안(28·29) 헤더가 안 생긴다. 값은 A:AC 통째로 append 되므로
    헤더만 맞춰주면 그 뒤로는 자동으로 채워진다. 앞 열은 절대 건드리지 않는다.
    """
    from eroomlib.gsheets import sheets_get, sheets_update  # noqa: E402
    try:
        cur = (sheets_get(sheet, f"'{tab}'!1:1") or [[]])[0]
    except Exception as e:
        print(f"  [경고] 헤더 확인 실패({tab}): {e} — 헤더 확장을 건너뜁니다")
        return
    if len(cur) >= len(header):
        return
    # 겹치는 구간이 다르면 열 순서가 어긋난 시트다 — 손대지 않고 사람이 보게 한다.
    if cur != header[:len(cur)]:
        print(f"  [경고] {tab} 헤더가 예상과 다릅니다(기존 {len(cur)}열). 확장하지 않습니다.")
        return
    start = _col_letter(len(cur) + 1)
    missing = header[len(cur):]
    try:
        sheets_update(sheet, f"'{tab}'!{start}1", [missing])
        print(f"  헤더 확장: {tab} +{len(missing)}열 ({', '.join(missing)})")
    except Exception as e:
        print(f"  [경고] 헤더 확장 실패({tab}): {e}")


def _joinlist(v):
    """워커가 리스트로 줄 수도, 문자열로 줄 수도 있다 — 둘 다 받는다."""
    if not v:
        return ""
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v if str(x).strip())
    return str(v)[:500]


def _build_rel_rows(p):
    """관련어 탭 행 — 채택하지 않은 것까지 전부. 재검수의 근거."""
    rows = []
    today = date.today().isoformat()
    adopted = {k for k in name_check.collect_keywords(p)}
    for r in p.get("관련어") or []:
        kw = str(r.get("키워드", "")).strip()
        if not kw:
            continue
        rows.append([
            p.get("productId", ""), today, p.get("카테고리", ""),
            kw, r.get("상품수", ""), r.get("검색량", ""),
            "O" if kw in adopted else "",
            r.get("사유", ""),
        ])
    return rows


def _mark_matrix(sheet, status_by_id):
    """현황판(00_진행)의 `상품명` 열을 상태값으로 갱신한다.

    매트릭스는 원장(상품명 탭)의 파생본이라, 실패해도 작업 결과에 영향이 없다
    (`matrix.py rebuild` 로 언제든 원장에서 다시 만든다). 그래서 예외를 삼킨다.
    """
    vals = {pid: matrix.map_name(st) for pid, st in status_by_id.items() if pid}
    if not sheet or not vals:
        return 0
    try:
        n = matrix.mark_many(sheet, "상품명", vals)
        print(f"  현황판({matrix.TAB}) 상품명: {n}칸 갱신")
        return n
    except Exception as e:  # noqa: BLE001
        print(f"  [경고] 현황판 갱신 실패: {str(e)[:120]}", file=sys.stderr)
        return 0


def _redo_candidates(group_ids, done_ids, redo_hit):
    """현황판 재작업 사유를 물어볼 후보 = 이미 상품명 탭에 행이 있는 상품.

    `redo_hit` 를 반드시 다시 더한다 (2026-08-14). `--redo` 가 바로 앞에서
    `done_ids - want` 를 하므로, 손으로 `--ids --redo` 를 친 건은 `group & done_ids`
    에서 통째로 빠진다 — **그래서 사유가 워커에 전혀 실리지 않았다.** 자동 편입과
    수동 지목이 배타적으로 동작한 셈인데, 정작 사유가 제일 필요한 건 수동 쪽이다:
    2-3 실측에서 옵션이 남긴 "대표옵션은 냉연강인데 상품명이 '스텐'" 사유가 안 실려
    재작업 라운드가 같은 이름을 그대로 다시 만들었다.

    상한은 언제나 `group_ids` 다 — `redo_hit` 는 `--ids` 를 그룹과 교집합하기 전에
    잡히므로 그룹 밖 id(다른 마켓그룹으로 옮겨간 상품 등)가 섞일 수 있는데,
    그건 어차피 `pending` 에 없어 사유를 실을 자리가 없다.
    """
    return set(group_ids) & (set(done_ids) | set(redo_hit or ()))


def _matrix_redo(sheet, candidates, read=None):
    """현황판 `상품명` 열이 `재작업(...)` 인 상품 → {상품id: 사유}. (2026-08-06 이룸님)

    `candidates` 는 **이미 상품명 탭에 행이 있는** 상품만 넘긴다 — 빈칸(신규)은 어차피
    대상이라 편입할 게 없고, 신호가 실제로 막혀 있던 자리는 이 교집합뿐이다.

    현황판을 못 읽어도 prep 을 멈추지 않는다 — 현황판은 파생물이고 원장은 상품명 탭이다.
    다만 조용히 넘어가지 않고 경고를 남긴다(못 집은 재작업이 있다는 뜻이므로).
    `read` 는 테스트 주입점(기본 `matrix.read`).
    """
    if not candidates:
        return {}
    try:
        m = (read or matrix.read)(sheet)
    except Exception as e:  # noqa: BLE001
        print(f"  [경고] 현황판 재작업 확인 실패 — 자동 편입 없이 진행합니다: "
              f"{str(e)[:120]}", file=sys.stderr)
        return {}
    return {pid: reason
            for pid, reason in matrix.redo_pending(m, "상품명").items()
            if pid in candidates}


def _recover_group_orphans(group, m, want=None, done_ids=None):
    """마켓그룹 목록에 안 잡히는데 현황판은 `상품명` 미완인 상품을 대상에 편입한다.

    **왜 필요한가 — 그룹에서 빠진 상품은 어느 회차도 안 집는다** (2026-08-17 25-2 실측).
    prep 의 대상 모집단은 `collect_group.py` 가 받아 온 그룹 목록 하나뿐이다. 그런데
    불사자 그룹 목록 API 가 **살아 있는 상품을 빠뜨리는 경우가 있다** — 25-2 에서
    현황판 `상품명` pending 54건 중 **13건이 그룹 1879건에 없었고**, 그중 12건은
    `bulsaja_product_detail` 로 조회하면 멀쩡히 존재했다(옵션·썸네일 축은 `완료`).
    prep 은 이런 건을 대상에서 조용히 뺀 뒤 `[2/6] 대상 N건` 만 찍으므로 **에러도
    경고도 없이** 회차마다 그대로 남는다. 사람이 `group.json` 에 손으로 넣어야만 뚫렸다.

    옵션정리에는 같은 성질의 회수 장치(`run_options._recover_orphans`)가 있는데
    이 축에만 없었다. 여기서 편입하면 다음 단계는 종전 경로를 그대로 탄다 —
    `_fill_workdata` 가 캐시에 없는 id 를 조회해 채우고(2026-08-15 수정), `_drop_gone`
    이 이미 삭제된 건을 걸러낸다. 즉 **이 함수는 모집단만 넓히고 판정은 안 한다.**

    편입 조건: ①현황판에 행이 있고 ②`상품명` 열이 pending(빈칸·재작업)이고
    ③그룹 목록에 없고 ④`already_gone` 이 아니다. `want`(`--ids`)가 있으면 그 안의 것만.
    `done_ids`(상품명 탭 A열)에 있는 건 제외한다 — 그쪽은 `--redo` 가 뚫는 경로다.

    반환: 편입할 상품 dict 리스트(그룹 목록과 같은 형태).
    """
    if not m:
        return []
    have = {g.get("productId") for g in group}
    done_ids = done_ids or set()
    out = []
    for pid in matrix.pending(m, "상품명"):
        if pid in have or pid in done_ids:
            continue
        if want and pid not in want:
            continue
        rec = m.get(pid) or {}
        if category_gate.already_gone(rec):
            continue
        out.append({"productId": pid,
                    "상품명": (rec.get("상품") or "").strip(),
                    "상태코드": 1, "잠금": False, "미아편입": True})
    return out


def _mark_gone_column(sheet, m, gone_ids, mark=None):
    """`_drop_gone` 이 뺀 건의 현황판 `상품명` 열에 그 삭제 상태를 되찍는다.

    **왜 필요한가 — 게이트는 막아주지만 큐를 비워주진 않는다** (2026-08-17 25-2 실측).
    제외카테고리·품목불일치로 삭제된 상품은 나머지 작업 열엔 `상품삭제(…)` 가 찍히는데
    **`상품명` 열만 빈칸·재작업인 채로 남는 경우가 있다.** `_drop_gone` 이 대상에서
    빼주므로 워커 비용은 안 새지만, 현황판 `상품명` pending 에는 계속 잡혀서
    **회차마다 "남은 일감"으로 다시 세어진다** — 25-2 에서 pending 54건 중 18건이
    이것이었고, 인계문서가 그 18건을 실제 작업량으로 적어 다음 세션을 오도했다.

    4회차 §3① 의 "삭제하고 현황판을 안 찍으면 다음 prep 이 도로 집는다"와 같은 뿌리다.
    거기서는 사람이 손으로 `matrix.mark_many` 를 돌려 막았는데, 그 수작업을 없앤다.

    찍는 값은 **다른 열에서 이미 쓰고 있는 삭제 상태를 그대로 복사한다** — 사유를 새로
    지어내지 않는다(제외카테고리·품목불일치·용팀장 지시가 서로 다른 경로다).
    `mark` 는 테스트 주입점(기본 `matrix.mark_many`).

    반환: 찍은 건수.
    """
    if not sheet or not m or not gone_ids:
        return 0
    cols = ("수집", "카테고리", "옵션", "썸네일", "상세", "지재권", "배송비", "업로드")
    dead = ("상품삭제", "삭제대기", "해당없음")
    tgt = {}
    for pid in gone_ids:
        rec = m.get(pid) or {}
        cur = (rec.get("상품명") or "").strip()
        # 되찍는 대상은 **현황판이 pending 으로 세는 값**뿐이다 = 빈칸 또는 `재작업(…)`.
        # `보류(…)`·`진행중(…)`·이미 찍힌 삭제 상태는 다른 단계나 사람이 쓴 값이라
        # 덮으면 정보가 사라진다(`matrix.pending` 과 같은 기준을 쓴다).
        if cur and not cur.startswith("재작업"):
            continue
        for c in cols:
            v = (rec.get(c) or "").strip()
            if v.startswith(dead):
                tgt[pid] = v
                break
    if not tgt:
        return 0
    (mark or matrix.mark_many)(sheet, "상품명", tgt)
    return len(tgt)


def _drop_gone(pending, m):
    """현황판이 "이 상품은 이미 없다"고 말하는 건을 대상에서 뺀다 (2026-08-15 4-1 사고).

    **왜 필요한가**: prep 의 멱등 판정은 `상품명` 탭 A열 존재 기준인데, 제외카테고리
    삭제대기 게이트는 **현황판에만** 찍힌다. 두 저장소가 어긋나 있어 A열에 행이 없는
    삭제대기 상품이 그대로 대상에 들어갔다 — 4-1 실측 **대상 227건 중 137건(60%)이
    삭제 예정 상품**이었고, 그중 93건은 rename 까지 반영됐다. 워커 비용의 절반 이상이
    지워질 상품에 쓰였다.

    판정은 `category_gate.already_gone` 1벌을 그대로 쓴다 — **7개 작업 열 중 하나라도**
    `삭제대기`·`상품삭제`·`해당없음` 이면 없는 것으로 본다. 열 하나가 덮여도 나머지가
    살아 있어 버틴다(4-1 에서 `상품명` 열이 append 로 덮인 뒤에도 `썸네일` 열로 사고를
    찾아낸 게 이 성질이다). 규칙을 여기 다시 적지 않는다 — 두 벌이 되면 어긋난다.

    반환: (남길 것, 뺀 id 리스트). 종전엔 뺀 **수**만 돌려줬는데, 호출부가
    `_mark_gone_column` 으로 현황판 `상품명` 열을 되찍으려면 id 가 필요하다
    (2026-08-17). `len()` 을 쓰면 종전 출력과 같다.
    """
    if not m:
        # 현황판을 못 읽었다 = 게이트가 통째로 안 걸린 상태다. 조용히 넘어가면 안 된다.
        print("  [경고] 현황판을 못 읽어 삭제대기 게이트를 걸지 못했습니다 — "
              "삭제 예정 상품이 대상에 섞일 수 있습니다.", file=sys.stderr)
        return pending, []
    kept, gone = [], []
    for g in pending:
        pid = g.get("productId")
        rec = m.get(pid)
        if rec and category_gate.already_gone(rec):
            gone.append(pid)
            continue
        kept.append(g)
    return kept, gone


def _handoff_flip_suspect(sheet, checked_dir, flag=None):
    """`보류(옵션뒤집힘)` 을 현황판 `옵션` 열 재작업 flag 로 넘긴다 (2026-08-06).

    수집 시점에 본품이 전부 판매제외되고 부속만 판매중인 상품은 상품명을 지을 수 없다 —
    부속 이름을 지으면 실물 오지칭(슬링랙→풋패드 사례), 본품 이름을 지으면 실판매와
    어긋난다. 복구 담당은 옵션정리(§현재 상태를 믿지 마라)이므로 현황판 flag 로 넘긴다.
    메모식 이관은 유실된다(계약 §다른 단계에 일감을 넘길 땐 현황판에 찍는다).
    `flag` 는 테스트 주입점(기본 `matrix.flag_many`).
    """
    if flag is None:
        flag = matrix.flag_many
    reasons = {}
    for cf in _checked_files(checked_dir):
        for p in _load(cf).get("products", []):
            if str(p.get("상태", "")) == "보류(옵션뒤집힘)" and p.get("productId"):
                reasons[p["productId"]] = (str(p.get("메모", "")).strip()[:80]
                                           or "본품 전부 판매제외 의심")
    if not reasons:
        return 0
    try:
        n = flag(sheet, "옵션", reasons, from_task="상품명")
        print(f"  현황판({matrix.TAB}) 옵션 재작업 flag: {n}칸 (옵션뒤집힘 의심)")
        return n
    except Exception as e:  # noqa: BLE001  flag 실패가 append 결과를 뒤엎지 않는다
        print(f"  [경고] 옵션뒤집힘 flag 실패: {str(e)[:120]}", file=sys.stderr)
        return 0


def _handoff_base_suffix(sheet, ok_ids, load=None, flag=None):
    """상품명엔 `기본형` 이 붙었는데 대표옵션명엔 없는 상품을 옵션 단계로 넘긴다.

    왜 필요한가 (2026-07-30 이룸님 결정 3·6): 마커는 신규 처리분에만 적용하고 기존
    완료건은 소급하지 않는다. 그런데 두 스킬은 각자 다른 날 돈다 — **옵션은 이미 옛
    규칙으로 끝났고 상품명만 이번에 도는 상품**이 생긴다(용쌤1-1 등 실제로 많다).
    그 상품은 상품명만 `…기본형` 이고 옵션 목록에는 그 단어가 없어 **짝이 깨진다.**
    고객이 어느 옵션이 기본인지 못 찾는다.

    그래서 현황판 `옵션` 열에 재작업 플래그만 찍는다(기존 이관 메커니즘 재사용).
    나중에 옵션명만 가볍게 보완하면 된다.

    - **append 가 아니라 rename 성공 후**에 부른다 — append 시점의 상품명은 아직 불사자
      미반영이라, rename 이 실패하면 불필요한 플래그가 남는다.
    - **옵션이 아예 없는 상품(단일상품)은 제외** — 마커를 붙일 대상이 없다.
    - 현황판은 원장의 파생본이라 실패해도 반영 결과에 영향이 없다 → 예외를 삼킨다.

    `load`·`flag` 는 테스트 주입점(기본 `snapshot.load` / `matrix.flag_many`).
    """
    if not sheet or not ok_ids:
        return 0
    if load is None:
        load = snapshot.load
    if flag is None:
        flag = matrix.flag_many
    need = {}
    for pid in ok_ids:
        try:
            rec = load(pid) or {}
        except Exception:  # noqa: BLE001
            continue
        rows = (rec.get("옵션") or {}).get("판매행") or []
        if not rows:
            continue                      # 옵션 없는 단일상품 — 보완할 대상이 없다
        main = next((r for r in rows if r.get("main_product")), None)
        if main is None:
            # 대표가 아직 안 세워짐 = 옵션 단계를 안 거쳤다. 그 단계가 오면 마커를 붙인다.
            continue
        if not str(main.get("text") or "").strip().endswith(name_check.BASE_SUFFIX):
            need[pid] = f"상품명에 {name_check.BASE_SUFFIX} 부착 — 대표옵션명 보완 필요"
    if not need:
        return 0
    try:
        n = flag(sheet, "옵션", need, from_task="상품명")
        print(f"  현황판({matrix.TAB}) 옵션 재작업 플래그: {n}칸 "
              f"(상품명에만 {name_check.BASE_SUFFIX}이 붙은 상품)")
        return n
    except Exception as e:  # noqa: BLE001
        print(f"  [경고] 옵션 이관 플래그 실패: {str(e)[:120]}", file=sys.stderr)
        return 0


def _cmd_append_pooled(args, run_dir, checked_dir):
    """--sheet-map 지정 시: 행을 상품 소속 그룹 시트로 라우팅해 append(대량다듬기 M3b).

    name_check(1단계)는 호출자가 이미 실행했다. 여기는 시트별 ensure_tab·done_ids·append·
    J backfill·현황판 갱신을 그룹 시트 단위로 되풀이한다 — 기존 단일 시트 로직과 동등하게,
    시트가 여러 개일 뿐이다. 기존 단일 시트 경로(cmd_append 본체)는 이 함수와 무관하게
    그대로 남아 있다(회귀 byte 동일 보장).
    """
    sheet_map = _load(getattr(args, "sheet_map"))
    jk_path = os.path.join(run_dir, "jk_map.json")
    jk_map = _load(jk_path) if os.path.exists(jk_path) else {}
    redo_path = os.path.join(run_dir, "redo.json")
    redo_ids = set(_load(redo_path)) if os.path.exists(redo_path) else set()

    # 전 청크 + 스킵 마커에서 pid별 (행·관련어행·실물판정·그룹명·상태) 를 먼저 모은다.
    entries = {}
    for cf in _checked_files(checked_dir):
        data = _load(cf)
        for p in data.get("products", []):
            pid = p.get("productId", "")
            if not pid:
                continue
            group_name = (sheet_map.get(pid) or {}).get("그룹명", "")
            entries[pid] = {
                "row": _build_row(p, group_name),
                "rel_rows": _build_rel_rows(p),
                "ident": str(p.get("실물판정", "")).strip(),
                "상태": p.get("상태", ""),
            }

    skip_path = os.path.join(run_dir, "skipped.json")
    skipped = _load(skip_path) if os.path.exists(skip_path) else []
    for s in skipped:
        pid = s.get("productId", "")
        if not pid or pid in entries:
            continue
        group_name = (sheet_map.get(pid) or {}).get("그룹명", "")
        r = [""] * len(NAME_HEADER)
        r[0], r[1], r[2] = pid, date.today().isoformat(), group_name
        r[4] = s.get("상품명", "")
        i_status = NAME_HEADER.index("상태")
        r[i_status] = f"스킵({s.get('사유', '')})"
        entries[pid] = {"row": r, "rel_rows": [], "ident": "", "상태": r[i_status]}

    rows_by_pid = {pid: e["row"] for pid, e in entries.items()}
    grouped = _route_by_sheet(rows_by_pid, sheet_map)

    total, rel_total = 0, 0
    backfill_by_sheet, matrix_by_sheet = {}, {}
    for sid, _rows in grouped.items():
        # sid 는 _route_by_sheet 가 strip() 한 값이다 — 여기 비교도 strip 해야
        # sheet_map 값에 공백이 섞였을 때 조용히 0건으로 걸러지지 않는다(피어리뷰 지적).
        pids_here = [pid for pid in entries
                     if ((sheet_map.get(pid) or {}).get("sheet") or "").strip() == sid]
        if not args.dry_run:
            if sheet_io.ensure_tab(sid, args.tab, NAME_HEADER):
                print(f"  탭 신설: {args.tab} ({sid})")
            else:
                _extend_header(sid, args.tab, NAME_HEADER)
            if not args.no_related and sheet_io.ensure_tab(sid, REL_TAB, REL_HEADER):
                print(f"  탭 신설: {REL_TAB} ({sid})")

        done_ids = (_done_ids(sid, args.tab) - redo_ids) if not args.dry_run else set()
        rows_final, rel_rows_final = [], []
        for pid in pids_here:
            if pid in done_ids:
                print(f"  스킵(이미처리): {pid}")
                continue
            e = entries[pid]
            if e["ident"] and not (jk_map.get(pid) or {}).get("실물판정"):
                backfill_by_sheet.setdefault(sid, {})[pid] = e["ident"]
            rows_final.append(e["row"])
            rel_rows_final += e["rel_rows"]
            matrix_by_sheet.setdefault(sid, {})[pid] = e["상태"]

        if not rows_final:
            continue
        if args.dry_run:
            print(f"--- 시트 {sid} (dry-run, {len(rows_final)}행 / 관련어 {len(rel_rows_final)}행) ---")
            for r in rows_final:
                print(json.dumps(r, ensure_ascii=False))
        else:
            total += sheet_io.append_rows(sid, args.tab, rows_final)
            if rel_rows_final and not args.no_related:
                rel_total += sheet_io.append_rows(sid, REL_TAB, rel_rows_final)
            print(f"  시트 {sid}: {len(rows_final)}행 (관련어 {len(rel_rows_final)}행)")

    if not args.dry_run:
        for sid, updates in backfill_by_sheet.items():
            n = _backfill_jcol(sid, CATFIX_TAB, updates)
            print(f"  J열 backfill: {n}/{len(updates)}건 (시트 {sid})")
        for sid, updates in matrix_by_sheet.items():
            _mark_matrix(sid, updates)
        if redo_ids:
            try:
                os.replace(redo_path, redo_path + ".done")
                print(f"  재작업 면제 소진: redo.json → redo.json.done ({len(redo_ids)}건)")
            except OSError as e:
                print(f"  [경고] redo.json 소진 실패: {e}")
        print(f"###APPEND### 총 {total}행(풀링, {len(grouped)}개 시트) / 관련어 {rel_total}행")


def cmd_append(args):
    run_dir = os.path.abspath(args.run_dir)
    named_files = _named_files(run_dir)
    if not named_files:
        print(f"named 파일이 없습니다: {os.path.join(run_dir, 'named')}")
        return

    # 0) 감사 — 워커 산출물을 배치 정본과 대조. 훼손된 id 는 고치고, 누락은 append 를 막는다.
    #    (옵션정리 apply 의 `_audit_results` 와 같은 방어선. 2026-08-15 추가)
    warns, has_missing, fixed = _audit_named(run_dir)
    for w in warns:
        print(f"  [감사] {w}")
    if fixed:
        print(f"  [감사] id 훼손 {fixed}건 교정 — named 파일을 되썼다")
    if has_missing and not getattr(args, "allow_missing", False):
        print("\n누락 상품이 있어 append 를 막는다. pending 재계산 → 재팬아웃으로 채우거나, "
              "의도된 것이면 --allow-missing.", file=sys.stderr)
        sys.exit(3)

    py = _py()
    checked_dir = os.path.join(run_dir, "checked")
    os.makedirs(checked_dir, exist_ok=True)

    # 1) 전 청크 규칙 검증
    print(f"[1/2] 규칙 검증 ({len(named_files)}청크)...")
    for nf in named_files:
        out = os.path.join(checked_dir, os.path.basename(nf).replace("named_", "checked_"))
        cmd = [py, os.path.join(SCRIPT_DIR, "name_check.py"), "--input", nf, "--output", out]
        bf = _batch_for(run_dir, nf)
        if bf:
            cmd += ["--batch", bf]
        _run(cmd, f"name_check({os.path.basename(nf)})")

    if getattr(args, "sheet_map", None):
        _cmd_append_pooled(args, run_dir, checked_dir)
        return

    # 2) 시트 append
    group_name = args.group_name or ""
    if not args.dry_run:
        if sheet_io.ensure_tab(args.sheet, args.tab, NAME_HEADER):
            print(f"  탭 신설: {args.tab}")
        else:
            _extend_header(args.sheet, args.tab, NAME_HEADER)

    if not args.dry_run and not args.no_related:
        if sheet_io.ensure_tab(args.sheet, REL_TAB, REL_HEADER):
            print(f"  탭 신설: {REL_TAB}")

    # J열 backfill 준비 — prep 때 저장한 jk_map 으로 "원래 J가 비어 있던"(구버전) 건을 안다.
    # 상품명 스킬이 직접 판정한 실물을 그 빈 J열에 되쓴다(신버전 J는 덮지 않는다).
    jk_path = os.path.join(run_dir, "jk_map.json")
    jk_map = _load(jk_path) if os.path.exists(jk_path) else {}
    backfill = {}  # {productId: 실물판정}

    # prep 이 --redo 로 넣은 건은 A열에 이미 있어도 append 해야 한다(재작업 = 새 행 추가).
    redo_path = os.path.join(run_dir, "redo.json")
    redo_ids = set(_load(redo_path)) if os.path.exists(redo_path) else set()
    if redo_ids:
        print(f"  재작업 대상 {len(redo_ids)}건 — 이미처리 판정에서 제외합니다")
        reasons_path = os.path.join(run_dir, "redo_reasons.json")
        try:
            _retire_stale_rows(args.sheet, args.tab, redo_ids,
                               _load(reasons_path) if os.path.exists(reasons_path) else {},
                               dry_run=args.dry_run)
        except Exception as e:  # noqa: BLE001  옛 행 정리 실패가 append 를 막지 않는다
            print(f"  [경고] 옛 생성완료 행 정리 실패 — rename 전에 직접 확인하세요: "
                  f"{str(e)[:120]}", file=sys.stderr)

    total, rel_total = 0, 0
    print("[2/2] 시트 append...")
    for cf in _checked_files(checked_dir):
        data = _load(cf)
        done_ids = _done_ids(args.sheet, args.tab) - redo_ids  # 직전 재조회(이중실행 방어)
        rows, rel_rows = [], []
        for p in data.get("products", []):
            pid = p.get("productId", "")
            if pid in done_ids:
                print(f"  스킵(이미처리): {pid}")
                continue
            # 구버전(J열 비었던) 건이고 이번에 실물을 판정했으면 backfill 대상
            ident = str(p.get("실물판정", "")).strip()
            if ident and not (jk_map.get(pid) or {}).get("실물판정"):
                backfill[pid] = ident
            rows.append(_build_row(p, group_name))
            rel_rows += _build_rel_rows(p)
        if not rows:
            continue
        if args.dry_run:
            print(f"--- {os.path.basename(cf)} (dry-run, {len(rows)}행 / 관련어 {len(rel_rows)}행) ---")
            for r in rows:
                print(json.dumps(r, ensure_ascii=False))
        else:
            total += sheet_io.append_rows(args.sheet, args.tab, rows)
            if rel_rows and not args.no_related:
                rel_total += sheet_io.append_rows(args.sheet, REL_TAB, rel_rows)
            print(f"  {os.path.basename(cf)}: {len(rows)}행 (관련어 {len(rel_rows)}행)")

    # 3) 스킵 마커(카테고리미설정) — 재시도 루프 차단
    skip_path = os.path.join(run_dir, "skipped.json")
    if os.path.exists(skip_path):
        skipped = _load(skip_path)
        if skipped:
            done_ids = _done_ids(args.sheet, args.tab)
            i_status = NAME_HEADER.index("상태")
            rows = []
            for s in skipped:
                if s.get("productId") in done_ids:
                    continue
                r = [""] * len(NAME_HEADER)
                r[0] = s.get("productId", "")
                r[1] = date.today().isoformat()
                r[2] = group_name
                r[4] = s.get("상품명", "")
                r[i_status] = f"스킵({s.get('사유', '')})"
                rows.append(r)
            if rows and not args.dry_run:
                total += sheet_io.append_rows(args.sheet, args.tab, rows)
                print(f"  스킵 마커: {len(rows)}행")
            elif rows:
                print(f"--- 스킵 마커 (dry-run, {len(rows)}행) ---")

    # 4) 구버전 그룹 J열 backfill (카테고리 시트에 실물판정 되쓰기)
    if backfill:
        if args.dry_run:
            print(f"--- J열 backfill (dry-run, {len(backfill)}건) ---")
            for pid, ident in list(backfill.items())[:10]:
                print(f"  {pid} → {ident}")
            if len(backfill) > 10:
                print(f"  ... 외 {len(backfill) - 10}건")
        else:
            n = _backfill_jcol(args.sheet, CATFIX_TAB, backfill)
            print(f"  J열 backfill: {n}/{len(backfill)}건 (카테고리 시트 '{CATFIX_TAB}')")

    # 5) redo 소진 — 재작업 면제는 1회용이다. 남겨두면 append 를 다시 돌릴 때
    #    같은 상품이 또 append 되어 중복 행이 생긴다(이중실행 방어가 뚫린다).
    if redo_ids and not args.dry_run:
        try:
            os.replace(redo_path, redo_path + ".done")
            print(f"  재작업 면제 소진: redo.json → redo.json.done ({len(redo_ids)}건)")
        except OSError as e:
            print(f"  [경고] redo.json 소진 실패: {e} — append 재실행 전에 직접 지우세요")

    # 6) 현황판(00_진행) 상품명 열 갱신 — 자기 열 1개만.
    #    '생성완료'는 아직 불사자 미반영이므로 완료가 아니다(rename 이 완료로 바꾼다).
    if not args.dry_run:
        _mark_matrix(args.sheet, {
            p.get("productId", ""): p.get("상태", "")
            for cf in _checked_files(checked_dir)
            for p in _load(cf).get("products", []) if p.get("productId")})
        # 6b) 옵션뒤집힘 의심 → 옵션 열 재작업 flag(옵션정리가 뒤집힘을 복구해야
        #     상품명이 가능하다 — 2026-08-06 슬링랙/풋패드 사례)
        _handoff_flip_suspect(args.sheet, checked_dir)

    if not args.dry_run:
        print(f"###APPEND### 총 {total}행 -> {args.tab} / 관련어 {rel_total}행 -> {REL_TAB}")
        print(f"  https://docs.google.com/spreadsheets/d/{args.sheet}/edit")


# ---------------------------------------------------------------------------
# rename
# ---------------------------------------------------------------------------

# 1-based 열번호 → A1 열문자(27→AA). 매트릭스도 같은 계산을 쓰므로 eroomlib 1벌에 둔다
# (2026-07-25 `chr('A'+26)='['` 버그가 났던 자리 — 두 벌로 두면 한쪽만 고쳐진다).
_col_letter = matrix._col_letter


# rename 호출 상한이 50건이고, 불사자는 배치 안에 '내 상품이 아닌 상품'이 1건이라도
# 있으면 배치 전체를 거부한다(2026-07-27 용쌤1-1: 불량 2건이 정상 98건을 같이 죽였다).
# 그래서 거부되면 청크를 잘게 쪼개 재시도하고, 1건 단위에서도 거부된 것만 불량으로 확정한다.
RENAME_SIZES = (50, 10, 1)


def _rename_cascade(targets, submit, sizes=RENAME_SIZES, log=None,
                    max_consecutive_errors=3):
    """계단식 분해 반영. 반환: (ok_ids, bad, errored).

    submit(chunk) -> (성공여부, 메시지). 예외를 던지면 통신 오류로 본다.
    거부(성공여부 False)된 청크는 더 작은 크기로 다시 던지고, 1건에서도 거부되면
    bad 로 확정한다. 예외는 errored 로 따로 모은다 — 통신 오류를 '상품삭제'로
    확정해버리면 멀쩡한 상품의 시트 상태를 망가뜨린다.

    예외도 분해한다(오류 원인이 특정 상품일 수 있고, 통째로 포기하면 그 배치는
    재실행마다 같은 자리에서 막힌다). 다만 통신 장애처럼 계속 터지는 상황에서
    재시도 폭풍이 되지 않도록, 오류가 max_consecutive_errors 회 연달아 나면
    남은 건은 호출 없이 errored 로 넘긴다(상태 보존 → 재실행에서 다시 잡힘).
    """
    ok, bad, errored = [], [], []
    state = {"consec": 0, "tripped": False}
    abort_msg = f"연속 오류 {max_consecutive_errors}회로 중단 — 미시도(재실행 대상)"

    def _emit(msg):
        if log:
            log(msg)

    def run(items, level):
        size = sizes[level]
        for i in range(0, len(items), size):
            chunk = items[i:i + size]
            if state["tripped"]:
                errored.extend((t["productId"], abort_msg) for t in chunk)
                continue
            try:
                success, msg = submit(chunk)
                is_err = False
            except Exception as e:                      # noqa: BLE001 (통신·MCP 오류 전부)
                success, msg, is_err = False, f"{type(e).__name__}: {e}", True
            if is_err:
                state["consec"] += 1
                if state["consec"] >= max_consecutive_errors:
                    state["tripped"] = True
                    _emit(f"  {abort_msg}")
            else:
                state["consec"] = 0
            if success:
                ok.extend(t["productId"] for t in chunk)
                _emit(f"  {len(chunk)}건 반영 (누적 {len(ok)})")
                continue
            # 같은 크기로 다시 던지지 않도록, 청크보다 작은 다음 단계를 고른다.
            # 차단이 걸린 직후면 더 쪼개지 않고, 실제 오류 메시지를 그대로 남긴다.
            nxt = None if state["tripped"] else next(
                (L for L in range(level + 1, len(sizes))
                 if sizes[L] < len(chunk)), None)
            if nxt is not None:
                _emit(f"  {len(chunk)}건 거부 → {sizes[nxt]}건씩 재시도: {str(msg)[:80]}")
                run(chunk, nxt)
            else:
                _emit(f"  {'오류' if is_err else '불량 확정'}: "
                      f"{chunk[0]['productId']} {str(msg)[:80]}")
                (errored if is_err else bad).extend(
                    (t["productId"], str(msg)) for t in chunk)

    if targets:
        run(targets, 0)
    return ok, bad, errored


def _build_status_col(rows, i_id, i_status, ok_ids, bad_ids):
    """상태열 전체를 메모리에서 고쳐 (2차원 값, 변경건수) 로 돌려준다.

    행 단위 update 를 수백 번 치지 않기 위해 열 하나를 통째로 write back 한다.
    대상이 아닌 행은 기존 값을 그대로 실어 보존한다(오류건 = 생성완료 유지 →
    재실행 시 다시 잡힌다. rename 은 멱등이라 재실행이 안전하다).

    바꾸는 건 상태='생성완료' 행뿐이다 — 반영 대상 선정 기준과 같게 둬야
    같은 상품id의 보류·스킵 행까지 덮어써 기록을 지우는 일이 없다.
    """
    col, changed = [], 0
    for r in rows:
        r = list(r)
        pid = str(r[i_id]).strip() if len(r) > i_id else ""
        cur = str(r[i_status]).strip() if len(r) > i_status else ""
        new = cur
        if pid and cur == "생성완료" and pid in ok_ids:
            new = "반영완료"
        elif pid and cur == "생성완료" and pid in bad_ids:
            new = "상품삭제(이룸님)"
        if new != cur:
            changed += 1
        col.append([new])
    return col, changed


def _writeback_status(sheet, tab, rows, ok_ids, bad_ids, update=None):
    """반영 결과를 상태열에 되쓴다. 반환: 변경된 행 수(실패 시 0).

    rows 는 cmd_rename 이 A2:{last} 로 읽은 그대로 — i번째가 시트 i+2행이다.
    update 는 테스트에서 갈아끼우기 위한 주입점(기본 eroomlib.gsheets.sheets_update).
    쓰기 실패로 반영 자체가 무효가 되진 않으므로 예외를 삼키고 0을 돌려준다.
    """
    if update is None:
        from eroomlib.gsheets import sheets_update as update  # noqa: E402
    i_id = NAME_HEADER.index("상품id")
    i_status = NAME_HEADER.index("상태")
    col_values, changed = _build_status_col(rows, i_id, i_status, ok_ids, bad_ids)
    if not changed:
        return 0
    letter = _col_letter(i_status + 1)
    rng = f"'{tab}'!{letter}2:{letter}{len(col_values) + 1}"
    try:
        update(sheet, rng, col_values)
    except Exception as e:  # noqa: BLE001
        print(f"  상태열 갱신 실패({rng}): {str(e)[:150]}", file=sys.stderr)
        return 0
    return changed


def cmd_check(args):
    """named 검증만 실행(append 1단계 분리) — Workflow 검증 스테이지가 부른다.

    시트를 전혀 안 건드린다 — name_check 만 돌려 checked/ 를 만들고 실패 요약을 찍는다.
    """
    run_dir = os.path.abspath(args.run_dir)
    named_files = _named_files(run_dir)
    if not named_files:
        print(f"named 파일이 없습니다: {os.path.join(run_dir, 'named')}")
        return
    py = _py()
    checked_dir = os.path.join(run_dir, "checked")
    os.makedirs(checked_dir, exist_ok=True)
    for nf in named_files:
        out = os.path.join(checked_dir, os.path.basename(nf).replace("named_", "checked_"))
        cmd = [py, os.path.join(SCRIPT_DIR, "name_check.py"), "--input", nf, "--output", out]
        bf = _batch_for(run_dir, nf)
        if bf:
            cmd += ["--batch", bf]
        _run(cmd, f"name_check({os.path.basename(nf)})")

    # named_NNN 이 지워졌는데(재팬아웃으로 배치를 포기) 옛 checked_NNN 이 남아 있으면
    # 집계에서 뺀다 — 안 그러면 지워진 배치가 영원히 실패로 잡힌다(피어리뷰 지적).
    named_stems = {os.path.basename(nf)[len("named_"):-len(".json")] for nf in named_files}
    passed, failed, fail_batches = 0, 0, []
    # 배치 수와 상품 수를 같이 찍는다 — 1-1 회차에서 "통과 390/실패 11"(배치)을
    # 상품 수로 읽어 판단을 틀렸다. 배치 목록은 재팬아웃 선정용이라 유지.
    p_pass = p_fail = p_hold = 0
    for cf in _checked_files(checked_dir):
        stem = os.path.basename(cf)[len("checked_"):-len(".json")]
        if stem not in named_stems:
            continue
        data = _load(cf)
        has_fail = False
        for p in data.get("products", []):
            st = str(p.get("상태", ""))
            if st == "검증실패":
                p_fail += 1
                has_fail = True
            elif st.startswith("보류") or st.startswith("스킵"):
                p_hold += 1
            else:
                p_pass += 1
        if has_fail:
            failed += 1
            digits = "".join(c for c in os.path.basename(cf) if c.isdigit())
            fail_batches.append(int(digits) if digits else 0)
        else:
            passed += 1
    print(f"###CHECK### 상품 통과 {p_pass} / 실패 {p_fail} / 보류 {p_hold}"
          f" · 배치 실패 {failed} / {passed + failed} / 실패배치 {fail_batches}")


def cmd_rename(args):
    """04-상품명 탭에서 상태=생성완료 건을 불사자에 실제 반영.

    --commit 없으면 대상만 출력(미리보기). rename은 50건/호출 상한.
    """
    from bulsaja_mcp import BulsajaMCP  # noqa: E402
    from eroomlib.gsheets import sheets_get  # noqa: E402

    ncol = len(NAME_HEADER)
    last = _col_letter(ncol)
    rows = sheets_get(args.sheet, f"'{args.tab}'!A2:{last}")
    i_status = NAME_HEADER.index("상태")
    i_id = NAME_HEADER.index("상품id")
    i_orig = NAME_HEADER.index("원본상품명")
    i_new = NAME_HEADER.index("새상품명")
    # --ids 지정 시 그 pid만 대상으로 좁힌다(전파가 자기 append 분만 커밋하도록 —
    # 미지정이면 필터 없이 기존 동작과 바이트 단위로 동일해야 한다).
    ids = set(getattr(args, "ids", None) or [])
    targets = []
    for r in rows:
        r = list(r) + [""] * (ncol - len(r))
        pid, orig, newname = r[i_id], r[i_orig], r[i_new]
        status = str(r[i_status]).strip()
        if not str(pid).strip() or status != "생성완료":
            continue
        if not str(newname).strip():
            continue
        if ids and str(pid).strip() not in ids:
            continue
        targets.append({"productId": str(pid).strip(),
                        "name": str(newname).strip(),
                        "원본": str(orig).strip()})

    print(f"반영 대상: {len(targets)}건 (상태=생성완료)")
    if args.limit:
        targets = targets[: args.limit]
        print(f"  --limit {args.limit} 적용 → {len(targets)}건")
    if not targets:
        return

    for t in targets[:5]:
        print(f"  {t['productId']}  {t['원본'][:28]} → {t['name']}")
    if len(targets) > 5:
        print(f"  ... 외 {len(targets) - 5}건")

    if not args.commit:
        print("\n미리보기 모드입니다. 실제 반영하려면 --commit 을 붙이세요.")
        return

    mcp = BulsajaMCP()
    mcp.open()

    def _submit(chunk):
        """청크 1개를 preview→confirm 2단계로 반영. (성공여부, 메시지)."""
        items = [{"productId": t["productId"], "name": t["name"]} for t in chunk]
        try:
            prev = mcp.call_tool("bulsaja_product_rename",
                                 {"items": items, "confirm": False})
            token = prev.get("confirmationToken")
            if not token:
                # 토큰 미발급 = 배치 거부(불량 상품 포함). 통신 오류가 아니다.
                return False, f"확인토큰 없음: {str(prev.get('message'))[:120]}"
            res = mcp.call_tool("bulsaja_product_rename",
                                {"items": items, "confirm": True,
                                 "confirmationToken": token})
            if res.get("success") is False:
                return False, str(res.get("message"))[:150]
            return True, ""
        finally:
            time.sleep(args.sleep)

    try:
        ok_ids, bad, errored = _rename_cascade(targets, _submit, log=print)
    finally:
        mcp.close()

    # 저장한 쪽이 스냅샷의 그 필드만 되쓴다 → 다음 스킬이 옛 상품명을 읽지 않는다.
    _name_by_id = {t["productId"]: t["name"] for t in targets}
    for pid in ok_ids:
        try:
            snapshot.update(pid, 상품명=_name_by_id.get(pid, ""))
        except Exception as e:  # 스냅샷 갱신 실패가 반영 결과를 뒤엎으면 안 된다
            print(f"  [경고] 스냅샷 갱신 실패({pid}): {str(e)[:80]}", file=sys.stderr)

    print(f"###RENAME### 반영 {len(ok_ids)}건 / 불량 {len(bad)}건 / 오류 {len(errored)}건")
    for pid, msg in bad:
        print(f"  불량(1건 단위에서도 거부): {pid} — {str(msg)[:100]}")
    for pid, msg in errored[:10]:
        print(f"  오류(상태 유지, 재실행 대상): {pid} — {str(msg)[:100]}", file=sys.stderr)
    if len(errored) > 10:
        print(f"  ... 외 오류 {len(errored) - 10}건", file=sys.stderr)

    # 상태열 되쓰기 — 성공=반영완료, 확정 불량=상품삭제(이룸님).
    # 오류건은 '생성완료'로 남겨 재실행에서 다시 잡히게 한다(rename 은 멱등).
    n = _writeback_status(args.sheet, args.tab, rows,
                          set(ok_ids), {pid for pid, _ in bad})
    print(f"  시트 상태열 갱신: {n}행")

    # 현황판 — 반영된 것만 완료. 불량(상품삭제)은 해당없음. 오류건은 손대지 않는다
    # (상태를 '생성완료'로 남겨 재실행에서 다시 잡히게 하는 위 원칙과 같게).
    _mark_matrix(args.sheet,
                 {**{pid: "반영완료" for pid in ok_ids},
                  **{pid: "상품삭제(이룸님)" for pid, _ in bad}})

    # 상품명엔 마커가 붙었는데 대표옵션명엔 없는 상품 → 옵션 단계로 이관(짝 복구용)
    _handoff_base_suffix(args.sheet, ok_ids)
    print(f"  https://docs.google.com/spreadsheets/d/{args.sheet}/edit")


# ---------------------------------------------------------------------------
# fix-r9 / holds / mark — 자동화 루프 보조 (2026-08-05)
# ---------------------------------------------------------------------------

def cmd_fix_r9(args):
    """R9 단독 실패를 기계 재배열(fix_r9.py) — 재팬아웃 전에 먼저 돌린다.

    R9 는 워커 재팬아웃으로 수렴하지 않고(25-2: 144→117) 규칙이 결정론적이라
    기계가 정확히 고친다(1-1 실측: 124건 교정·재검증 전건 통과·비용 0).
    """
    import fix_r9  # noqa: E402  (같은 scripts/ — 지연 임포트로 다른 커맨드에 무영향)
    fixed, _skipped = fix_r9.run(args.run_dir, commit=args.commit)
    if fixed and args.commit:
        print("재검증 필요: run_names.py check 를 다시 돌리세요.")


def _catfix_already_correct(catfix_run):
    """재교정 run-dir 의 `이미정확` pid 집합 — "카테고리는 맞다"고 판정된 것들.

    이게 무키워드 경로(③b)의 게이트다. **카테고리가 맞는데도 뷰에 직결어가 0** 이면
    재교정을 또 돌려도 안 나온다 — 통다운에 그 카테고리 키워드가 없는 것이다.
    반대로 `이미정확` 이 아닌 건(경로가 바뀐 건·합의없음 등)은 아직 카테고리 쪽에
    할 일이 남아 있으므로 무키워드로 이름부터 짓지 않는다.
    """
    p = os.path.join(os.path.abspath(catfix_run), "decisions.json")
    if not os.path.exists(p):
        print(f"  [경고] 재교정 decisions.json 없음 — 무키워드 분류 생략: {p}",
              file=sys.stderr)
        return set()
    d = _load(p)
    items = d if isinstance(d, list) else (d.get("decisions") or d.get("결정") or [])
    return {it.get("productId") for it in items
            if str(it.get("상태", "")) == "이미정확" and it.get("productId")}


def cmd_holds(args):
    """1바퀴 결과에서 보류 3종 + 스킵(카테고리미설정) pid 를 집계한다(디스크만, 시트 무관).

    Step 5 자동 서브플로(②재교정 / ③키워드부족 원본채움)의 입력이다. run-dir 이름이
    `_redo`·`_kw1` 계열이면 재진입 금지 경고를 찍는다 — 재진입은 각 1회 한정이고,
    2회째 의심·2회째 키워드부족은 종합보고로 보낸다(SKILL.md Step 5).

    `--catfix-run` 을 주면 `카테고리의심` 을 두 갈래로 **쪼개서 더 실어 보낸다**
    (원래 목록은 그대로 둔다 — 부분집합이다):
      `무키워드대상`   catfix 가 `이미정확` → ③b 무키워드 라운드로 자동 진행
      `카테고리수동큐` 그 밖 → 종합보고 (카테고리 쪽에 아직 할 일이 남았다)
    """
    run_dir = os.path.abspath(args.run_dir)
    out = {"카테고리의심": [], "실물불명": [], "키워드부족": [], "카테고리미설정": [],
           "옵션뒤집힘": []}
    key_by_status = {"보류(카테고리의심)": "카테고리의심", "보류(실물불명)": "실물불명",
                     "보류(키워드부족)": "키워드부족", "보류(옵션뒤집힘)": "옵션뒤집힘"}
    for cf in _checked_files(os.path.join(run_dir, "checked")):
        for p in _load(cf).get("products", []):
            pid = p.get("productId", "")
            k = key_by_status.get(str(p.get("상태", "")))
            if pid and k:
                out[k].append(pid)
    sk = os.path.join(run_dir, "skipped.json")
    if os.path.exists(sk):
        for it in _load(sk):
            if it.get("사유") == "카테고리미설정" and it.get("productId"):
                out["카테고리미설정"].append(it["productId"])
    for k in out:
        out[k] = sorted(set(out[k]))
    if getattr(args, "catfix_run", None):
        ok = _catfix_already_correct(args.catfix_run)
        out["무키워드대상"] = [p for p in out["카테고리의심"] if p in ok]
        out["카테고리수동큐"] = [p for p in out["카테고리의심"] if p not in ok]
    base = os.path.basename(run_dir.rstrip("/\\"))
    if "_nokw" in base:
        print("[재진입금지] 무키워드 run-dir — 여기서 또 의심이 나와도 다시 태우지 않는다.")
    elif "_redo" in base or "_kw1" in base:
        print("[재진입금지] 재진입 run-dir — 여기서 나온 의심/미설정/키워드부족은 서브플로를 "
              "다시 태우지 않고 종합보고로 보낸다.")
    print(json.dumps(out, ensure_ascii=False))


def _retire_stale_rows(sheet, tab, pids, reasons=None, dry_run=False):
    """재진입 상품의 **옛 `생성완료` 행**을 `재작업(...)` 으로 내린다 (2026-08-06).

    `rename` 은 마지막 행이 아니라 **상태=`생성완료` 인 행 전부**를 반영한다(cmd_rename).
    그래서 옛 라운드에서 만들어 두고 아직 반영 못 한 행이 남아 있으면, 재진입해 새로 지은
    이름과 옛 이름이 **둘 다** 실리고 어느 쪽이 이길지는 행 순서가 정한다.
    지금까지는 이걸 사람이 손으로 바꿔 두게 했다(prep 의 `[필수]` 안내) — 자동 재진입에서는
    사람이 없으므로 append 가 직접 내린다.

    `반영완료`·`보류`·`스킵` 행은 건드리지 않는다 — rename 대상이 아니고, E열 원본상품명이
    되돌리기 경로다. 반환: 내린 행 수.
    """
    from eroomlib.gsheets import sheets_get, sheets_update  # noqa: E402

    if not pids:
        return 0
    ncol = len(NAME_HEADER)
    rows = sheets_get(sheet, f"'{tab}'!A2:{_col_letter(ncol)}") or []
    i_id, i_status = NAME_HEADER.index("상품id"), NAME_HEADER.index("상태")
    col, n = [], 0
    for r in rows:
        r = list(r) + [""] * (ncol - len(r))
        cur = str(r[i_status]).strip()
        if str(r[i_id]).strip() in pids and cur == "생성완료":
            reason = str((reasons or {}).get(str(r[i_id]).strip()) or "재진입")[:60]
            col.append([matrix.redo_value(reason)])
            n += 1
        else:
            col.append([r[i_status]])
    if not n or dry_run:
        if n:
            print(f"--- 옛 생성완료 행 내리기 (dry-run, {n}행) ---")
        return n
    sl = _col_letter(i_status + 1)
    sheets_update(sheet, f"'{tab}'!{sl}2:{sl}{len(col) + 1}", col)
    print(f"  옛 `생성완료` 행 {n}개를 재작업으로 내렸습니다(중복 반영 방지)")
    return n


def cmd_mark(args):
    """상품명 탭에서 지정 pid들의 **마지막 행** 상태를 일괄 변경한다.

    append 는 새 행만 쓰고 rename 되쓰기는 생성완료→반영완료 전용이라, 기존 행 상태를
    바꾸는 자동 수단은 이것뿐이다. 용도: ①카테고리 재교정 저장분 `재작업(카테고리변경)`
    ②표본검수 의심 `보류(표본의심)` ③실물불명 자동삭제 `상품삭제(실물불명·자동)`.
    같은 pid 가 여러 행이면 마지막 행만 바꾼다(마지막 행이 최신 — matrix 규약과 동일).
    상태열(+--note 시 메모열)을 통째로 되쓴다 — rename 과 같은 패턴이므로 도는 동안
    그 시트의 상태열을 손으로 편집하지 않는다.
    """
    from eroomlib.gsheets import sheets_get, sheets_update  # noqa: E402

    ncol = len(NAME_HEADER)
    rows = sheets_get(args.sheet, f"'{args.tab}'!A2:{_col_letter(ncol)}")
    i_id = NAME_HEADER.index("상품id")
    i_status = NAME_HEADER.index("상태")
    i_memo = NAME_HEADER.index("메모")
    want = {str(x).strip() for x in args.ids if str(x).strip()}
    last_row = {}
    for idx, r in enumerate(rows):
        r = list(r) + [""] * (ncol - len(r))
        pid = str(r[i_id]).strip()
        if pid in want:
            last_row[pid] = idx
    missing = sorted(want - set(last_row))
    if missing:
        print(f"  [경고] 시트에 없는 상품id {len(missing)}건: "
              f"{missing[:5]}{' …' if len(missing) > 5 else ''}")
    if not last_row:
        print("###MARK### 0건 — 대상 행이 없습니다.")
        return
    hit = set(last_row.values())
    status_col, memo_col = [], []
    for idx, r in enumerate(rows):
        r = list(r) + [""] * (ncol - len(r))
        if idx in hit:
            status_col.append([args.status])
            old = str(r[i_memo]).strip()
            memo_col.append([(old + " | " if old else "") + args.note if args.note
                             else r[i_memo]])
        else:
            status_col.append([r[i_status]])
            memo_col.append([r[i_memo]])
    sl = _col_letter(i_status + 1)
    sheets_update(args.sheet, f"'{args.tab}'!{sl}2:{sl}{len(status_col) + 1}", status_col)
    if args.note:
        ml = _col_letter(i_memo + 1)
        sheets_update(args.sheet, f"'{args.tab}'!{ml}2:{ml}{len(memo_col) + 1}", memo_col)
    print(f"###MARK### {len(hit)}건 → '{args.status}'"
          + (" (메모 덧붙임)" if args.note else ""))

    # **현황판도 같이 찍는다** (2026-08-19 실측). 종전엔 `상품명` 탭만 고쳐서 두 저장소가
    # 갈렸다 — 표본검수로 뺀 3건이 탭에는 `보류(표본의심)` 인데 현황판에는 `진행중(미반영)`
    # 로 남았다. `진행중` 은 pending 이 아니라 다음 prep 이 집지도 않으므로 **영영 그 상태로
    # 굳는다.** 다음 세션은 현황판을 원장으로 읽으니 "반영 대기 중"으로 오해한다.
    # 계약(`_shared/스킬-계약.md`)도 "다른 단계에 넘기거나 상태를 바꿀 땐 현황판에 찍는다"다.
    if not getattr(args, "no_matrix", False):
        try:
            n_m = matrix.mark_many(args.sheet, "상품명",
                                   {pid: args.status for pid in last_row})
            print(f"  현황판({matrix.TAB}) 상품명: {n_m}칸 갱신")
        except Exception as e:  # noqa: BLE001
            print(f"  [경고] 현황판 갱신 실패 — 상품명 탭만 반영됐다: {str(e)[:120]}",
                  file=sys.stderr)


# ---------------------------------------------------------------------------
# status — 남은 배치 나열 + 워커 분배표 (순수 파일 glob, LLM·MCP·시트 무관)
# ---------------------------------------------------------------------------

def cmd_status(args):
    """Step 3 진행 현황 — named/ 결과가 없는 배치(= 남은 일감)를 나열한다.

    `--chunks K` 를 주면 남은 배치를 K등분해 워커별 할당표(배치 파일 경로 목록)를 찍는다.
    서브에이전트가 없는 하네스(코덱스 등)에서 배치를 독립 프로세스로 나눌 때 쓴다.
    named_NNN.json 존재 = 그 배치 완료. 겹쳐 돌려도 멱등이라 안전(§SKILL Step 3 위임).
    """
    run_dir = os.path.abspath(args.run_dir)
    batches_dir = os.path.join(run_dir, "batches")
    named_dir = os.path.join(run_dir, "named")
    batch_files = sorted(glob.glob(os.path.join(batches_dir, "batch_*.json")))
    if not batch_files:
        print(f"배치가 없습니다: {batches_dir} — prep을 먼저 돌리세요.")
        return

    def _num(path):  # batch_007.json → "007"
        return os.path.splitext(os.path.basename(path))[0].split("_")[-1]

    done, pending = [], []
    for bf in batch_files:
        n = _num(bf)
        if os.path.exists(os.path.join(named_dir, f"named_{n}.json")):
            done.append(n)
        else:
            pending.append(n)

    print(f"배치 {len(batch_files)}개 / 완료 {len(done)}개 / 남음 {len(pending)}개")
    if not pending:
        print("남은 배치가 없습니다. append 로 진행하세요.")
        return
    print("남은 배치: " + ", ".join(pending))

    if args.chunks and args.chunks > 0:
        k = min(args.chunks, len(pending))
        base, rem = divmod(len(pending), k)  # 크기 차 ≤1 균등분할
        print(f"\n--chunks {args.chunks} → {k}등분 할당표 "
              f"(워커별 배치 파일 경로 — 각 워커에 references/배치-워커-프롬프트.md와 함께 준다):")
        idx = 0
        for i in range(k):
            size = base + (1 if i < rem else 0)
            grp = pending[idx:idx + size]
            idx += size
            if not grp:
                continue
            paths = [os.path.join(batches_dir, f"batch_{n}.json") for n in grp]
            print(f"  워커{i + 1} ({len(grp)}배치 {grp[0]}~{grp[-1]}):")
            for p in paths:
                print(f"    {p}")


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="상품명 배치 오케스트레이터 (파이프라인 ⑤)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("prep", help="마켓그룹 → 썸네일·카테고리·키워드후보 청크")
    p1.add_argument("--group-id", type=int, default=None,
                    help="--targets-json 과 상호배타 — 단일 그룹 진입점")
    p1.add_argument("--targets-json", default=None,
                    help="유니크 풀링 대표 목록(targets_<작업>.json). 지정하면 --group-id 불필요"
                         "(대량다듬기 M3b)")
    p1.add_argument("--sheet-map", default=None,
                    help="--targets-json 과 함께. pid→그룹시트 매핑(sheet_map.json)")
    p1.add_argument("--run-dir", required=True)
    p1.add_argument("--source-date", default=None,
                    help="셀러라이프 통다운 YYMMDD. 생략하면 드라이브 최신 통다운을 쓰고, "
                         "7일을 넘겼거나 전체카테고리 zip 이 없으면 새로 받는다")
    p1.add_argument("--raw-dir", default=None)
    p1.add_argument("--nokw-mode", action="store_true",
                    help="무키워드 모드 — 배치에 `무키워드모드:true` 를 실어 워커가 "
                         "직결어 0개여도 원본·원문·옵션명 단어로 짓게 한다. "
                         "카테고리 재교정까지 소진한 잔여분 전용(2026-08-06)")
    p1.add_argument("--zip", default=None)
    p1.add_argument("--limit", type=int, default=None, help="상위 N건만 (파일럿용)")
    p1.add_argument("--ids", nargs="+", default=None,
                    help="특정 productId만 처리 (1건~몇 건 애드혹 작업용)")
    p1.add_argument("--redo", action="store_true",
                    help="--ids 와 함께. 시트에 이미 기록된 건도 재대상으로 (카테고리 변경 후 재작업)")
    p1.add_argument("--views-only", action="store_true",
                    help="기존 run-dir의 targets/manifest로 뷰·배치만 재생성 "
                         "(MCP·통다운 스캔을 다시 타지 않는다)")
    p1.add_argument("--no-parent", action="store_true",
                    help="상위 카테고리(2차 접두) 뷰를 만들지 않는다. leaf에 직결어가 없는 "
                         "상품의 구명줄이 사라지므로 평소엔 켜둔다")
    p1.add_argument("--sleep", type=float, default=0.3, help="workdata 호출 간격(초)")
    p1.add_argument("--skip-thumbs", action="store_true", help="썸네일 다운로드 생략")
    p1.add_argument("--thumb-px", type=int, default=512,
                    help="썸네일 긴 변 축소 px (0=원본 유지). 비전 토큰 ∝ 픽셀수")
    p1.add_argument("--no-resume", action="store_true", help="시트 기반 재개 무시(전건 처리)")
    p1.add_argument("--force", action="store_true", help="group/workdata 캐시 무시하고 재수집")
    p1.add_argument("--group-name", default="",
                    help="마켓그룹명. '카테고리교정_<그룹명>' 시트를 찾아 재개 판정에 쓴다")
    p1.add_argument("--sheet", default="", help="스프레드시트 id 직접 지정(그룹명 조회 대신)")
    p1.add_argument("--tab", default=NAME_TAB, help="기록할 탭 이름")
    p1.set_defaults(func=cmd_prep)

    p2 = sub.add_parser("append", help="named → 검증 → 상품명 탭 append")
    p2.add_argument("--run-dir", required=True)
    p2.add_argument("--group-name", default="",
                    help="마켓그룹명. 시트 '마켓그룹' 열에 쓰이고 대상 시트를 찾는 키")
    p2.add_argument("--dry-run", action="store_true")
    p2.add_argument("--no-related", action="store_true",
                    help="관련어 탭 기록을 생략한다(재검수 근거가 사라지므로 평소엔 쓰지 않는다)")
    p2.add_argument("--sheet", default="", help="스프레드시트 id 직접 지정(그룹명 조회 대신)")
    p2.add_argument("--sheet-map", default=None,
                    help="pid→그룹시트 매핑(sheet_map.json) — 지정하면 풀링 모드로 라우팅한다"
                         "(대량다듬기 M3b)")
    p2.add_argument("--tab", default=NAME_TAB, help="기록할 탭 이름")
    p2.add_argument("--allow-missing", action="store_true",
                    help="감사가 누락 상품을 잡아도 append 를 강행한다(의도된 부분 반영 전용)")
    p2.set_defaults(func=cmd_append)

    p3 = sub.add_parser("rename", help="시트 생성완료 건을 불사자에 반영")
    p3.add_argument("--run-dir", required=True)
    p3.add_argument("--commit", action="store_true", help="실제 반영(없으면 미리보기)")
    p3.add_argument("--ids", nargs="+", default=None,
                    help="지정 시 이 상품id들만 대상(전파가 자기 append 분만 커밋할 때 사용)")
    p3.add_argument("--limit", type=int, default=None)
    p3.add_argument("--sleep", type=float, default=1.0)
    p3.add_argument("--group-name", default="", help="마켓그룹명(시트 조회 키)")
    p3.add_argument("--sheet", default="", help="스프레드시트 id 직접 지정(그룹명 조회 대신)")
    p3.add_argument("--tab", default=NAME_TAB, help="기록할 탭 이름")
    p3.set_defaults(func=cmd_rename)

    p4 = sub.add_parser("status", help="남은 배치 나열 + 워커 분배표(파일 glob, 시트 무관)")
    p4.add_argument("--run-dir", required=True)
    p4.add_argument("--chunks", type=int, default=None,
                    help="남은 배치를 K등분해 워커별 배치경로 할당표를 찍는다(코덱스 등 다중 프로세스용)")
    p4.set_defaults(func=cmd_status)

    p5 = sub.add_parser("check", help="named 검증만 실행(시트 무관) — Workflow 검증 스테이지용")
    p5.add_argument("--run-dir", required=True)
    p5.set_defaults(func=cmd_check)

    p6 = sub.add_parser("fix-r9", help="R9 단독 실패 기계 재배열(기본 dry-run) — 재팬아웃 전에")
    p6.add_argument("--run-dir", required=True)
    p6.add_argument("--commit", action="store_true", help="named 제자리 저장(없으면 dry-run)")
    p6.set_defaults(func=cmd_fix_r9)

    p7 = sub.add_parser("holds", help="보류 3종+카테고리미설정 pid 집계(JSON, 시트 무관)")
    p7.add_argument("--run-dir", required=True)
    p7.add_argument("--catfix-run", help="재교정 run-dir. 주면 `카테고리의심` 을 "
                                         "`무키워드대상`(catfix=이미정확)과 `카테고리수동큐` 로 쪼갠다")
    p7.set_defaults(func=cmd_holds)

    p8 = sub.add_parser("mark", help="상품명 탭 기존 행(pid별 마지막 행)의 상태 일괄 변경")
    p8.add_argument("--ids", nargs="+", required=True)
    p8.add_argument("--status", required=True,
                    help="예: '재작업(카테고리변경)' / '보류(표본의심)' / '상품삭제(실물불명·자동)'")
    p8.add_argument("--note", default="", help="메모열 끝에 덧붙일 사유")
    p8.add_argument("--group-name", default="", help="마켓그룹명(시트 조회 키)")
    p8.add_argument("--sheet", default="", help="스프레드시트 id 직접 지정(그룹명 조회 대신)")
    p8.add_argument("--tab", default=NAME_TAB, help="기록할 탭 이름")
    p8.add_argument("--no-matrix", action="store_true",
                    help="현황판(00_진행) 갱신 생략 — 상품명 탭만 고친다")
    p8.set_defaults(func=cmd_mark)

    args = ap.parse_args()
    try:
        # dry-run 이어도 재개 판정에 시트를 읽으므로 먼저 확정한다.
        # (prep --no-resume/--views-only/--targets-json, append --sheet-map, status, check 는
        #  시트를 아예 안 읽으므로 예외 — 유니크 풀링(대량다듬기 M3b)이 후자 둘을 추가했다)
        skip_sheet = args.cmd in ("status", "check", "fix-r9", "holds") or (
            args.cmd == "prep" and (args.no_resume or args.views_only or args.targets_json)) or (
            args.cmd == "append" and getattr(args, "sheet_map", None))
        if not skip_sheet:
            args.sheet = resolve_sheet(args)
        args.func(args)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
