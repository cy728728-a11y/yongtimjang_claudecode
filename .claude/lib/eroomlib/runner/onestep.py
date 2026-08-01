#!/usr/bin/env python3
"""세로 러너 — 상품 1개 × 작업 전부. 신규 상품 건별 등록용.

**왜 이게 필요한가.** 지금 상품 1건을 카테고리·상품명·옵션까지 정리하려면 명령어 8개를
순서대로 쳐야 하고, run-dir 3개와 그룹명을 손으로 넣어야 하며, 중간에 쉬면 "어디까지 했지"를
시트 세 군데를 열어 확인해야 한다.

**이 파일이 하지 않는 것.** 자동 완주. 세 스킬 모두 계약의 `run` 단계가 스크립트가 아니라
Claude다(썸네일·중국어 원문을 보는 판단이라 규칙으로 못 쓴다). 그래서 이건 "돌려놓고
기다리는 프로그램"이 아니라 **Claude가 조종하는 진행 관리자**다. 존재 이유는 두 가지 —
① Claude가 단계 순서를 착각하지 않게 하고 ② 세션이 끊겨도 진행 상태가 파일에 남게 한다.

**게이트 모드가 설계의 핵심.** 지금은 매 단계 멈추고(`step`), 최종 목적지는 완전 자동(`none`)이다.
그 사이를 코드 재작성 없이 건너려면, 모드가 바뀌어도 *명령 시퀀스는 동일하고 멈춤 여부만*
달라져야 한다. `test_onestep.py` 가 이걸 검증한다.

설계: `00-system/04-specs/2026-07-28-헤르메스-step4-세로러너-design.md`
"""
import argparse
import json
import os
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_LIB = os.path.dirname(os.path.dirname(_HERE))
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

from eroomlib import matrix, snapshot                     # noqa: E402
from eroomlib.config import cfg, workspace_root           # noqa: E402
from eroomlib.runner import approval_log, signals         # noqa: E402

PY = sys.executable or "python"

# ---------------------------------------------------------------------------
# 게이트 모드 — 멈추는 지점만 다르다. 명령 시퀀스는 전부 같다.
# ---------------------------------------------------------------------------
GATES = ("step", "product", "risky", "none")
GATE_HELP = {
    "step":    "단계마다 저장 직전에 멈춘다 (지금 기본 — 승인하며 스킬을 깎는 단계)",
    "product": "3단계 가공을 다 모은 뒤 1번 멈춘다 (계획서 게이트①)",
    "risky":   "이상 신호가 있을 때만 멈춘다",
    "none":    "안 멈춘다 (완전 자동)",
}

# 단계 상태 — 앞으로만 간다.
TODO, PREPPED, RAN, PREVIEWED, DONE = "미착수", "prep완료", "run완료", "preview완료", "완료"
ORDER = [TODO, PREPPED, RAN, PREVIEWED, DONE]


def _skills():
    root = workspace_root()
    if not root:
        raise RuntimeError("워크스페이스 루트(.claude 를 품은 폴더)를 찾지 못했다.")
    return os.path.join(root, ".claude", "skills")


def _script(rel):
    return os.path.join(_skills(), rel)


# ---------------------------------------------------------------------------
# 단계 정의
#
# 각 단계는 계약의 prep / run / apply 를 그대로 쓴다. 스킬마다 명령어 이름이 다른 것은
# `_shared/스킬-계약.md` §기존 스킬 예외에 적힌 그대로다 — 개명하지 않고 여기서 흡수한다.
#
#   preview = 쓰기 없이 결과를 확정하는 호출(승인 자료를 만든다)
#   commit  = 불사자에 실제로 저장하는 호출
# ---------------------------------------------------------------------------

def _catfix(c, sub, *rest):
    # run_all.py 는 --sheet 가 서브커맨드 **앞**에 오는 전역 인자다.
    return [_script("bulsaja-category-fix/scripts/run_all.py"),
            "--sheet", c["sheet"], sub, "--run-dir", c["rd"], *rest]


def _pname(c, sub, *rest):
    return [_script("product-name/scripts/run_names.py"), sub,
            "--run-dir", c["rd"], "--sheet", c["sheet"],
            "--group-name", c["그룹"], *rest]


def _popt(c, sub, *rest):
    return [_script("bulsaja-option-cleanup/scripts/run_options.py"), sub,
            "--run-dir", c["rd"], "--sheet", c["sheet"], *rest]


def _thumb(c, sub, *rest):
    return [_script("bulsaja-thumbnail/scripts/run_thumbs.py"), sub,
            "--run-dir", c["rd"], "--sheet", c["sheet"], *rest]


def _detail(c, sub, *rest):
    return [_script("bulsaja-detail/scripts/run_detail.py"), sub,
            "--run-dir", c["rd"], "--sheet", c["sheet"], *rest]


