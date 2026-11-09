#!/usr/bin/env python3
"""제외카테고리 상품 게이트 — 재고 스캔(CLI) + 붙박이 게이트(라이브러리) 한 벌.

게이트(붙박이)와 스캔(1회 명령)은 대상이 다른 물건이다:
  게이트 : 앞으로 교정될 것·재교정될 것 → catfix 저장부가 부르는 `gate_records()`
  스캔   : 이미 교정 끝난 재고          → 이 스크립트의 `scan` 서브커맨드, 1회 실행

**판정·표시·큐 규칙은 둘이 같은 코드를 쓴다**(`gate_select` · `_make_queue` · `V_PENDING`).
두 벌이 되면 "게이트가 잡은 것"과 "스캔이 잡은 것"의 뜻이 조용히 갈라진다.
붙박이 게이트의 산출물은 catfix run-dir 아래 **`gate/` 한 칸 내려** 쓴다(`gate_dir`) —
`targets.json` 이름이 catfix 자기 것과 겹치기 때문. 그래서 삭제·승격은 이 스크립트의
`finalize --run-dir <catfix run-dir>/gate` 가 그대로 받는다.

이 스캔이 따로 필요한 이유는 catfix 대상 선정이 *"G열 상태가 찬 행은 건너뛴다"* 라
그룹을 다시 돌려도 그 상품들이 게이트를 다시 지나지 않기 때문이다.

**모집단은 그룹 시트 `시트1`(catfix 원장)** — 로컬 스냅샷도 `00_진행` 도 아니다.
  - 스냅샷: 이 맥에 받아진 것만이라 54그룹과 같은 모집단이 아니다
  - `00_진행`: 카테고리 **경로가 없다**(`완료` 만 있다)
불사자 MCP 를 한 번도 부르지 않는다. 시트 읽기만 한다.

시트1 열: A=상품id B=상품명 C=이전카테고리 D=변경카테고리 E=검색어 F=확신도
          G=상태 H=기록일 I=위험/근접플래그 J=실물판정 K=썸네일URL

**확정 카테고리 = D, 비면 C.** 세 저장 경로가 전부 D 에 *실제 저장된 불사자 경로*를 쓴다 —
`bulsaja_mcp.py:292`(정확일치) · `:288`(`이미정확` 은 기존 경로를 D 에 복사) ·
`category_steer.py:150`(유도·근접 저장은 `hit["ss"]`).

**태우는 상태는 `DONE_STATUSES`** — `matrix.CATFIX_DONE` 3종(`자동저장완료`·`저장완료`·
`이미정확`) + 구버전 확정 2종(`근사매칭저장`·`기존유지`, 2026-08-09 이룸님. §LEGACY_DONE).
의심 건(`매칭불가`·`부분일치확인요`·`보류(정체불명)`·`변경대상` 등)은 삭제하지 않는다 —
어차피 재교정을 돌게 되어 있고, 거기서 확정되면 그때 걸린다(2026-08-08 이룸님).
근접저장(I열)은 확정으로 보고 삭제하되 **구분 표기**한다(같은 날 이룸님).

설계 정본: `00-system/04-specs/2026-08-09-제외카테고리-재고스캔-design.md`
근거 노트: `40-personal/43-ideas/제외카테고리-상품-게이트.md`

CLI:
    python .claude/skills/bulsaja-category-fix/scripts/category_gate.py scan
    python ... scan --only 용쌤1-1            # 그룹명에 이 문자열이 든 것만(소규모 검증)
    python ... scan --blacklist <xlsx>        # 정본 대신 지정 파일로(재현·오프라인)

라이브러리(붙박이 게이트 — 호출부는 §붙박이 게이트 API):
    gate_records(sheet, [{productId, 상품명, 카테고리, 근접저장}], run_dir=..., m=...)
    queue_pending_deletes(sheet, run_dir=...)   # 런 시작 청소(미삭제분 재큐)
"""
import argparse
import datetime
import json
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# `.claude` 앵커(= lib/eroomlib)를 찾아 lib 를 1회 insert.
_d = SCRIPT_DIR
while _d and _d != os.path.dirname(_d):
    _lib = os.path.join(_d, "lib")
    if os.path.isdir(os.path.join(_lib, "eroomlib")):
        if _lib not in sys.path:
            sys.path.insert(0, _lib)
        break
    _d = os.path.dirname(_d)

from eroomlib import matrix  # noqa: E402
from eroomlib.config import cfg as _cfg  # noqa: E402
from eroomlib.exclusion import (SHEET_CAT, category_gate, is_broad_fragment,  # noqa: E402
                                load_blacklist)
from eroomlib.gsheets import sheets_get  # noqa: E402

CATFIX_TAB = "시트1"

# 태우는 상태 = `matrix.CATFIX_DONE` 3종 + **구버전 그룹에만 남은 확정 상태 2종**
# (2026-08-09 이룸님). 아래 둘은 지금 코드 어디에도 없다 — grep 0건. 구버전이거나 손으로 쓴 값이다.
#
#   `근사매칭저장` 201건/42그룹 — E열 `(근사)…` · F열 `근사%` · **D열이 실제 저장된 경로**.
#       로컬 스냅샷 대조에서 스냅샷 보유 5건 전부 D와 일치했다(스냅샷 `기존카테고리` 는 저장
#       성공 시에만 되쓰인다). 지금 코드의 `저장완료` + I열 `근접저장(셀하≠불사자)` 를
#       G열에 직접 적은 구버전 표기다 → 근접저장과 같은 성격이라 **구분 표기 대상**이다.
#
#   `기존유지` 29건/16그룹 — E열 `(근사후보)…` · F열 빈칸 · **D열은 기각된 후보**다.
#       이름 그대로 기존 카테고리를 유지한 것이라 **C열이 실제 카테고리**.
#       D 로 읽으면 20건이 걸리지만 그건 안 쓴 후보를 판정한 것이고, C 로는 1건이다.
#
# `현행유지(검색어오해)`·`현행유지(이룸님지정)` 16건은 태우지 않는다 — 사람이 현행 유지로
# 판단한 건이고, D열이 `(현행유지)` 리터럴이라 `_is_path` 가 이미 C 로 폴백시킨다(걸림 0건).
LEGACY_DONE = {"근사매칭저장", "기존유지"}
DONE_STATUSES = set(matrix.CATFIX_DONE) | LEGACY_DONE

# 이 상태는 D열이 **기각된 후보**다 → C열(이전카테고리)만 본다.
PREV_COL_STATUSES = {"기존유지"}

# 저장된 카테고리가 정확한 값이 아닌 상태 — 오삭제 가능성이 있어 종합보고에 구분 표기한다.
NEAR_STATUSES = {"근사매칭저장"}

# 시트1 열 인덱스 (0-based)
C_PID, C_NAME, C_PREV, C_NEW, C_STATUS, C_FLAG = 0, 1, 2, 3, 6, 8

# 현황판에서 이 상품은 이미 없는 것으로 본다 → 스캔 대상에서 뺀다.
GONE_PREFIXES = (matrix.DELETED_PREFIX, "삭제대기")

# 게이트가 찍는 값. `해당없음` 이 아닌 이유: 스킵 효과는 같지만(빈칸만 아니면 건너뛴다)
# 기록이 다르다 — 전자는 "이 작업은 해당 없음", 후자는 "이 상품은 지웠음"이고
# 종합보고에 삭제 목록으로 뽑히는 건 후자다(선례 `상품삭제(실물불명·자동)`).
V_PENDING = "삭제대기(제외카테고리)"
V_DELETED = "상품삭제(제외카테고리·자동)"

# 게이트가 막는 작업 = `matrix.TASKS` 9개 중 **뒤 7개**.
# `수집`·`카테고리` 는 실제로 완료된 사실이라 그대로 둔다.
GATED_TASKS = tuple(matrix.TASKS[2:])

DEFAULT_MAX_RATIO = 0.40   # 실측 28.2% 대비 여유. 넘으면 블랙리스트 오염 신호
FRAG_WARN_RATIO = 0.30     # 조각 하나가 대상의 이 비율 이상을 혼자 만들면 경고


# ---------------------------------------------------------------------------
# 읽기
# ---------------------------------------------------------------------------

def _s(row, i):
    return str(row[i]).strip() if row and len(row) > i and row[i] is not None else ""