STEPS = [
    {
        "name": "카테고리", "dir": "01-카테고리", "deps": [],
        "prep":    lambda c: _catfix(c, "prep", "--ids", c["pid"]),
        "run":     "names.json 의 증거 4종(상품명·원문명·옵션명·썸네일)으로 실물을 판별하고 "
                   "대표 검색어를 정해 keywords.json 을 만든다",
        "output":  "keywords.json",
        "prep_out": "names.json",
        # 재시도(force)면 셀하를 다시 태운다 — 기본은 --resume 이라 검색어를 바꿔도
        # 옛 조회 결과를 그대로 쓴다(= 고친 게 반영 안 된다).
        "preview": lambda c: _catfix(c, "finish", "--dry-run",
                                     *(["--force"] if c.get("force") else [])),
        "commit":  lambda c: _catfix(c, "finish"),
    },
    {
        "name": "상품명", "dir": "02-상품명", "deps": ["카테고리"],
        # --source-date = 셀러라이프 통다운 YYMMDD. 카테고리 키워드 후보의 원천이라
        # 없으면 prep 이 중단된다. state 에 실어 두고 매번 자동 주입한다.
        "prep":    lambda c: _pname(c, "prep", "--group-id", str(c["group_id"]),
                                    "--ids", c["pid"],
                                    *(["--source-date", c["source_date"]]
                                      if c.get("source_date") else [])),
        "run":     "batches/ 를 읽고 썸네일로 실물을 확인한 뒤 카테고리 키워드 2~3개를 골라 "
                   "상품명을 만들어 named/ 에 쓴다",
        "output":  "named/",
        "prep_out": "batches_index.json",
        "preview": lambda c: _pname(c, "append"),
        "commit":  lambda c: _pname(c, "rename", "--commit"),
    },
    {
        "name": "옵션", "dir": "03-옵션", "deps": ["카테고리"],
        "prep":    lambda c: _popt(c, "prep", "--ids", c["pid"]),
        "run":     "batches/ 를 읽고 메인상품·비상품 행을 판별한 뒤 옵션명을 지어 "
                   "results/result_NNN.json 에 쓴다",
        "output":  "results/",
        "prep_out": "batches_index.json",
        "preview": lambda c: _popt(c, "apply", "--emit",
                                   os.path.join(c["rd"], "plans.json")),
        "commit":  lambda c: _popt(c, "apply", "--commit"),
    },
    {
        # ⚠ 이 단계만 예외 — 다른 세 단계는 preview 가 순수 계산(공짜)이지만, 썸네일은
        # "무엇을 승인할지"(생성본 이미지) 자체가 실제 생성을 돌려야만 나온다. 그래서
        # preview 에서 크레딧이 든다. commit 은 그 결과를 review.html 로 본 뒤의 최종
        # 반영이다(review.html 은 이미지라 여기 검수표엔 경로만 찍힌다 — signals.py 참조).
        "name": "썸네일", "dir": "04-썸네일", "deps": ["카테고리"],
        "prep":    lambda c: _thumb(c, "prep", "--ids", c["pid"]),
        "run":     "batches/ 를 읽고 원본 적합성 8기준으로 기준 이미지를 고르고(+레시피 "
                   "모드면 배경전략·프롬프트 작성) results/result_NNN.json 에 쓴다",
        # `output` 은 **run 이 만드는 것**이어야 한다. generated.json 은 preview 산출물이라
        # 그걸 적으면 record 가 영영 통과하지 못한다(상세에서 실제로 났던 교착).
        "output":  "results/",
        # 2026-08-01: prep 이 대표옵션 확정건을 result_000 에 선기록하고 배치에서 빼므로
        # batch_001.json 은 없을 수 있다(1건 세로 실행이 정확히 그 경우). 인덱스가 산출물.
        "prep_out": "batches_index.json",
        "preview": lambda c: _thumb(c, "apply", "--generate"),
        "commit":  lambda c: _thumb(c, "apply", "--commit"),
    },
    {
        # 썸네일과 같은 예외 — preview 에서 크레딧이 든다(승인 대상인 생성 8장이
        # 실제 생성을 돌려야만 나온다). 1건이라 검수 샘플 = 전수다.
        "name": "상세", "dir": "05-상세", "deps": ["카테고리"],
        "prep":    lambda c: _detail(c, "prep", "--ids", c["pid"]),
        # run 이 **없다** — 생성은 판단이 아니라 접수→폴링이라 Claude 차례가 없다.
        # None 은 1급 표기다(§run 이 없는 단계): prep 이 끝나면 곧장 preview 로 간다.
        "run":     None,
        "output":  None,
        "prep_out": "batches/batch_001.json",
        "preview": lambda c: _detail(c, "apply", "--generate", "--sample-size", "1"),
        "commit":  lambda c: _detail(c, "apply", "--commit"),
    },
]
STEP_BY_NAME = {s["name"]: s for s in STEPS}


# ---------------------------------------------------------------------------
# run 이 없는 단계
#
# 대부분의 단계는 `run` 이 Claude 차례다(썸네일·중국어 원문을 보는 판단). 그런데 상세는
# 판단할 것이 없다 — 접수하고 폴링하면 끝이라 그 자리에 사람도 Claude도 설 이유가 없다.
# 그런 단계는 `run: None` 으로 선언하고, 상태머신이 PREPPED 를 사람 손 없이 RAN 으로
# 통과시킨다. 특수 취급을 단계 **이름**("상세")으로 하지 않는 이유는, 다음에 같은 성격의
# 단계가 붙을 때 또 이름을 심게 되기 때문이다.
# ---------------------------------------------------------------------------

def has_run(step):
    """그 단계에 Claude 차례(run)가 있나."""
    return bool((STEP_BY_NAME.get(step) or {}).get("run"))


# ---------------------------------------------------------------------------
# 상태 파일
# ---------------------------------------------------------------------------

def runs_root():
    return cfg("paths.onestep_runs", required=True)


def state_path(pid):
    return os.path.join(runs_root(), pid, "state.json")


def load_state(pid):
    p = state_path(pid)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# 드라이런 — 명령 시퀀스만 보고 흔적은 남기지 않는다.
# 상태를 **메모리에서만** 굴려야 체인 전체(카테고리→상품명→옵션)를 미리 볼 수 있으면서
# 파일이 오염되지 않는다. 여기서 막지 않으면 "구경했을 뿐인데 prep 완료로 찍히는" 일이 난다.
_DRY = False


def save_state(st):
    if _DRY:
        st["_갱신"] = "(dry-run)"
        return st
    p = state_path(st["productId"])
    os.makedirs(os.path.dirname(p), exist_ok=True)
    st["_갱신"] = time.strftime("%Y-%m-%d %H:%M:%S")
    tmp = f"{p}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)
    return st


def _need(pid):
    st = load_state(pid)
    if st is None:
        raise SystemExit(f"상태가 없다. 먼저: onestep.py start --pid {pid} --group-name ...")
    return st


def run_dir_of(st, step):
    return os.path.join(runs_root(), st["productId"], STEP_BY_NAME[step]["dir"])


def _ctx(st, step):
    return {"pid": st["productId"], "sheet": st["sheet"], "그룹": st.get("그룹", ""),
            "group_id": st.get("group_id", 0), "rd": run_dir_of(st, step),
            "source_date": st.get("source_date", ""),
            "force": bool((st["단계"].get(step) or {}).get("force_preview"))}


def _resolve_sheet(group_name, sheet=""):
    """그룹명 → 그룹 시트 id. 옵션정리 스킬의 해석 규칙과 같다."""
    if sheet:
        return sheet
    name = (group_name or "").strip()
    if not name:
        raise SystemExit("--sheet 또는 --group-name 중 하나는 필요하다")
    groups = list(matrix.index_groups())
    for g, sid in groups:
        if g == name:
            return sid
    hits = [(g, sid) for g, sid in groups if name in g]
    if len(hits) != 1:
        raise SystemExit(f"'{name}' 으로 그룹 시트를 특정하지 못했다(후보 {len(hits)}개)")
    return hits[0][1]


# ---------------------------------------------------------------------------
# 진행 판정
# ---------------------------------------------------------------------------

def _stat(st, step):
    return (st["단계"].get(step) or {}).get("상태", TODO)


def _blocked(st, step):
    """선행 단계가 아직 저장까지 안 끝났으면 그 이름들. 가결정이 있으면 카테고리는 통과."""
    out = []
    for dep in STEP_BY_NAME[step]["deps"]:
        s = _stat(st, dep)
        if s == DONE:
            continue
        # 가결정이 심어져 있으면 카테고리는 '값이 정해진' 상태라 다음 단계가 진행 가능하다.
        # (`product` 모드에서 저장이 게이트 뒤로 밀리는 경우)
        # `보류(...)`·`해당없음` 처럼 ORDER 밖의 값은 진행 상태가 아니므로 그대로 막는다.
        if dep == "카테고리" and s in ORDER and ORDER.index(s) >= ORDER.index(PREVIEWED) \
                and (st["단계"].get(dep) or {}).get("가결정"):
            continue
        out.append(dep)
    return out


def next_action(st):
    """다음에 할 일 1개. 반환 dict 의 `종류` = prep / run / preview / gate / commit / 완료."""
    gate = st.get("gate", "step")

    # 1) 가공(prep→run→preview)을 DAG 순서로 밀어 올린다
    for s in STEPS:
        name = s["name"]
        cur = _stat(st, name)
        if cur in (DONE, "해당없음") or str(cur).startswith("보류"):
            continue
        blocked = _blocked(st, name)
        if blocked:
            continue
        if cur == TODO:
            return {"종류": "prep", "단계": name}
        if cur == PREPPED:
            # run 이 없는 단계는 여기서 멈추지 않는다. 멈추면 러너가 `record` 를 시키고,
            # `record` 는 preview 가 만드는 파일을 요구해 영영 못 넘어간다. 그 교착을
            # 손으로 뚫으려면 preview 명령을 미리 돌려야 하는데 — 그게 유료 생성이라
            # 이어지는 preview 에서 같은 상품을 한 번 더 태운다(40크레딧 × 2).
            return {"종류": "run" if has_run(name) else "preview", "단계": name}
        if cur == RAN:
            return {"종류": "preview", "단계": name}
        # PREVIEWED → 저장은 아래 게이트 판정으로
        if gate == "step":
            if not (st["단계"][name].get("승인") or {}):
                return {"종류": "gate", "단계": name}
            return {"종류": "commit", "단계": name}

    # 2) product/risky/none — 가공이 다 끝난 뒤 한 번에 판정
    pend = [s["name"] for s in STEPS if _stat(st, s["name"]) == PREVIEWED]
    if pend:
        if gate == "product" and not st.get("승인"):
            return {"종류": "gate", "단계": "전체", "대상": pend}
        if gate == "risky" and not st.get("승인"):
            sigs = [x for n in pend for x in (st["단계"][n].get("신호") or [])]
            if sigs:
                return {"종류": "gate", "단계": "전체", "대상": pend, "신호": sigs}
        return {"종류": "commit", "단계": pend[0]}

    left = [s["name"] for s in STEPS if _stat(st, s["name"]) not in (DONE, "해당없음")
            and not str(_stat(st, s["name"])).startswith("보류")]
    if left:
        return {"종류": "대기", "단계": left[0],
                "사유": f"선행 미완: {', '.join(_blocked(st, left[0])) or '알 수 없음'}"}
    return {"종류": "완료"}


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------