def read_ledger(sheet_id, tab=CATFIX_TAB):
    """시트1 → [{productId, 상품명, 이전, 변경, 상태, 플래그, row}]. 헤더 행은 건너뛴다."""
    rows = sheets_get(sheet_id, f"'{tab}'!A1:K")
    if not rows:
        return []
    # 1행이 헤더인지 판정 — A1 이 상품id 처럼 안 생겼으면 헤더로 본다.
    # (`_status_by_id` 는 무조건 1행을 헤더로 보지만, 여기서 데이터 1건을 조용히
    #  잃으면 그 상품만 게이트를 영영 안 지난다. 잃는 쪽이 더 나쁘다.)
    start = 1 if not _s(rows[0], C_PID).isdigit() else 0
    out = []
    for i, r in enumerate(rows[start:], start=start + 1):
        pid = _s(r, C_PID)
        if not pid:
            continue
        out.append({
            "productId": pid,
            "상품명": _s(r, C_NAME),
            "이전카테고리": _s(r, C_PREV),
            "변경카테고리": _s(r, C_NEW),
            "상태": _s(r, C_STATUS),
            "플래그": _s(r, C_FLAG),
            "row": i,
        })
    return out


def _is_path(v):
    """카테고리 **경로**로 보이나. `(현행유지)`·`미설정` 같은 표식은 경로가 아니다.

    실측(2026-08-09): 구버전 그룹의 D열에 `(현행유지)` 리터럴이 들어 있다. 그걸 카테고리로
    읽으면 조각 매칭이 그 문자열을 대상으로 돌아 조용히 틀린 판정이 된다. 지금은 그 상태가
    `CATFIX_DONE` 밖이라 안 태우지만, 방어가 없으면 상태 목록을 넓히는 순간 터진다.
    """
    v = (v or "").strip()
    return bool(v) and v != "미설정" and not v.startswith("(")


def final_category(rec):
    """확정 카테고리 = 변경(D) 우선, 비면(또는 경로가 아니면) 이전(C).

    단 `PREV_COL_STATUSES`(=`기존유지`) 는 **D열이 기각된 후보**라 C열만 본다.
    """
    new, prev = rec.get("변경카테고리"), rec.get("이전카테고리")
    if rec.get("상태") in PREV_COL_STATUSES:
        return prev.strip() if _is_path(prev) else ""
    if _is_path(new):
        return new.strip()
    return prev.strip() if _is_path(prev) else ""


def already_gone(rec):
    """현황판 행이 "이 상품은 이미 없다"고 말하는가 — 없는 상품을 또 지우지 않는다.

    `삭제대기` 도 여기 든다. 이미 큐에 올라간 건을 다시 잡으면 같은 상품이 배치마다
    쌓인다. 잠금으로 남은 `삭제대기` 를 다시 태우는 건 게이트가 아니라
    `queue_pending_deletes`(런 시작 청소) · `retry` 의 몫이다.
    """
    vals = [(rec.get(t) or "").strip() for t in GATED_TASKS]
    return any(v == matrix.NA or v.startswith(GONE_PREFIXES) for v in vals)


def is_near_save(rec):
    """저장된 경로가 정확한 값이 아닌가 — 오삭제 가능성이 있어 구분 표기한다.

    두 경로가 같은 뜻이다: 지금 코드는 I열 플래그(`근접저장(셀하≠불사자)`)로 남기고,
    구버전은 G열 상태(`근사매칭저장`)로 남겼다.
    """
    return ("근접저장" in (rec.get("플래그") or "")
            or rec.get("상태") in NEAR_STATUSES)


# ---------------------------------------------------------------------------
# 판정
# ---------------------------------------------------------------------------

def scan_group(group, sheet_id, gate, read_matrix=True, tab=CATFIX_TAB):
    """그룹 1개 판정. 반환: (targets, stats)."""
    ledger = read_ledger(sheet_id, tab)
    m = matrix.read(sheet_id) if read_matrix else {}

    stats = {
        "행": len(ledger), "확정": 0, "제외대상": 0, "근접저장": 0,
        "상태별": {},                # 태우지 않은 상태의 분포(왜 줄었나)
        "카테고리없음": 0,
        "이미삭제": 0,               # 현황판이 이미 삭제/삭제대기로 본 상품
        "현황판미기록": 0,           # 시트1 은 저장됨인데 00_진행 카테고리 열이 빈 건
        "원장에없음": 0,             # 00_진행 에만 있고 시트1 에 없는 상품(catfix 미도달)
    }
    targets = []
    seen = set()

    for rec in ledger:
        pid = rec["productId"]
        seen.add(pid)
        st = rec["상태"]

        if st not in DONE_STATUSES:
            stats["상태별"][st or "(빈칸)"] = stats["상태별"].get(st or "(빈칸)", 0) + 1
            continue
        stats["확정"] += 1

        # 진단① — 저장은 됐는데 현황판에 안 찍힌 건(= category_steer 경로의 기존 버그).
        # 스캔은 시트1 을 모집단으로 잡으므로 **영향받지 않는다.** 크기만 잰다.
        if m and not (m.get(pid, {}).get("카테고리") or "").strip():
            stats["현황판미기록"] += 1

        cat = final_category(rec)
        if not cat:
            stats["카테고리없음"] += 1
            continue

        hits = gate.hits(cat)
        if not hits:
            continue

        # 이미 없는 상품은 대상에서 뺀다 — 없는 상품을 또 지우지 않는다.
        if m and pid in m and already_gone(m[pid]):
            stats["이미삭제"] += 1
            continue

        near = is_near_save(rec)
        if near:
            stats["근접저장"] += 1
        stats["제외대상"] += 1
        targets.append({
            "productId": pid, "그룹": group, "sheetId": sheet_id, "row": rec["row"],
            "상품명": rec["상품명"], "카테고리": cat, "상태": st,
            "조각": hits[0], "조각전체": hits, "근접저장": near,
        })

    # 진단② — 현황판에만 있고 원장에 없는 상품 = catfix 미도달(게이트가 잡을 몫).
    if m:
        stats["원장에없음"] = sum(1 for pid in m if pid not in seen)

    return targets, stats


# ---------------------------------------------------------------------------
# 리포트
# ---------------------------------------------------------------------------

def _top(counter, n=None):
    items = sorted(counter.items(), key=lambda kv: -kv[1])
    return items[:n] if n else items


def build_report(result, warnings):
    """scan 결과 → report.md 본문."""
    g = result["합계"]
    L = ["# 제외카테고리 재고 스캔", "",
         f"- 실행: {result['생성']}",
         f"- 블랙리스트: `{result['블랙리스트']}` (제외카테고리 {result['조각수']}조각)",
         f"- 그룹 {g['그룹']}개 (읽기 실패 {g['실패그룹']}개)",
         f"- 원장 {g['행']}행 · **확정 {g['확정']}건** · "
         f"**제외 대상 {g['제외대상']}건 ({g['비율']:.1%})**",
         f"- 그중 근접저장 {g['근접저장']}건 (저장 경로가 정확한 값이 아님 — 사후 확인용 구분)", ""]

    if warnings:
        L += ["## ⚠ 경고", ""] + [f"- {w}" for w in warnings] + [""]

    L += ["## 그룹별", "",
          "| 그룹 | 원장행 | 확정 | 제외대상 | 비율 | 근접 |", "|---|---|---|---|---|---|"]
    for r in sorted(result["그룹"], key=lambda x: -x["stats"]["제외대상"]):
        s = r["stats"]
        ratio = (s["제외대상"] / s["확정"]) if s["확정"] else 0
        L.append(f"| {r['그룹']} | {s['행']} | {s['확정']} | {s['제외대상']} | "
                 f"{ratio:.0%} | {s['근접저장']} |")
    L.append("")

    L += ["## 대분류별", "", "| 대분류 | 건수 |", "|---|---|"]
    for k, v in _top(result["대분류별"]):
        L.append(f"| {k} | {v} |")
    L.append("")

    frags = result["조각별"]
    L += [f"## 발동한 조각 {len(frags)}개 / 전체 {result['조각수']}개", "",
          "| 조각 | 건수 | 대분류급 |", "|---|---|---|"]
    for k, v in _top(frags, 40):
        L.append(f"| `{k}` | {v} | {'★' if is_broad_fragment(k) else ''} |")
    if len(frags) > 40:
        L.append(f"\n(상위 40개만 표시 — 전체는 `scan.json`)")
    L.append("")

    L += ["## 진단 (이 스캔이 곁다리로 잰 것)", "",
          f"- **현황판 미기록 {g['현황판미기록']}건** — 시트1 은 저장됨인데 `00_진행` 카테고리 열이 빈 건. "
          "`category_steer.py` 가 현황판을 안 쓰는 경로(근접저장 등)로 저장된 상품이다. "
          "게이트 이전부터 있던 버그이고, 스캔은 시트1 을 모집단으로 잡으므로 영향받지 않는다.",
          f"- **원장에 없음 {g['원장에없음']}건** — `00_진행` 에만 있고 시트1 에 없는 상품 = catfix 미도달. "
          "스캔 대상이 아니다(붙박이 게이트가 잡을 몫).",
          f"- **이미 삭제/삭제대기 {g['이미삭제']}건** — 제외 조각에는 걸렸지만 현황판이 이미 없는 "
          "상품으로 본 건. 대상에서 뺐다.", ""]

    if g["상태별"]:
        L += ["## 태우지 않은 상태 (의심 건 — 재교정에서 확정되면 그때 걸린다)", "",
              "| 상태 | 건수 |", "|---|---|"]
        for k, v in _top(g["상태별"]):
            L.append(f"| {k} | {v} |")
        L.append("")

    if result["실패"]:
        L += ["## 읽기 실패 그룹", ""] + [f"- {n}: {e}" for n, e in result["실패"]] + [""]
    return "\n".join(L)


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------