def _sh(argv, dry=False):
    print(f"\n$ {os.path.basename(argv[0])} {' '.join(argv[1:])}\n{'-' * 56}")
    if dry:
        print("(dry-run — 실행하지 않음)")
        return 0
    proc = subprocess.run([PY, *argv],
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return proc.returncode


def _set(st, step, **fields):
    st["단계"].setdefault(step, {}).update(fields)
    return save_state(st)


def _signal_kw(step, st):
    if step != "상품명":
        return {}
    return {"name_check_py": _script("product-name/scripts/name_check.py"), "py": PY}


def _zero_target(index_data):
    """`batches_index.json` 이 '대상 0건' sentinel 이면 그 이유, 아니면 None.

    스킬의 prep 은 대상이 0건일 때(전부 기작업 등) 배치 파일을 만들지 않는다. 그때
    **산출물이 아예 없으면** 러너가 'prep 실패'와 구분하지 못하므로, 스킬 쪽에서
    `{"대상": 0, "이유": ...}` 를 남기기로 했다(Task 6). 정상 인덱스는 배열이라
    dict 인지부터 본다 — 배열을 sentinel 로 오독하면 진짜 배치를 0건으로 버린다.
    """
    if not isinstance(index_data, dict):
        return None
    if index_data.get("대상") != 0:
        return None
    return str(index_data.get("이유") or "대상 0건")


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def do_prep(st, step, dry=False):
    c = _ctx(st, step)
    if not dry:
        os.makedirs(c["rd"], exist_ok=True)
    rc = _sh(STEP_BY_NAME[step]["prep"](c), dry)
    if rc != 0:
        raise SystemExit(f"[중단] {step} prep 실패 (exit {rc})")

    # 대상 0건은 **정상 완료**다. 이 sentinel 을 먼저 보지 않으면 아래 산출물 검사가
    # "prep 이 아무것도 안 남겼다"로 오판해 멈춘다(썸네일·상세가 그랬다 — sentinel 을
    # 만들어 놓고 정작 러너가 안 읽었다).
    if not dry:
        why = _zero_target(_read_json(os.path.join(c["rd"], "batches_index.json")))
        if why:
            print(f"  대상 0건 — {why}. 이 단계는 할 일이 없다.")
            _set(st, step, 상태=DONE, run_dir=c["rd"], 메모=f"대상 0건({why})")
            return st

    # **exit 0 을 성공으로 믿지 않는다.** 스킬의 prep 은 "대상 0건"을 정상 종료로 알리는
    # 경로가 있었고, 그러면 러너가 산출물 없이 다음 단계로 넘어간다(실제로 났던 사고).
    out = STEP_BY_NAME[step].get("prep_out")
    if out and not dry:
        path = os.path.join(c["rd"], out)
        if not os.path.exists(path) or os.path.getsize(path) < 3:
            raise SystemExit(
                f"[중단] {step} prep 이 산출물을 남기지 않았다: {path}\n"
                f"  exit 0 이어도 대상이 0건이면 여기서 멈춘다.")
    # run 이 없는 단계는 prep 이 끝난 순간 이미 run 을 지났다 — 상태 파일에도 그렇게 쓴다.
    _set(st, step, 상태=PREPPED if has_run(step) else RAN, run_dir=c["rd"])
    return st


def do_preview(st, step, dry=False):
    c = _ctx(st, step)
    rc = _sh(STEP_BY_NAME[step]["preview"](c), dry)
    if rc != 0:
        raise SystemExit(f"[중단] {step} preview 실패 (exit {rc})")
    if dry:
        # 산출물이 없으니 신호 판정도 가결정 쓰기도 하지 않는다(둘 다 실물을 건드린다)
        _set(st, step, 상태=PREVIEWED, 가결정="(dry-run)" if step == "카테고리" else None)
        return st
    sigs = signals.for_step(step, c["rd"], c["pid"], **_signal_kw(step, st))
    # 강제 재조회는 1회용 — 남겨 두면 다음 preview 마다 외부 조회를 다시 태운다.
    fields = {"상태": PREVIEWED, "신호": sigs, "force_preview": False}

    # 카테고리 확정값을 스냅샷에 '가결정'으로 심는다 — 승인 전이라 불사자에는 아직 없지만
    # 상품명 단계가 이 값으로 키워드를 골라야 한다(DAG 필수 선행).
    if step == "카테고리":
        path = signals.category_decision(c["rd"], c["pid"])
        if path:
            snapshot.set_provisional(c["pid"], path)
            fields["가결정"] = path
            print(f"  가결정 카테고리: {path}")
        else:
            print("  (카테고리를 확정하지 못했다 — 가결정 없음)")
    _set(st, step, **fields)
    for line in signals.fmt(sigs):
        print("  " + line)
    return st


def do_commit(st, step, dry=False):
    c = _ctx(st, step)
    rc = _sh(STEP_BY_NAME[step]["commit"](c), dry)
    if rc != 0:
        raise SystemExit(f"[중단] {step} commit 실패 (exit {rc})")
    if step == "카테고리" and not dry:
        snapshot.commit_provisional(c["pid"])
    _set(st, step, 상태=DONE)
    # 현황판은 각 스킬이 자기 열을 이미 갱신한다. 여기서는 확인만 하고 덧쓰지 않는다
    # (자기 열 1칸만 쓴다는 계약을 러너가 어기면 원장이 두 벌이 된다).
    return st


# ---------------------------------------------------------------------------
# 출력
# ---------------------------------------------------------------------------

def _fmt_action(st, act):
    pid = st["productId"]
    kind = act["종류"]
    if kind == "완료":
        return f"{pid} · 전 단계 완료"
    step = act["단계"]
    idx = [s["name"] for s in STEPS].index(step) + 1 if step in STEP_BY_NAME else 0
    head = f"{pid} · 단계 {idx}/{len(STEPS)} · {step}" if idx else f"{pid} · {step}"
    c = _ctx(st, step) if step in STEP_BY_NAME else {}
    if kind == "prep":
        return (f"{head} · prep 필요\n"
                f"  실행: onestep.py advance --pid {pid}")
    if kind == "run":
        s = STEP_BY_NAME[step]
        prev = (st["단계"].get("카테고리") or {}).get("가결정") or ""
        lines = [f"{head} · run 대기 (Claude 차례)",
                 f"  run-dir: {c['rd']}",
                 f"  할 것: {s['run']}",
                 f"  산출:  {s['output']}"]
        if step == "상품명" and prev:
            lines.append(f"  참고:  카테고리 = {prev}")
        lines.append(f"  끝나면: onestep.py record --pid {pid} --step {step}")
        return "\n".join(lines)
    if kind == "preview":
        return f"{head} · preview 필요\n  실행: onestep.py advance --pid {pid}"
    if kind == "gate":
        return f"{head} · 승인 대기\n  확인: onestep.py gate --pid {pid}"
    if kind == "commit":
        return f"{head} · 저장 대기\n  실행: onestep.py advance --pid {pid}"
    if kind == "대기":
        return f"{head} · 대기 — {act.get('사유', '')}"
    return f"{head} · {kind}"


def _print_gate(st, act):
    pid = st["productId"]
    targets = act.get("대상") or [act["단계"]]
    print("=" * 60)
    print(f"【게이트】 {pid} · 모드 {st.get('gate')} · 대상 {', '.join(targets)}")
    print("=" * 60)
    allsig = []
    for name in targets:
        d = st["단계"].get(name) or {}
        print(f"\n[{name}]  run-dir: {d.get('run_dir', '')}")
        # 검수표를 신호보다 **먼저** 찍는다 — 승인 대상이 무엇인지가 먼저고,
        # 신호는 그걸 볼 때 유의할 점이다. 순서가 반대면 화면 위쪽이 경고로만 찬다.
        for line in signals.detail(name, run_dir_of(st, name), pid):
            print("  " + line)
        sigs = d.get("신호") or []
        allsig += sigs
        for line in signals.fmt(sigs):
            print("  " + line)
        if not sigs:
            print("  (신호 없음)")
        # 되돌린 시도에서 떴던 신호도 보여준다 — 승인 로그에 함께 실린다.
        for h in (d.get("신호이력") or []):
            for line in signals.fmt(h.get("신호") or []):
                print(f"  [{h.get('회차')}차 시도] " + line)
            print(f"     └ 되돌린 사유: {h.get('사유', '')}")
    print("\n" + "-" * 60)
    print("승인:  onestep.py approve --pid %s --step %s [--fix \"...\"] [--memo \"...\"]"
          % (pid, targets[0] if len(targets) == 1 else "전체"))
    print("보류:  onestep.py hold    --pid %s --step %s --reason \"...\""
          % (pid, targets[0] if len(targets) == 1 else "전체"))
    if allsig:
        print(f"\n신호 {len(allsig)}건 — 승인 전에 위 항목을 확인하세요.")
    return allsig


# ---------------------------------------------------------------------------
# 명령
# ---------------------------------------------------------------------------

def cmd_start(a):
    sheet = _resolve_sheet(a.group_name, a.sheet)
    st = load_state(a.pid)
    if st and not a.force:
        print(f"이미 있다: {state_path(a.pid)} (--force 로 새로 시작)")
        return
    m = matrix.read(sheet)
    if a.pid not in m:
        print(f"  [경고] 현황판에 없는 상품이다: {a.pid}")
    st = {
        "productId": a.pid, "그룹": a.group_name, "sheet": sheet,
        "group_id": a.group_id, "gate": a.gate,
        "source_date": a.source_date,
        "상품": (m.get(a.pid) or {}).get("상품", ""),
        "생성": time.strftime("%Y-%m-%d %H:%M:%S"),
        "단계": {s["name"]: {"상태": TODO} for s in STEPS},
    }
    # 현황판에 이미 완료로 찍힌 작업은 건너뛴다(멱등 — 재처리 0).
    for s in STEPS:
        v = (m.get(a.pid) or {}).get(s["name"], "")
        if v == matrix.DONE:
            st["단계"][s["name"]] = {"상태": DONE, "메모": "현황판 완료(이전 작업)"}
        elif v == matrix.NA:
            st["단계"][s["name"]] = {"상태": "해당없음"}
        elif matrix.is_redo(v):
            # 다른 단계가 넘긴 일감 — 세로는 1건이라 모아둘 이유가 없다. 바로 대상.
            st["단계"][s["name"]] = {"상태": TODO, "재작업": matrix.redo_reason(v)}
        elif v:
            st["단계"][s["name"]] = {"상태": v}
    save_state(st)
    print(f"시작: {a.pid} · 그룹 {a.group_name} · 게이트 {a.gate}")
    print(f"  상태 파일: {state_path(a.pid)}")
    print("\n" + _fmt_action(st, next_action(st)))


def cmd_next(a):
    st = _need(a.pid)
    act = next_action(st)
    if a.json:
        print(json.dumps(act, ensure_ascii=False))
        return
    print(_fmt_action(st, act))


def cmd_advance(a):
    global _DRY
    _DRY = bool(a.dry_run)
    st = _need(a.pid)
    while True:
        act = next_action(st)
        kind = act["종류"]
        # 드라이런은 Claude 차례와 게이트를 건너뛰고 **체인 전체**를 미리 보여준다.
        # 실행 모드에서는 거기서 멈춰야 한다(그게 게이트의 존재 이유다).
        if _DRY and kind == "run":
            _set(st, act["단계"], 상태=RAN)
            continue
        if _DRY and kind == "gate":
            for n in (act.get("대상") or [act["단계"]]):
                _set(st, n, 승인={"결과": "(dry-run)"})
            st["승인"] = {"결과": "(dry-run)"}
            continue
        if kind in ("run", "gate", "완료", "대기"):
            print(_fmt_action(st, act) if kind != "gate" else "")
            if kind == "gate":
                _print_gate(st, act)
            return
        step = act["단계"]
        if kind == "prep":
            do_prep(st, step, a.dry_run)
        elif kind == "preview":
            do_preview(st, step, a.dry_run)
        elif kind == "commit":
            do_commit(st, step, a.dry_run)
        if a.once:
            print("\n" + _fmt_action(st, next_action(st)))
            return


def cmd_record(a):
    """Claude 가 run 단계를 끝냈다고 알린다."""
    st = _need(a.pid)
    step = a.step
    if step not in STEP_BY_NAME:
        raise SystemExit(f"모르는 단계: {step}")
    if not has_run(step):
        # 여기서 조용히 통과시키면 안 된다. `record` 를 부른다는 건 "run 산출물을
        # 만들었다"는 뜻인데, 이 단계에 그런 산출물이 있다면 그건 preview(=유료 생성)를
        # 손으로 미리 돌렸다는 뜻이고, 이어지는 preview 가 같은 상품을 또 태운다.
        raise SystemExit(
            f"[중단] '{step}' 단계엔 run 이 없다 — record 할 것이 없다.\n"
            f"  prep 다음 바로 preview 다: onestep.py advance --pid {a.pid}")
    if _stat(st, step) != PREPPED:
        print(f"  [경고] 현재 상태가 '{_stat(st, step)}' 다 (기대: {PREPPED})")
    rd = run_dir_of(st, step)
    out = STEP_BY_NAME[step]["output"].rstrip("/")
    if not os.path.exists(os.path.join(rd, out)):
        raise SystemExit(f"[중단] 산출물이 없다: {os.path.join(rd, out)}")
    _set(st, step, 상태=RAN)
    print(f"기록: {a.pid} · {step} run 완료")
    print("\n" + _fmt_action(st, next_action(st)))


def cmd_gate(a):
    st = _need(a.pid)
    act = next_action(st)
    if act["종류"] != "gate":
        print(f"지금은 승인 대기가 아니다.\n\n{_fmt_action(st, act)}")
        return
    _print_gate(st, act)


def _all_signals(d):
    """그 단계에서 **여태 뜬 신호 전부** — 되돌린 시도의 것까지 합친다."""
    out = list(d.get("신호") or [])
    for h in (d.get("신호이력") or []):
        out += list(h.get("신호") or [])
    return out


def _attempts(d):
    return len(d.get("신호이력") or []) + 1


def cmd_approve(a):
    st = _need(a.pid)
    steps = ([s["name"] for s in STEPS if _stat(st, s["name"]) == PREVIEWED]
             if a.step == "전체" else [a.step])
    result = "수정승인" if a.fix else "승인"
    for name in steps:
        d = st["단계"].get(name) or {}
        approval_log.record(
            st["sheet"], a.pid, name, result, signals=_all_signals(d),
            fix=a.fix, memo=a.memo, gate=st.get("gate", ""),
            summary=d.get("가결정", ""), attempts=_attempts(d))
        _set(st, name, 승인={"결과": result, "시각": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "수정": a.fix, "메모": a.memo})
    if a.step == "전체":
        st["승인"] = {"결과": result, "시각": time.strftime("%Y-%m-%d %H:%M:%S")}
        save_state(st)
    print(f"{result}: {a.pid} · {', '.join(steps)}")
    print("\n" + _fmt_action(st, next_action(st)))


def cmd_hold(a):
    st = _need(a.pid)
    steps = ([s["name"] for s in STEPS if _stat(st, s["name"]) == PREVIEWED]
             if a.step == "전체" else [a.step])
    for name in steps:
        d = st["단계"].get(name) or {}
        approval_log.record(st["sheet"], a.pid, name, "보류",
                            signals=_all_signals(d), memo=a.reason,
                            gate=st.get("gate", ""), attempts=_attempts(d))
        _set(st, name, 상태=f"보류({a.reason})")
        if name == "카테고리":
            snapshot.clear_provisional(a.pid)   # 가결정을 남기면 다음 스킬이 잘못 읽는다
    print(f"보류: {a.pid} · {', '.join(steps)} — {a.reason}")


# `--from` = 어느 단계부터 다시 하나 → 되돌아갈 상태.
# 판단(run)만 고쳐 다시 보고 싶을 때 prep 부터 되돌리면 workdata·썸네일을 다시 받는다.
# 실전 1건에서 바로 걸렸다: 검색어만 바꿔 셀하를 다시 태우면 되는데 경로가 없었다.
REDO_FROM = {"prep": TODO, "run": PREPPED, "preview": RAN}


def cmd_redo(a):
    """이미 끝낸 단계를 되돌려 다시 태운다 — 뒤 단계에서 앞 단계 문제를 발견했을 때.

    가로(1000건)는 현황판에 `재작업(...)` 을 찍어 모아 뒀다가 그 단계 차례에 몰아 하지만,
    세로는 1건이라 모아둘 이유가 없다. 그 자리에서 되돌아간다.

    `--from preview` 는 run 산출물(keywords.json 등)을 **그대로 두고** 검증만 다시 돌린다.
    그 파일을 손으로 고친 뒤 쓰는 경로다. 외부 조회는 강제 재조회로 붙는다.
    """
    st = _need(a.pid)
    if a.step not in STEP_BY_NAME:
        raise SystemExit(f"모르는 단계: {a.step}")
    back = REDO_FROM[a.frm]
    was = _stat(st, a.step)
    keep = st["단계"].get(a.step) or {}
    # 버려지는 시도의 신호를 이력에 남긴다. 마지막 시도 신호만 로그에 실으면
    # "고쳐서 통과시켰는데 신호는 없었다"는 모순된 행이 남는다(첫 기록에서 실제로 났다).
    hist = list(keep.get("신호이력") or [])
    if keep.get("신호"):
        hist.append({"회차": len(hist) + 1, "신호": keep["신호"],
                     "사유": a.reason, "되돌린지점": a.frm})
    d = {"상태": back, "재작업": a.reason, "이전상태": was, "신호이력": hist}
    if back != TODO:                       # prep 산출물을 살려 두는 경우
        d["run_dir"] = keep.get("run_dir") or run_dir_of(st, a.step)
    if back == RAN:
        d["force_preview"] = True          # 외부 조회를 다시 태운다(--resume 무력화)
    st["단계"][a.step] = d
    st.pop("승인", None)                    # 상품 단위 승인도 무효 — 내용이 바뀐다
    # 카테고리를 다시 하면 그 상품의 상품명은 폐기 대상이다(두 스킬 양방향 계약).
    if a.step == "카테고리":
        snapshot.clear_provisional(a.pid)
        if _stat(st, "상품명") == DONE:
            st["단계"]["상품명"] = {"상태": TODO, "재작업": "카테고리 재작업 — 키워드 재선정"}
            print("  상품명도 함께 되돌렸다(카테고리 재교정 = 상품명 폐기).")
    save_state(st)
    print(f"되돌림: {a.pid} · {a.step} ({was} → {back}, --from {a.frm}) — {a.reason}")
    if back == RAN:
        print(f"  run 산출물은 그대로 둔다 — 고친 뒤 advance 하면 외부 조회를 다시 태운다.")
    print("\n" + _fmt_action(st, next_action(st)))


def cmd_status(a):
    st = _need(a.pid)
    print(f"{st['productId']} · {st.get('상품', '')}")
    print(f"  그룹 {st.get('그룹', '')} · 게이트 {st.get('gate')} · 시트 {st['sheet']}")
    print(f"  {'단계':<10}{'상태':<14}{'신호'}")
    for s in STEPS:
        d = st["단계"].get(s["name"]) or {}
        sig = ", ".join(x["코드"] for x in (d.get("신호") or [])) or "-"
        print(f"  {s['name']:<10}{d.get('상태', TODO):<14}{sig}")
    print("\n" + _fmt_action(st, next_action(st)))


def cmd_rebuild(a):
    """현황판에서 state.json 을 다시 만든다 — state 는 파생본이라 지워도 복구된다."""
    st = load_state(a.pid)
    group = a.group_name or (st or {}).get("그룹", "")
    sheet = _resolve_sheet(group, a.sheet or (st or {}).get("sheet", ""))
    m = matrix.read(sheet)
    rec = m.get(a.pid)
    if not rec:
        raise SystemExit(f"현황판에 없는 상품이다: {a.pid}")
    new = {
        "productId": a.pid, "그룹": group, "sheet": sheet,
        "group_id": a.group_id or (st or {}).get("group_id", 0),
        "gate": a.gate or (st or {}).get("gate", "step"),
        "source_date": a.source_date or (st or {}).get("source_date", ""),
        "상품": rec.get("상품", ""),
        "생성": (st or {}).get("생성") or time.strftime("%Y-%m-%d %H:%M:%S"),
        "단계": {},
    }
    for s in STEPS:
        v = rec.get(s["name"], "")
        if v == matrix.DONE:
            new["단계"][s["name"]] = {"상태": DONE, "메모": "현황판에서 복구"}
        elif v == matrix.NA:
            new["단계"][s["name"]] = {"상태": "해당없음"}
        elif matrix.is_redo(v):
            new["단계"][s["name"]] = {"상태": TODO, "재작업": matrix.redo_reason(v)}
        elif v:
            new["단계"][s["name"]] = {"상태": v}
        else:
            new["단계"][s["name"]] = {"상태": TODO}
    save_state(new)
    print(f"복구: {state_path(a.pid)}")
    print("\n" + _fmt_action(new, next_action(new)))


def main():
    ap = argparse.ArgumentParser(
        description="세로 러너 — 상품 1개 × 작업 전부",
        epilog="게이트: " + " / ".join(f"{k}={v}" for k, v in GATE_HELP.items()))
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(x):
        x.add_argument("--pid", required=True, help="상품id")

    s = sub.add_parser("start", help="진행 시작 — 상태 파일 생성")
    common(s)
    s.add_argument("--group-name", default="", help="마켓그룹명 (예: 1번_용쌤1-1)")
    s.add_argument("--sheet", default="", help="그룹 시트 id 직접 지정")
    s.add_argument("--group-id", type=int, default=0, help="불사자 마켓그룹 id (상품명 prep 필수)")
    s.add_argument("--source-date", default="",
                   help="셀러라이프 통다운 YYMMDD (상품명 prep 필수)")
    s.add_argument("--gate", choices=GATES, default="step")
    s.add_argument("--force", action="store_true", help="기존 상태를 버리고 새로 시작")
    s.set_defaults(func=cmd_start)

    n = sub.add_parser("next", help="다음 할 일 1개 (부작용 없음)")
    common(n)
    n.add_argument("--json", action="store_true")
    n.set_defaults(func=cmd_next)

    a = sub.add_parser("advance", help="다음 할 일이 스크립트면 실행. Claude 차례면 멈춘다")
    common(a)
    a.add_argument("--once", action="store_true", help="한 단계만")
    a.add_argument("--dry-run", action="store_true", help="명령만 출력하고 실행하지 않는다")
    a.set_defaults(func=cmd_advance)

    r = sub.add_parser("record", help="Claude 가 run 을 끝냈다고 알린다")
    common(r)
    r.add_argument("--step", required=True, choices=[s["name"] for s in STEPS])
    r.set_defaults(func=cmd_record)

    g = sub.add_parser("gate", help="승인 화면(요약 + 신호)")
    common(g)
    g.set_defaults(func=cmd_gate)

    ap2 = sub.add_parser("approve", help="게이트 승인")
    common(ap2)
    ap2.add_argument("--step", required=True)
    ap2.add_argument("--fix", default="", help="고쳐서 통과시킨 내용 → '수정승인' 으로 기록")
    ap2.add_argument("--memo", default="")
    ap2.set_defaults(func=cmd_approve)

    h = sub.add_parser("hold", help="보류")
    common(h)
    h.add_argument("--step", required=True)
    h.add_argument("--reason", required=True)
    h.set_defaults(func=cmd_hold)

    rd = sub.add_parser("redo", help="끝낸 단계를 되돌려 다시 태운다")
    common(rd)
    rd.add_argument("--step", required=True, choices=[s["name"] for s in STEPS])
    rd.add_argument("--reason", required=True)
    rd.add_argument("--from", dest="frm", choices=list(REDO_FROM), default="prep",
                    help="어디부터 다시 하나. preview=run 산출물을 살리고 검증만 다시")
    rd.set_defaults(func=cmd_redo)

    t = sub.add_parser("status", help="현재 상태 표")
    common(t)
    t.set_defaults(func=cmd_status)

    b = sub.add_parser("rebuild", help="현황판에서 state.json 재구성")
    common(b)
    b.add_argument("--group-name", default="")
    b.add_argument("--sheet", default="")
    b.add_argument("--group-id", type=int, default=0)
    b.add_argument("--source-date", default="")
    b.add_argument("--gate", choices=GATES, default=None)
    b.set_defaults(func=cmd_rebuild)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