def cmd_scan(args):
    bl = load_blacklist(args.blacklist)
    gate = category_gate(args.blacklist)
    print(f"블랙리스트: {bl['경로']}")
    print(f"  제외카테고리 {len(gate)}조각 (대분류급 "
          f"{sum(1 for f in gate.fragments if is_broad_fragment(f))}개)")

    groups = matrix.index_groups(args.master_sheet)
    if args.only:
        groups = [(g, s) for g, s in groups if args.only in g]
    if not groups:
        print("[중단] 대상 그룹이 없습니다.", file=sys.stderr)
        return 1
    print(f"대상 그룹 {len(groups)}개\n")

    run_dir = args.run_dir or os.path.join(
        _cfg("paths.data_root", required=True), "category-gate", "runs",
        datetime.datetime.now().strftime("%y%m%d-%H%M"))
    os.makedirs(run_dir, exist_ok=True)

    all_targets, per_group, failed = [], [], []
    total = {k: 0 for k in ("행", "확정", "제외대상", "근접저장", "카테고리없음",
                            "이미삭제", "현황판미기록", "원장에없음")}
    total["상태별"] = {}
    big, frags = {}, {}

    def take(group, sid, t, s):
        all_targets.extend(t)
        per_group.append({"그룹": group, "sheetId": sid, "stats": s})
        for k in total:
            if k == "상태별":
                for kk, vv in s["상태별"].items():
                    total["상태별"][kk] = total["상태별"].get(kk, 0) + vv
            else:
                total[k] += s[k]
        for x in t:
            top = x["카테고리"].split(">")[0]
            big[top] = big.get(top, 0) + 1
            for f in x["조각전체"]:
                frags[f] = frags.get(f, 0) + 1
        near = " (근접 {})".format(s["근접저장"]) if s["근접저장"] else ""
        print("  원장 {} · 확정 {} · 제외대상 {}{}".format(
            s["행"], s["확정"], s["제외대상"], near))

    for i, (group, sid) in enumerate(groups, 1):
        print(f"[{i}/{len(groups)}] {group}", flush=True)
        try:
            t, s = scan_group(group, sid, gate, read_matrix=not args.no_matrix)
        except Exception as e:  # noqa: BLE001 — 한 그룹 실패가 전체를 멈추면 안 된다
            msg = f"{type(e).__name__}: {e}"[:200]
            print(f"  [실패] {msg}", file=sys.stderr)
            failed.append((group, sid, msg))
            continue
        take(group, sid, t, s)
        time.sleep(args.sleep)

    # 실패 그룹 재시도 — **조용히 빠지면 그 그룹 전체가 삭제 대상에서 누락된다.**
    # 실측(2026-08-09): gws 503 하나로 935행짜리 그룹이 통째로 빠져 제외 대상 235건이
    # 사라졌고, 합계만 보면 숫자가 줄어든 걸 오히려 정상으로 착각하기 쉬웠다.
    # `sheets_get` 자체 백오프(4회)를 이미 통과한 실패라 **다른 그룹을 다 돈 뒤** 다시 친다.
    for attempt in range(1, args.retry + 1):
        if not failed:
            break
        again, failed = failed, []
        print(f"\n실패 그룹 재시도 {attempt}/{args.retry} — {len(again)}개", flush=True)
        for group, sid, _msg in again:
            print(f"  {group}", flush=True)
            try:
                t, s = scan_group(group, sid, gate, read_matrix=not args.no_matrix)
            except Exception as e:  # noqa: BLE001
                msg = f"{type(e).__name__}: {e}"[:200]
                print(f"    [실패] {msg}", file=sys.stderr)
                failed.append((group, sid, msg))
                continue
            take(group, sid, t, s)
            time.sleep(args.sleep * 3)
    failed = [(g, m) for g, _sid, m in failed]

    total["그룹"] = len(per_group)
    total["실패그룹"] = len(failed)
    total["비율"] = (total["제외대상"] / total["확정"]) if total["확정"] else 0.0

    # --- 경고 ---
    warnings = []
    if failed:
        # 이건 "조금 덜 셌다"가 아니라 **그 그룹의 삭제 대상이 통째로 빠졌다**는 뜻이다.
        # 합계만 보면 숫자가 줄어든 게 정상처럼 보이므로 맨 앞에 세운다.
        warnings.append(
            f"**그룹 {len(failed)}개를 못 읽었다 — 그 그룹의 제외 대상은 이 결과에 없다.** "
            + ", ".join(g for g, _ in failed)
            + ". 재시도 후에도 실패한 것이므로 `scan` 을 다시 돌려 채워야 한다.")
    if total["비율"] > args.max_ratio:
        warnings.append(
            f"**대상 비율 {total['비율']:.1%} 가 상한 {args.max_ratio:.0%} 를 넘었다** — "
            "블랙리스트가 오염됐거나 대분류급 조각이 과매칭 중일 수 있다. "
            "`apply` 는 이 상태에서 거부한다(`--max-ratio` 로 조정).")
    for f, n in _top(frags, 5):
        if total["제외대상"] and n / total["제외대상"] >= FRAG_WARN_RATIO:
            warnings.append(
                f"조각 `{f}` 하나가 대상의 {n / total['제외대상']:.0%}({n}건)를 만든다"
                + (" — **대분류급 조각**이다." if is_broad_fragment(f) else "."))
    broad_hits = sum(n for f, n in frags.items() if is_broad_fragment(f))
    if broad_hits:
        warnings.append(f"대분류급 조각('>' 없음)이 만든 매치 {broad_hits}건 "
                        "(한 상품이 여러 조각에 걸리면 중복 계수).")

    result = {
        "생성": datetime.datetime.now().isoformat(timespec="seconds"),
        "블랙리스트": bl["경로"], "조각수": len(bl[SHEET_CAT]),
        "run_dir": run_dir, "합계": total, "그룹": per_group,
        "대분류별": big, "조각별": frags, "실패": failed,
    }

    _dump(os.path.join(run_dir, "scan.json"), result)
    _dump(os.path.join(run_dir, "targets.json"), all_targets)
    report = build_report(result, warnings)
    with open(os.path.join(run_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\n{'=' * 60}")
    print(f"확정 {total['확정']}건 중 **제외 대상 {total['제외대상']}건 "
          f"({total['비율']:.1%})** · 근접저장 {total['근접저장']}건")
    for w in warnings:
        print(f"  ⚠ {w}")
    print(f"\n리포트 -> {os.path.join(run_dir, 'report.md')}")
    print(f"###GATESCAN### " + json.dumps(
        {k: total[k] for k in ("그룹", "행", "확정", "제외대상", "근접저장")},
        ensure_ascii=False))
    return 2 if total["비율"] > args.max_ratio else 0


def _dump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _by_group(targets):
    """[{...}] → {(그룹, sheetId): [대상...]} — 시트 쓰기·삭제 배치가 둘 다 그룹 단위다."""
    out = {}
    for t in targets:
        out.setdefault((t.get("그룹", ""), t["sheetId"]), []).append(t)
    return out


def _make_queue(targets, batch_size=50):
    """삭제 대상 → `bulsaja_market_delete` 배치. **그룹 경계를 넘지 않게** 묶는다.

    배치가 통째로 실패했을 때 되돌릴 단위가 마켓그룹이라, 한 배치에 두 그룹이 섞이면
    실패 기록도 두 그룹에 걸친다.
    """
    out = []
    for (group, sid), ts in _by_group(targets).items():
        for j in range(0, len(ts), batch_size):
            chunk = ts[j:j + batch_size]
            out.append({
                "그룹": group, "sheetId": sid,
                "productIds": [c["productId"] for c in chunk],
                "상품": [{"productId": c["productId"], "상품명": c.get("상품명", ""),
                        "카테고리": c.get("카테고리", ""), "조각": c.get("조각", ""),
                        "근접저장": c.get("근접저장", False)} for c in chunk],
            })
    return out


def pending_delete_ids(m):
    """현황판에서 `삭제대기(제외카테고리)` 인 상품id — 7열 중 **하나라도** 걸리면 잡는다.

    하나라도로 보는 이유: `apply` 가 열 7개를 순서대로 쓰다 중간에 실패하면 그 상품은
    일부 열만 차 있다. 전부 일치로 보면 그 상품이 영영 재시도에 안 걸린다.
    """
    return [pid for pid, rec in m.items()
            if any((rec.get(t) or "").strip() == V_PENDING for t in GATED_TASKS)]


# ---------------------------------------------------------------------------
# 붙박이 게이트 API — catfix 저장부(bulsaja_mcp.apply · category_steer)가 부른다
# ---------------------------------------------------------------------------

def gate_dir(run_dir):
    """catfix run-dir 안의 게이트 산출물 자리. run-dir 자체를 쓰지 않는 이유는
    `targets.json` 이 catfix 의 대상 목록과 이름이 겹치기 때문이다. 한 칸 내려 두면
    `finalize --run-dir <catfix run-dir>/gate` 가 스캔과 똑같이 동작한다."""
    return os.path.join(run_dir, "gate")


def gate_select(records, gate, m=None):
    """순수 판정 — 저장된 카테고리로 삭제 대상을 고른다. 시트를 건드리지 않는다.

    records = [{productId, 상품명, 카테고리, 근접저장(선택), 상태(선택)}]
    **호출자가 확정 건만 넣는다** — 상태 판정(`CATFIX_DONE`)은 저장부가 하는 일이고
    여기까지 오면 "카테고리가 방금 확정된 상품"이라는 계약이다(의심 건은 삭제하지 않는다).

    반환: (targets, stats)
    """
    targets = []
    stats = {"판정": 0, "제외대상": 0, "카테고리없음": 0, "이미삭제": 0, "현황판없음": 0}
    for r in records:
        pid = str(r.get("productId") or "").strip()
        if not pid:
            continue
        stats["판정"] += 1
        cat = str(r.get("카테고리") or "").strip()
        if not _is_path(cat):
            stats["카테고리없음"] += 1
            continue
        hits = gate.hits(cat)
        if not hits:
            continue
        rec = (m or {}).get(pid)
        if rec is not None and already_gone(rec):
            stats["이미삭제"] += 1
            continue
        # 현황판에 행이 없으면 표시를 못 한다. 그래도 **삭제 대상에서는 빼지 않는다** —
        # `matrix.pending` 이 현황판을 도니 비용은 어차피 0이고, 안 지우면 재고만 남는다.
        no_row = m is not None and rec is None
        if no_row:
            stats["현황판없음"] += 1
        stats["제외대상"] += 1
        targets.append({
            "productId": pid, "상품명": r.get("상품명", ""), "카테고리": cat,
            "상태": r.get("상태", ""), "조각": hits[0], "조각전체": hits,
            "근접저장": bool(r.get("근접저장")), "현황판없음": no_row,
        })
    return targets, stats


def _merge_targets(old, new):
    """같은 run-dir 에 여러 번 붙는 게이트 결과를 productId 기준으로 합친다(나중이 이긴다).

    catfix 한 런에서 게이트가 최소 두 번 돈다(apply 저장분 → steer 저장분). 덮어쓰면
    앞엣것이 사라지고, 그냥 이어붙이면 같은 상품이 배치에 두 번 든다.
    """
    by_pid = {t["productId"]: t for t in old}
    for t in new:
        by_pid[t["productId"]] = t
    return list(by_pid.values())


def gate_records(sheet_id, records, run_dir=None, m=None, group="", blacklist=None,
                 batch_size=50, col_sleep=0.6, log=print):
    """**붙박이 게이트** — 방금 카테고리가 확정된 상품 중 제외 조각에 걸린 것을 잡는다.

    하는 일 셋: ① 판정 ② 현황판 뒤 7열에 `삭제대기(제외카테고리)` ③ 삭제 큐 갱신.
    실제 삭제는 여기서 하지 않는다 — 선례 3곳과 같이 **메인이 MCP 로** 부른다
    (`delete_queue.json` → `finalize`).

    **② 에서 비용 차단이 끝난다.** `matrix.pending` 은 빈칸만 고르므로 값이 차 있기만
    하면 상품명·옵션·썸네일·상세가 코드 추가 없이 건너뛴다. 삭제가 잠금으로 늦어져도
    다음 단계는 기다릴 필요가 없다.

    `m`(현황판 캐시)을 주면 **쓴 값을 그 자리에 반영**한다. 호출자가 같은 캐시로
    이어서 다른 열을 쓰기 때문이다 — 반영하지 않으면 다음 `mark_many` 가 옛 값으로
    열을 통째로 되써서 방금 찍은 표시를 지운다(`matrix.mark_many` 는 캐시를 정본으로 본다).

    반환: (targets, stats). 예외는 삼키지 않는다 — 호출자가 "저장은 끝났다"는 맥락에서
    경고로 낮출지 결정한다(§호출부 주석).
    """
    gate = category_gate(blacklist)
    if m is None:
        m = matrix.read(sheet_id)
    targets, stats = gate_select(records, gate, m)
    if not targets:
        return targets, stats

    for t in targets:
        t.setdefault("그룹", group)
        t.setdefault("sheetId", sheet_id)

    vals = {t["productId"]: V_PENDING for t in targets if not t["현황판없음"]}
    if vals:
        for task in GATED_TASKS:
            matrix.mark_many(sheet_id, task, vals, matrix=m)
            for pid in vals:            # 캐시 동기화 — 위 docstring 참조
                m[pid][task] = V_PENDING
            time.sleep(col_sleep)       # 쓰기 쿼터(분당 60) 여유
    near = sum(1 for t in targets if t["근접저장"])
    log(f"  [게이트] 제외카테고리 {len(targets)}건 → '{V_PENDING}' "
        f"(근접저장 {near}건 · 현황판없음 {stats['현황판없음']}건)")
    for t in targets[:5]:
        log(f"    {t['productId']} {t['상품명'][:24]} | {t['카테고리']} ← `{t['조각']}`")
    if len(targets) > 5:
        log(f"    … 외 {len(targets) - 5}건")

    if run_dir:
        gd = gate_dir(run_dir)
        os.makedirs(gd, exist_ok=True)
        tpath = os.path.join(gd, "targets.json")
        old = _load(tpath) if os.path.exists(tpath) else []
        allt = _merge_targets(old, targets)
        _dump(tpath, allt)
        _dump(os.path.join(gd, "delete_queue.json"), _make_queue(allt, batch_size))
        log(f"  [게이트] 삭제 큐 {len(allt)}건 -> {gd}")
    else:
        log("  [게이트] run-dir 이 없어 삭제 큐를 남기지 않았다 — "
            "시트의 `삭제대기` 는 `category_gate.py retry` 가 잡는다")
    return targets, stats


def queue_pending_deletes(sheet_id, run_dir=None, group="", batch_size=50, m=None,
                          log=print):
    """**런 시작 청소** — 지난 게이트가 잡았지만 아직 안 지워진 상품을 큐에 다시 올린다.

    삭제는 *"다른 작업이 처리 중인 상품은 삭제 불가"* 로 되돌아오는 일이 흔하다.
    그래서 그 그룹을 다시 돌릴 때 앞단에서 먼저 청소한다(2026-08-08 이룸님 — 자동 훅과
    단독 명령 둘 다). 시트는 이미 `삭제대기` 라 다시 쓰지 않는다. 큐만 만든다.
    """
    if m is None:
        m = matrix.read(sheet_id)
    pids = pending_delete_ids(m)
    targets = [{"productId": p, "그룹": group, "sheetId": sheet_id,
                "상품명": (m[p].get("상품") or ""), "카테고리": "", "상태": "",
                "조각": "(재시도)", "조각전체": [], "근접저장": False,
                "현황판없음": False} for p in pids]
    if not targets:
        return targets
    log(f"  [게이트] 미삭제 잔여 {len(targets)}건 — 삭제 큐로 재수집")
    if run_dir:
        gd = gate_dir(run_dir)
        os.makedirs(gd, exist_ok=True)
        tpath = os.path.join(gd, "targets.json")
        old = _load(tpath) if os.path.exists(tpath) else []
        allt = _merge_targets(old, targets)
        _dump(tpath, allt)
        _dump(os.path.join(gd, "delete_queue.json"), _make_queue(allt, batch_size))
        log(f"  [게이트] 삭제 큐 {len(allt)}건 -> {gd}")
    return targets


# ---------------------------------------------------------------------------
# apply — 현황판 7열 표시 + 삭제 큐 생성
# ---------------------------------------------------------------------------

def cmd_apply(args):
    """현황판 뒤 7열에 `삭제대기(제외카테고리)` 를 찍고 삭제 큐를 만든다.

    **여기서 비용 차단이 끝난다.** `matrix.pending` 은 빈칸만 고르므로(`_shared/스킬-계약.md:78`)
    값이 차 있기만 하면 상품명·옵션·썸네일·상세가 코드 추가 없이 건너뛴다. 실제 삭제가
    잠금으로 늦어져도 상품명 런은 기다릴 필요가 없다.

    **먼저 찍는 값이 `상품삭제(…)` 가 아니라 `삭제대기(…)` 인 이유** — 선례(pname 실물불명)는
    `상품삭제` 를 먼저 찍고 지운다. 그건 건수가 적어서 성립한다. 여기는 수백 건 배치인데
    삭제 잠금이 흔한 실패 모드라(`bulsaja-option-cleanup/SKILL.md:288`), 먼저 `상품삭제` 를
    찍으면 **안 지워진 상품이 지워졌다고 기록**된다. 성공분만 `finalize` 가 승격한다.
    """
    run_dir = args.run_dir
    targets = _load(os.path.join(run_dir, "targets.json"))
    scan = _load(os.path.join(run_dir, "scan.json"))
    if not targets:
        print("대상이 없습니다.")
        return 0

    # 못 읽은 그룹이 있으면 targets.json 은 **그 그룹만큼 짧다.** 그대로 apply 하면
    # 빠진 그룹 상품이 빈칸으로 남아 상품명·옵션·썸네일 대상으로 그대로 넘어간다 —
    # 막으려던 비용이 조용히 나가는 경로다. `--allow-partial` 로만 넘긴다.
    if scan.get("실패") and not args.allow_partial:
        print(f"[거부] scan 이 그룹 {len(scan['실패'])}개를 못 읽었습니다 — "
              "그 그룹의 제외 대상이 목록에 없습니다: "
              + ", ".join(g for g, _ in scan["실패"]), file=sys.stderr)
        print("  `scan` 을 다시 돌려 채우거나, 알고도 진행하려면 --allow-partial",
              file=sys.stderr)
        return 1

    ratio = scan["합계"]["비율"]
    if ratio > args.max_ratio:
        print(f"[거부] 대상 비율 {ratio:.1%} 가 상한 {args.max_ratio:.0%} 를 넘습니다. "
              f"블랙리스트를 확인하거나 --max-ratio 를 올리세요.", file=sys.stderr)
        return 1

    groups = _by_group(targets)
    if args.only:
        groups = {k: v for k, v in groups.items() if args.only in k[0]}
        targets = [t for ts in groups.values() for t in ts]
        if not groups:
            print(f"[중단] '{args.only}' 에 맞는 그룹이 없습니다.", file=sys.stderr)
            return 1
    print(f"대상 {len(targets)}건 / {len(groups)}그룹 · 근접저장 "
          f"{sum(1 for t in targets if t['근접저장'])}건")
    print(f"찍을 열 {len(GATED_TASKS)}개: {' · '.join(GATED_TASKS)} → '{V_PENDING}'")
    print("(카테고리 열은 건드리지 않습니다 — 실제로 확정된 사실입니다)")
    if not args.yes:
        for (g, _sid), ts in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:10]:
            print(f"  {g}: {len(ts)}건")
        print("\n실제로 찍으려면 --yes 를 붙이세요(요약만 출력했습니다).")
        return 0

    queue, marked, failed = [], 0, []
    for i, ((group, sid), ts) in enumerate(groups.items(), 1):
        pids = [t["productId"] for t in ts]
        print(f"[{i}/{len(groups)}] {group} — {len(pids)}건", flush=True)
        try:
            m = matrix.read(sid)
            vals = {p: V_PENDING for p in pids if p in m}
            missing = [p for p in pids if p not in m]
            if missing:
                print(f"  [주의] 현황판에 없는 상품 {len(missing)}건 — 시트 표시를 건너뜁니다")
            for task in GATED_TASKS:
                matrix.mark_many(sid, task, vals, matrix=m)
                # 쓰기 쿼터는 분당 60회다. 열 7개 × 그룹 47개인데 열 하나가 청크 2개로
                # 쪼개지는 그룹도 있어(1000행 × ~15자 > 12000자 예산) 실제 호출은 600회를
                # 넘는다. `sheets_update` 에 백오프가 있지만 429 를 맞고 나서 기다리는 것보다
                # 안 맞는 게 싸다.
                time.sleep(args.col_sleep)
            marked += len(vals)
        except Exception as e:  # noqa: BLE001 — 한 그룹 실패가 전체를 멈추면 안 된다
            msg = f"{type(e).__name__}: {e}"[:200]
            print(f"  [실패] 현황판 표시: {msg}", file=sys.stderr)
            failed.append((group, msg))
            continue
        queue.extend(_make_queue(ts, args.batch_size))
        time.sleep(args.sleep)

    _dump(os.path.join(run_dir, "delete_queue.json"), queue)
    print(f"\n현황판 표시 {marked}건 · 삭제 배치 {len(queue)}개")
    if failed:
        # 열 7개 중 일부만 쓰고 실패했을 수 있다 → 그 상품은 남은 열이 빈칸이라
        # 그 스킬들이 다시 집어간다. `apply` 는 같은 값을 다시 쓰는 멱등 연산이므로
        # 그냥 다시 돌리면 이어서 채워진다. 실패 그룹만 `--only` 로 좁힐 수 있다.
        print(f"  표시 실패 그룹 {len(failed)}개: " + ", ".join(g for g, _ in failed))
        print("  → 그 그룹은 열이 일부만 찼을 수 있습니다. "
              f"`apply --run-dir {run_dir} --yes --only <그룹>` 로 다시 돌리세요(멱등).")
        print("  (삭제 큐에는 안 넣었습니다 — 기록하지 못한 걸 지우지 않습니다)")
    print(f"큐 -> {os.path.join(run_dir, 'delete_queue.json')}")
    print("  다음: 메인이 배치마다 bulsaja_market_delete "
          "{productIds, scope:'ALL', deleteAction:'MARKET_AND_SOURCE'} (확인키 2단계) →")
    print(f"  결과를 delete_results.json 으로 남기고 `finalize --run-dir {run_dir}`")
    print("###GATEAPPLY### " + json.dumps(
        {"표시": marked, "배치": len(queue), "실패그룹": len(failed)}, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# delete — 큐를 실제로 지운다 (스크립트가 MCP 를 직접 부른다)
# ---------------------------------------------------------------------------
#
# **선례 3곳(pname 실물불명 · 썸네일 §404 · 옵션 삭제후보)은 "메인이 MCP 호출" 이다.**
# 여기만 다른 이유는 규모다 — 12,486건이면 확인키 2단계 + 작업번호 전건 사후 조회로
# 호출이 800회쯤 되고 응답이 전부 메인 컨텍스트에 쌓인다(2026-08-09 이룸님).
#
# 실측 응답 형태(2026-08-09, 293건 1그룹) — 다섯 가지다:
#   ① `삭제 대기열 접수됨` + taskId (198) — **접수일 뿐 성공이 아니다.** 작업번호로 확정한다
#   ② `삭제 작업 원자적 생성 실패로 전체 그룹 미접수` (67) — 배치 안 한 건 때문에 **배치 전체**가
#      미접수. 상품 자체의 문제가 아니므로 **더 작은 배치로 재제출**하면 대부분 통과한다
#   ③ `업로드된 마켓이 없고 이미 휴지통인 상품을 확인함` (24) — **이미 지워져 있다.**
#      실패가 아니라 목적 달성이다. 성공으로 센다(안 그러면 영영 `삭제대기` 로 남는다)
#      ③의 형제 문구가 하나 더 있다(2026-08-14 실측):
#      `업로드된 마켓이 없어 소싱 상품을 휴지통으로 이동함` — "이미 있었다"가 아니라
#      "지금 옮겼다"라 `이미 휴지통` 에 안 걸려 **성공을 실패로 셌다.** 둘 다 결과는
#      "휴지통에 있다"로 같으므로 함께 잡는다
#   ④ `잠금된 상품은 삭제 불가` (4) — 이룸님이 앱에서 건 삭제 잠금. 재시도 무의미
#   ⑤ 그 밖 — 사유 그대로 실패
# 결과는 **상품 단위**로 온다 — 배치 통째 실패로 뭉뚱그리지 않는다.

DELETE_TOOL = "bulsaja_market_delete"
TASKS_TOOL = "bulsaja_upload_tasks"
LOCK_MARK = "잠금"
QUEUED_MARK = "접수"
GONE_MARKS = ("이미 휴지통", "휴지통으로 이동")  # ③ 휴지통에 있다(이미 있었든, 방금 갔든)
NOT_GONE_MARKS = ("이동 실패", "이동하지", "이동 불가")  # 위 문구의 부정형 — 성공이 아니다
UNQUEUED_MARK = "미접수"       # ② 배치 원자성 실패 — 재제출 대상
TASK_QUERY_MAX = 50            # upload_tasks 의 taskIds 상한
TASK_FINAL = ("성공", "실패")  # 그 밖(대기·진행중)은 아직 안 끝난 것
DELETE_ARGS = {"scope": "ALL", "deleteAction": "MARKET_AND_SOURCE"}


def _rows(resp, key="결과"):
    v = (resp or {}).get(key)
    return v if isinstance(v, list) else []


def _is_gone(res):
    """응답 문구가 "그 상품은 휴지통에 있다"를 뜻하는가 (③ 및 그 형제 문구).

    부정형("휴지통으로 이동 실패")을 먼저 걸러야 한다 — 부분일치라 그냥 두면
    실패를 성공으로 뒤집는다.
    """
    s = str(res or "")
    if any(n in s for n in NOT_GONE_MARKS):
        return False
    return any(g in s for g in GONE_MARKS)


def delete_batch(mcp, product_ids, log=print):
    """확인키 2단계로 배치 1개를 제출 → [{productId, 판정, 사유, taskId}].

    판정: `접수`(taskId 있음) / `잠금` / `실패`. 여기서는 **성공을 말하지 않는다** —
    접수는 접수일 뿐이라 `verify_tasks` 가 확정한다.
    """
    args = dict(DELETE_ARGS, productIds=list(product_ids), confirm=True)
    plan = mcp.call_tool(DELETE_TOOL, args)
    token = (plan or {}).get("confirmationToken")
    if not token:
        # 확인키가 안 나오면 실행 계획 단계에서 막힌 것이다 — 배치 전원 실패로 남긴다.
        msg = str((plan or {}).get("message") or plan)[:160]
        return [{"productId": p, "판정": "실패", "사유": f"확인키 미발급: {msg}",
                 "taskId": ""} for p in product_ids]

    done = mcp.call_tool(DELETE_TOOL, dict(args, confirmationToken=token))
    by_pid = {}
    for r in _rows(done):
        pid = str(r.get("productId") or "").strip()
        if not pid:
            continue
        res = str(r.get("결과") or "")
        tid = str(r.get("taskId") or "")
        if LOCK_MARK in res:
            j = "잠금"
        elif _is_gone(res):
            j = "이미없음"          # 실패가 아니다 — 휴지통에 있다
        elif UNQUEUED_MARK in res:
            j = "미접수"            # 배치 원자성 실패 — 더 작게 재제출하면 통과한다
        elif tid and QUEUED_MARK in res:
            j = "접수"
        else:
            j = "실패"
        by_pid[pid] = {"productId": pid, "판정": j, "사유": res or "사유 없음",
                       "taskId": tid if j == "접수" else ""}
    # 응답에 아예 안 실린 상품 — 조용히 성공으로 보지 않는다.
    miss = str((done or {}).get("message") or "")[:120]
    for p in product_ids:
        by_pid.setdefault(p, {"productId": p, "판정": "실패",
                              "사유": f"응답에 없음: {miss}", "taskId": ""})
    return [by_pid[p] for p in product_ids]


def verify_tasks(mcp, task_map, rounds=8, interval=45, log=print):
    """{taskId: productId} → {productId: (성공?, 사유)}. `upload_tasks` 로 확정한다.

    **접수 ≠ 성공.** 실측(2026-08-09): 198건을 접수하고 60초 뒤 한 번 조회했더니
    성공 0 · 대기 30 · 조회에 아예 안 잡힘 168 이었다. 대기열이 그때까지 안 돈 것뿐인데
    한 번만 보고 끝내면 **전부 실패로 기록**된다. 그래서 **끝난 것만 확정하고 나머지는
    다시 본다** — 상태가 `성공`·`실패` 인 것만 종결로 취급한다.

    끝까지 안 잡히는 작업은 성공으로 올리지 않고 `미확정` 으로 남긴다. `삭제대기` 로 남으므로
    비용은 계속 0이고, 다음 실행이나 `retry` 가 다시 잡는다 — 조용히 성공 처리하는 것보다 낫다.
    """
    pend = dict(task_map)
    out = {}
    for rnd in range(1, rounds + 1):
        if not pend:
            break
        ids = list(pend)
        seen = set()
        for i in range(0, len(ids), TASK_QUERY_MAX):
            resp = mcp.call_tool(TASKS_TOOL,
                                 {"mode": "list", "taskIds": ids[i:i + TASK_QUERY_MAX]})
            for r in _rows(resp, "마켓작업"):
                tid = str(r.get("taskId") or "")
                if tid not in pend or tid in seen:
                    continue      # 이 조회는 무관한 최근 작업도 같이 돌려준다
                st = str(r.get("상태") or "")
                if st not in TASK_FINAL:
                    continue      # 대기·진행중 — 아직 끝나지 않았다
                seen.add(tid)
                out[pend[tid]] = (st == "성공", st if st == "성공"
                                  else f"{st}: {r.get('실패사유', '')}"[:160])
        for tid in seen:
            pend.pop(tid, None)
        log(f"    확정 {len(out)}/{len(task_map)} · 남은 {len(pend)} (조회 {rnd}/{rounds})")
        if pend and rnd < rounds:
            time.sleep(interval)
    for pid in pend.values():
        out.setdefault(pid, (False, "미확정(대기열이 아직 안 끝남 — 재실행하면 다시 확인한다)"))
    return out


def cmd_delete(args):
    """`delete_queue.json` 을 실제로 지우고 `delete_results.json` 을 만든다.

    배치마다 `delete_progress.jsonl` 에 **즉시** 한 줄 남긴다 — 중간에 죽어도
    `--resume` 이 거기서 이어받는다. 삭제는 되돌리기 어려운 방향이라 "어디까지 했나"를
    메모리에만 두면 안 된다.
    """
    run_dir = args.run_dir
    queue = _load(os.path.join(run_dir, "delete_queue.json"))
    if args.only:
        queue = [b for b in queue if args.only in b["그룹"]]
    if not queue:
        print("삭제할 배치가 없습니다.")
        return 0

    prog_path = os.path.join(run_dir, "delete_progress.jsonl")
    done_batches, records = set(), []
    if args.resume and os.path.exists(prog_path):
        with open(prog_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                done_batches.add(d["배치키"])
                records.extend(d["결과"])
        print(f"이어하기: 이미 제출한 배치 {len(done_batches)}개 · 상품 {len(records)}건")

    todo = [(i, b) for i, b in enumerate(queue)
            if f"{b['그룹']}#{i}" not in done_batches]
    n_items = sum(len(b["productIds"]) for _i, b in todo)
    print(f"제출할 배치 {len(todo)}개 · 상품 {n_items}건 "
          f"(그룹 {len({b['그룹'] for _i, b in todo})}개)")
    if not args.yes:
        print("\n실제로 삭제하려면 --yes 를 붙이세요(요약만 출력했습니다).")
        return 0

    from eroomlib.bulsaja import BulsajaMCP
    mcp = BulsajaMCP()
    mcp.open()
    try:
        for n, (i, b) in enumerate(todo, 1):
            key = f"{b['그룹']}#{i}"
            print(f"[{n}/{len(todo)}] {b['그룹']} — {len(b['productIds'])}건", flush=True)
            try:
                res = delete_batch(mcp, b["productIds"])
            except Exception as e:  # noqa: BLE001 — 한 배치 실패가 전체를 멈추면 안 된다
                msg = f"{type(e).__name__}: {e}"[:160]
                print(f"  [오류] {msg}", file=sys.stderr)
                res = [{"productId": p, "판정": "실패", "사유": msg, "taskId": ""}
                       for p in b["productIds"]]
            c = {}
            for r in res:
                c[r["판정"]] = c.get(r["판정"], 0) + 1
            print("  " + " · ".join(f"{k} {v}" for k, v in sorted(c.items())))
            records.extend(res)
            with open(prog_path, "a", encoding="utf-8") as f:  # 즉시 flush 되는 append
                f.write(json.dumps({"배치키": key, "그룹": b["그룹"], "결과": res},
                                   ensure_ascii=False) + "\n")
            time.sleep(args.sleep)

        # --- 미접수 재제출 ---
        # `원자적 생성 실패로 전체 그룹 미접수` 는 배치 안 한 건 때문에 배치 전체가 막힌
        # 것이라 **상품 자체의 문제가 아니다**. 실측 293건 중 67건(23%)이 이것이었다.
        # 더 작은 배치로 다시 내면 막은 한 건만 남고 나머지는 통과한다.
        unq = [r["productId"] for r in records if r["판정"] == UNQUEUED_MARK]
        if unq and args.retry_size > 0:
            print(f"\n미접수 {len(unq)}건 재제출 (배치 {args.retry_size}건씩)", flush=True)
            redo = {}
            for i in range(0, len(unq), args.retry_size):
                chunk = unq[i:i + args.retry_size]
                try:
                    for r in delete_batch(mcp, chunk):
                        redo[r["productId"]] = r
                except Exception as e:  # noqa: BLE001
                    msg = f"{type(e).__name__}: {e}"[:160]
                    for p in chunk:
                        redo[p] = {"productId": p, "판정": "실패", "사유": msg, "taskId": ""}
                time.sleep(args.sleep)
            records = [redo.get(r["productId"], r) if r["판정"] == UNQUEUED_MARK else r
                       for r in records]
            with open(prog_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"배치키": "재제출#미접수", "그룹": "(재제출)",
                                    "결과": list(redo.values())}, ensure_ascii=False) + "\n")
            c = {}
            for r in redo.values():
                c[r["판정"]] = c.get(r["판정"], 0) + 1
            print("  " + " · ".join(f"{k} {v}" for k, v in sorted(c.items())))

        # --- 접수분 확정 ---
        task_map = {r["taskId"]: r["productId"] for r in records
                    if r["판정"] == "접수" and r["taskId"]}
        if task_map:
            print(f"\n접수 {len(task_map)}건 — 대기열 소진 대기 {args.settle}초 후 확인",
                  flush=True)
            time.sleep(args.settle)
            verdict = verify_tasks(mcp, task_map,
                                   rounds=args.poll, interval=args.poll_interval)
        else:
            verdict = {}
    finally:
        mcp.close()

    ok, ng = [], []
    for r in records:
        pid = r["productId"]
        if r["판정"] == "접수":
            good, why = verdict.get(pid, (False, "미확정"))
            (ok.append(pid) if good else ng.append({"productId": pid, "사유": why}))
        elif r["판정"] == "이미없음":
            # 목적은 "이 상품이 불사자에 없을 것" 이다. 이미 없으면 달성된 것 —
            # 실패로 세면 영영 `삭제대기` 로 남아 재시도기가 계속 집어간다.
            ok.append(pid)
        else:
            ng.append({"productId": pid, "사유": f"{r['판정']}: {r['사유']}"[:160]})

    _dump(os.path.join(run_dir, "delete_results.json"), {"성공": ok, "실패": ng})
    c = {}
    for x in ng:
        head = x["사유"].split(":")[0]
        c[head] = c.get(head, 0) + 1
    print(f"\n삭제 성공 {len(ok)}건 · 실패 {len(ng)}건")
    for k, v in sorted(c.items(), key=lambda kv: -kv[1]):
        print(f"    {k}: {v}건")
    print(f"결과 -> {os.path.join(run_dir, 'delete_results.json')}")
    print(f"  다음: `finalize --run-dir {run_dir}` (성공분만 승격)")
    print("###GATEDELETE### " + json.dumps(
        {"성공": len(ok), "실패": len(ng)}, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# finalize — 삭제 성공분만 승격
# ---------------------------------------------------------------------------

def cmd_finalize(args):
    """`delete_results.json` 의 성공분만 `상품삭제(제외카테고리·자동)` 로 올린다.

    실패분은 `삭제대기(제외카테고리)` 그대로 둔다 — **빈칸으로 되돌리면 안 된다.**
    빈칸을 보는 건 게이트가 아니라 일반 작업 스킬들이라(`matrix.pending`), 되돌리는 순간
    상품명·옵션·썸네일 비용이 그대로 나간다(막으려던 것과 정반대). 그리고 catfix 는 그
    상품을 다시 안 잡는다 — 대상 선정이 "G열이 찬 행은 건너뛴다"인데 삭제가 실패해도
    G열은 `자동저장완료` 그대로다. 잡는 주체는 일반 스킬이 아니라 `retry` 다.
    """
    run_dir = args.run_dir
    path = args.results or os.path.join(run_dir, "delete_results.json")
    if not os.path.exists(path):
        print(f"[중단] 삭제 결과 파일이 없습니다: {path}\n"
              '  형식: {"성공": ["<id>"...], "실패": [{"productId":"<id>","사유":"..."}]}',
              file=sys.stderr)
        return 1
    res = _load(path)
    ok = {str(p).strip() for p in res.get("성공", [])}
    ng = {str(x.get("productId", "")).strip(): x.get("사유", "")
          for x in res.get("실패", []) if x.get("productId")}
    targets = _load(os.path.join(run_dir, "targets.json"))
    print(f"삭제 성공 {len(ok)}건 · 실패 {len(ng)}건 (대상 {len(targets)}건)")

    unknown = ok - {t["productId"] for t in targets}
    if unknown:
        print(f"  [주의] 대상 목록에 없는 성공 id {len(unknown)}건 — 무시합니다")

    promoted = 0
    for (group, sid), ts in _by_group(targets).items():
        vals = {t["productId"]: V_DELETED for t in ts if t["productId"] in ok}
        if not vals:
            continue
        try:
            m = matrix.read(sid)
            for task in GATED_TASKS:
                matrix.mark_many(sid, task, vals, matrix=m)
                time.sleep(args.col_sleep)   # apply 와 같은 이유 — 쓰기 쿼터
            promoted += len(vals)
            print(f"  {group}: {len(vals)}건 승격")
        except Exception as e:  # noqa: BLE001
            print(f"  [실패] {group}: {type(e).__name__}: {e}"[:160], file=sys.stderr)
        time.sleep(args.sleep)

    # 종합보고에 실을 목록 — 삭제분과 잔여 삭제대기분을 나눠 남긴다.
    deleted = [t for t in targets if t["productId"] in ok]
    pendingv = [dict(t, 실패사유=ng.get(t["productId"], ""))
                for t in targets if t["productId"] not in ok]
    _dump(os.path.join(run_dir, "deleted.json"), deleted)
    _dump(os.path.join(run_dir, "still_pending.json"), pendingv)
    near = sum(1 for t in deleted if t["근접저장"])
    print(f"\n승격 {promoted}건 (그중 근접저장 {near}건 — 종합보고에 구분 표기) · "
          f"잔여 삭제대기 {len(pendingv)}건")
    print("###GATEFINAL### " + json.dumps(
        {"삭제": len(deleted), "근접저장": near, "삭제대기": len(pendingv)},
        ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# auto_delete — 묻지 않고 끝까지 지운다 (런 출구에서 자동)
# ---------------------------------------------------------------------------
#
# **2026-08-11 이룸님: "삭제대기건은 나에게 묻지 말고 삭제한다."**
# 그전까지는 `apply` 까지만 자동이고(비용 차단), 실제 삭제는 메인이 큐를 보고 판단했다.
# 이제 catfix 런의 출구(`run_all.py auto`)가 이걸 부른다 — 물어보는 자리가 없어졌다.
#
# **라운드를 도는 이유는 서버 대기열이 병목이라서다**(§삭제는 서버 대기열이 병목이다).
# 한 번에 다 안 넘어가고 `미접수`·`미확정` 으로 남는데, 그건 상품 문제가 아니라 대기열이
# 그때까지 안 돈 것이다. 시간을 두고 다시 내면 넘어간다. 그래도 남으면 `삭제대기` 그대로
# 둔다 — 비용은 이미 0이고(현황판 7열이 차 있다) 다음 런의 `prep` 이 다시 잡는다.

# 재시도해도 소용없는 사유 — 다시 큐에 넣지 않는다.
NO_RETRY_MARKS = ("잠금",)


class _Args:
    """서브커맨드가 argparse 네임스페이스를 받게 되어 있어 쓰는 얇은 어댑터."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def _retryable(rec):
    why = str(rec.get("실패사유") or "")
    return not any(mark in why for mark in NO_RETRY_MARKS)


def auto_delete(gate_run_dir, rounds=3, wait=180, batch_size=50, log=print,
                settle=60, poll=8, poll_interval=45):
    """`delete → finalize → 잔여 재큐` 를 최대 `rounds` 번. 사람에게 묻지 않는다.

    라운드 2부터는 `<gate>/retryN/` 에 새 큐를 깔고 거기서 돈다 — 같은 자리에서 다시
    돌리면 `delete_progress.jsonl` 의 배치키가 겹쳐 `--resume` 이 전부 건너뛴다.
    반환: {"삭제": n, "잔여": n, "라운드": n}
    """
    q_path = os.path.join(gate_run_dir, "delete_queue.json")
    if not os.path.exists(q_path) or not _load(q_path):
        log("  [게이트] 삭제할 것이 없다 — 큐가 비었다")
        return {"삭제": 0, "잔여": 0, "라운드": 0}

    cur, deleted_all, rnd = gate_run_dir, 0, 0
    for rnd in range(1, rounds + 1):
        log(f"\n{'=' * 56}\n[게이트 자동삭제 {rnd}/{rounds}] {cur}", )
        try:
            cmd_delete(_Args(run_dir=cur, yes=True, only=None, resume=True,
                             sleep=0.5, settle=settle, poll=poll,
                             poll_interval=poll_interval, retry_size=10))
            cmd_finalize(_Args(run_dir=cur, results=None, sleep=0.3, col_sleep=0.6))
        except Exception as e:  # noqa: BLE001 — 삭제 실패가 교정 결과를 날리면 안 된다
            log(f"  [게이트] {rnd}라운드 실패 — {type(e).__name__}: {e}"[:200])
            break

        deleted_all += len(_load(os.path.join(cur, "deleted.json")))
        rest = [r for r in _load(os.path.join(cur, "still_pending.json"))
                if _retryable(r)]
        if not rest:
            log(f"  [게이트] 잔여 없음 — {rnd}라운드에서 끝")
            break
        if rnd >= rounds:
            log(f"  [게이트] 잔여 {len(rest)}건 — 라운드 소진. `삭제대기` 로 남긴다")
            break

        nxt = os.path.join(gate_run_dir, f"retry{rnd + 1}")
        os.makedirs(nxt, exist_ok=True)
        _dump(os.path.join(nxt, "targets.json"), rest)
        _dump(os.path.join(nxt, "delete_queue.json"), _make_queue(rest, batch_size))
        log(f"  [게이트] 잔여 {len(rest)}건 — {wait}초 뒤 재시도 ({nxt})")
        time.sleep(wait)
        cur = nxt

    still = _load(os.path.join(cur, "still_pending.json")) \
        if os.path.exists(os.path.join(cur, "still_pending.json")) else []
    log(f"\n[게이트 자동삭제 종료] 삭제 {deleted_all}건 · 잔여 삭제대기 {len(still)}건")
    print("###GATEAUTO### " + json.dumps(
        {"삭제": deleted_all, "잔여": len(still), "라운드": rnd}, ensure_ascii=False))
    return {"삭제": deleted_all, "잔여": len(still), "라운드": rnd}


def cmd_autodelete(args):
    auto_delete(args.run_dir, rounds=args.rounds, wait=args.wait,
                settle=args.settle, poll=args.poll, poll_interval=args.poll_interval)
    return 0


# ---------------------------------------------------------------------------
# retry — 삭제대기 잔여분 재수집
# ---------------------------------------------------------------------------

def cmd_retry(args):
    """현황판에서 `삭제대기(제외카테고리)` 를 긁어 삭제 큐를 다시 만든다.

    잠금은 다른 작업이 끝나면 풀리는 일시적 상태라 나중에 재시도하면 대개 성공한다.
    (원안: catfix 런 시작 때 자동 청소 + 이 단독 명령 — 둘 다 연다. 자동 훅은 게이트 구현 때)
    """
    groups = matrix.index_groups(args.master_sheet)
    if args.only:
        groups = [(g, s) for g, s in groups if args.only in g]
    run_dir = args.run_dir or os.path.join(
        _cfg("paths.data_root", required=True), "category-gate", "runs",
        datetime.datetime.now().strftime("%y%m%d-%H%M") + "-retry")
    os.makedirs(run_dir, exist_ok=True)

    queue, total = [], 0
    for i, (group, sid) in enumerate(groups, 1):
        try:
            m = matrix.read(sid)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(groups)}] {group} — 읽기 실패: {str(e)[:100]}", file=sys.stderr)
            continue
        # 7열 중 **하나라도** 삭제대기면 미삭제분이다(부분 표시된 그룹도 잡는다).
        pids = pending_delete_ids(m)
        if not pids:
            continue
        total += len(pids)
        print(f"[{i}/{len(groups)}] {group} — 삭제대기 {len(pids)}건")
        for j in range(0, len(pids), args.batch_size):
            chunk = pids[j:j + args.batch_size]
            queue.append({"그룹": group, "sheetId": sid, "productIds": chunk,
                          "상품": [{"productId": p, "상품명": m[p].get("상품", "")}
                                 for p in chunk]})
        time.sleep(args.sleep)

    _dump(os.path.join(run_dir, "delete_queue.json"), queue)
    _dump(os.path.join(run_dir, "targets.json"),
          [{"productId": p, "그룹": q["그룹"], "sheetId": q["sheetId"],
            "상품명": s.get("상품명", ""), "카테고리": "", "조각": "(재시도)",
            "조각전체": [], "근접저장": False, "상태": ""}
           for q in queue for p, s in zip(q["productIds"], q["상품"])])
    print(f"\n삭제대기 {total}건 · 배치 {len(queue)}개 -> {run_dir}")
    print(f"  다음: 메인이 삭제 → `finalize --run-dir {run_dir}`")
    print("###GATERETRY### " + json.dumps({"삭제대기": total, "배치": len(queue)},
                                          ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="제외카테고리 상품 게이트 — 재고 스캔")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="읽기만 — 삭제 대상 판정 + 리포트")
    s.add_argument("--only", help="그룹명에 이 문자열이 든 것만(소규모 검증용)")
    s.add_argument("--master-sheet", default=None)
    s.add_argument("--blacklist", default=None, help="기본: 드라이브 정본")
    s.add_argument("--run-dir", default=None)
    s.add_argument("--max-ratio", type=float, default=DEFAULT_MAX_RATIO)
    s.add_argument("--sleep", type=float, default=0.2, help="그룹 간 대기(읽기 쿼터)")
    s.add_argument("--retry", type=int, default=2, help="실패 그룹 재시도 횟수")
    s.add_argument("--no-matrix", action="store_true",
                   help="00_진행 을 안 읽는다(빠르지만 이미삭제·진단이 빠진다)")

    a = sub.add_parser("apply", help="현황판 7열에 삭제대기 표시 + 삭제 큐 생성")
    a.add_argument("--run-dir", required=True, help="scan 이 만든 run-dir")
    a.add_argument("--yes", action="store_true", help="실제로 시트에 쓴다(없으면 요약만)")
    a.add_argument("--only", help="그룹명에 이 문자열이 든 것만(검증·실패 재시도용)")
    a.add_argument("--allow-partial", action="store_true",
                   help="scan 이 못 읽은 그룹이 있어도 진행(그 그룹은 대상에서 빠진 채로)")
    a.add_argument("--max-ratio", type=float, default=DEFAULT_MAX_RATIO)
    a.add_argument("--batch-size", type=int, default=50, help="삭제 배치 크기")
    a.add_argument("--sleep", type=float, default=0.3, help="그룹 간 대기")
    a.add_argument("--col-sleep", type=float, default=0.6, help="작업 열 간 대기(쓰기 쿼터)")

    d = sub.add_parser("delete", help="삭제 큐를 실제로 지운다(스크립트가 MCP 직접 호출)")
    d.add_argument("--run-dir", required=True)
    d.add_argument("--yes", action="store_true", help="실제로 삭제한다(없으면 요약만)")
    d.add_argument("--only", help="그룹명에 이 문자열이 든 것만")
    d.add_argument("--resume", action="store_true",
                   help="delete_progress.jsonl 에 남은 배치는 건너뛴다")
    d.add_argument("--sleep", type=float, default=0.5, help="배치 간 대기")
    d.add_argument("--settle", type=float, default=60,
                   help="접수분 확정 조회 전 대기(초) — 대기열이 소진될 시간")
    d.add_argument("--poll", type=int, default=8, help="확정 조회 반복 횟수")
    d.add_argument("--poll-interval", type=float, default=45, help="확정 조회 간격(초)")
    d.add_argument("--retry-size", type=int, default=10,
                   help="`미접수`(배치 원자성 실패) 재제출 배치 크기. 0이면 재제출 안 함")

    f = sub.add_parser("finalize", help="삭제 성공분만 `상품삭제(…)` 로 승격")
    f.add_argument("--run-dir", required=True)
    f.add_argument("--results", default=None, help="기본: <run-dir>/delete_results.json")
    f.add_argument("--sleep", type=float, default=0.3, help="그룹 간 대기")
    f.add_argument("--col-sleep", type=float, default=0.6, help="작업 열 간 대기(쓰기 쿼터)")

    ad = sub.add_parser("autodelete",
                        help="delete→finalize→잔여 재큐 를 라운드로 (묻지 않는다)")
    ad.add_argument("--run-dir", required=True, help="게이트 run-dir (<catfix run-dir>/gate)")
    ad.add_argument("--rounds", type=int, default=3, help="최대 재시도 라운드")
    ad.add_argument("--wait", type=float, default=180, help="라운드 간 대기(초) — 대기열 소진")
    ad.add_argument("--settle", type=float, default=60)
    ad.add_argument("--poll", type=int, default=8)
    ad.add_argument("--poll-interval", type=float, default=45)

    r = sub.add_parser("retry", help="현황판의 `삭제대기` 잔여분으로 삭제 큐 재생성")
    r.add_argument("--only", help="그룹명에 이 문자열이 든 것만")
    r.add_argument("--master-sheet", default=None)
    r.add_argument("--run-dir", default=None)
    r.add_argument("--batch-size", type=int, default=50)
    r.add_argument("--sleep", type=float, default=0.2)

    args = ap.parse_args()
    sys.exit({"scan": cmd_scan, "apply": cmd_apply, "delete": cmd_delete,
              "finalize": cmd_finalize, "autodelete": cmd_autodelete,
              "retry": cmd_retry}[args.cmd](args))


if __name__ == "__main__":
    main()
