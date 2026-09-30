#!/usr/bin/env python3
"""쿠팡 웹 러너 — 관제탑 쿠팡 잡이 부르는 얇은 껍데기 (Phase 7 / CP-01~04).

  preview : prep → resolve → build → ship → gate → apply(미리보기) 를 한 run-dir 에서
            **자식 프로세스로** 차례로 돌린다. 비0 단계에서 멈춘다. 쓰기 0.
  commit  : gate 재조회(D-12) → 미리보기보다 늘어났으면 복사 0 · exit 5
            → 승인 ∩ 새 후보만 apply 커밋(--limit 항상) → verify → verified.json 의 중복0 판정.

**CLI 를 import 하지 않는다** — subprocess 로만 부른다. 자식 stdout 은 이 프로세스의
stdout(=잡 로그 파일)을 물려받아 웹 SSE tail 이 산다(RESEARCH §Pattern 1). gate·apply 만
줄을 받아 그대로 다시 찍으면서 요약에 옮길 줄을 캡처한다.
**기준 인자를 넘기지 않는다** — 마진·주문 기준과 그룹 대조 여부는 CLI 기본값
(workspace.toml [coupang])이 정본이다(L-04 · D-10 · D-15). 이 파일에 그 플래그 문자열이
나오면 테스트가 깨진다.

사용 (웹앱 argv.CoupangArgv 가 이 모양으로 조립한다):
  python coupang_web.py preview --run-dir R --expect-nick N --summary-out R/summary.json
  python coupang_web.py commit  --run-dir R --approved R/approved_<잡id>.json --limit L \\
      --expect-nick N --summary-out R/commit_summary_<잡id>.json

commit 은 미리보기 요약을 R/summary.json (고정 이름)에서 읽는다. approved = JSON 배열 [대표pid…]

종료코드:
  0 = 정상 · 1 = 예기치 못한 실패(verify 중복 발견 포함) · 2 = 입력/후보 없음
  3 = gate 부분읽기(다시 돌리면 됨) · 4 = 계정 불일치 · 5 = 재조회에서 후보가 늘어남(복사 0)
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

try:
    # line_buffering — 잡 로그 파일로 리다이렉트돼도 줄 단위로 바로 보이게.
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
RUN_COUPANG = os.path.join(_HERE, "run_coupang.py")
# scripts → coupang-candidates → skills → .claude → 저장소 루트
REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))

PREVIEW_STAGES = ("prep", "resolve", "build", "ship", "gate", "apply")
# MCP 를 여는 단계만 계정 확인을 넘긴다(prep·build 는 불사자를 안 연다).
NICK_STAGES = {"resolve", "ship", "gate", "apply", "verify"}
# 줄을 캡처해 요약에 옮길 단계
CAPTURE_STAGES = {"gate", "apply"}
# gate 의 기본 상한(run_coupang gate --limit 기본값). 옛 후보가 이 크기면 늘어남이
# '진짜 새 상품' 이 아니라 상한 밖에 있던 것이 밀려 들어온 것일 수 있다(D-12 ⚠).
GATE_LIMIT = 100
# 실제 복사 플래그 — 이 파일에서 **한 번만** 적는다.
_COMMIT_FLAG = "--commit"

_그룹읽기 = re.compile(r"\[gate\] 그룹읽기 총상품수 (\S+) · 읽음 (\d+) · 타오바오결측 (\d+)")
_apply대상 = re.compile(r"\[apply\] 대상 (\d+)건")


# ------------------------------------------------------------------ 입출력

def _dump(path, obj):
    """원자적 쓰기 — 웹이 반쯤 쓴 요약을 읽지 않게."""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _load(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return default


def _jsonl(path):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        out.append({"_깨진줄": line[:200]})
    except FileNotFoundError:
        pass
    return out


def _pid_ok(pid):
    """자식에 넘어갈 pid 모양 — 선행 하이픈·공백·빈 값 거부."""
    return isinstance(pid, str) and bool(pid) and not pid.startswith("-") \
        and not re.search(r"\s", pid)


# ------------------------------------------------------------------ 단계 실행

def _단계(stage, run_dir, extra=(), nick=""):
    """run_coupang.py <stage> 를 자식으로. 반환 (종료코드, 캡처한 줄[])."""
    av = [sys.executable, RUN_COUPANG, stage, "--run-dir", run_dir, *extra]
    if stage in NICK_STAGES and nick:
        av += ["--expect-nick", nick]
    print(f"###STAGE### {stage} 시작", flush=True)
    lines = []
    try:
        if stage in CAPTURE_STAGES:
            p = subprocess.Popen(av, cwd=REPO_ROOT, stdout=subprocess.PIPE,
                                 text=True, encoding="utf-8", errors="replace")
            for line in p.stdout:
                # 로그 tail 유지 — 받은 줄을 그대로 다시 찍는다.
                print(line, end="", flush=True)
                lines.append(line.rstrip("\n"))
            code = p.wait()
        else:
            code = subprocess.call(av, cwd=REPO_ROOT)
    except OSError as e:
        print(f"###STAGE### {stage} 실행불가 {type(e).__name__}: {e}", flush=True)
        return 1, lines
    print(f"###STAGE### {stage} exit {code}", flush=True)
    return code, lines


def _러너코드(code):
    """자식 종료코드 → 러너 종료코드. 계약 밖 코드는 1 로 접는다."""
    return code if code in (1, 2, 3, 4, 5) else 1


def _gate_요약(run_dir, lines):
    """gate 산출(candidates/rejected) + 출력 줄 → 요약 조각."""
    cands = _load(os.path.join(run_dir, "candidates.json"), []) or []
    rej = _load(os.path.join(run_dir, "rejected.json"), []) or []
    by = {}
    for r in rej:
        k = str(r.get("사유") or "").split("(")[0]
        by[k] = by.get(k, 0) + 1
    기준 = next((ln for ln in lines if ln.startswith("[gate] 기준:")), "")
    읽기 = None
    for ln in lines:
        m = _그룹읽기.search(ln)
        if m:
            tot = m.group(1)
            읽기 = {"총상품수": int(tot) if tot.isdigit() else None,
                  "읽음": int(m.group(2)), "타오바오결측": int(m.group(3))}
    return {"기준": 기준, "통과": cands, "탈락사유별": by,
            "이미있음": by.get("쿠팡그룹에이미있음", 0), "그룹읽기": 읽기}, cands, rej


# ------------------------------------------------------------------ preview

def cmd_preview(args):
    run_dir = os.path.abspath(args.run_dir)
    os.makedirs(run_dir, exist_ok=True)
    summary = {"단계": [], "정지단계": None, "기준": "", "통과": [], "탈락사유별": {},
               "이미있음": 0, "그룹읽기": None, "apply미리보기": None}
    final = 0
    for stage in PREVIEW_STAGES:
        code, lines = _단계(stage, run_dir, nick=args.expect_nick)
        summary["단계"].append({"이름": stage, "exit": code})
        if stage == "gate" and code == 0:
            part, _, _ = _gate_요약(run_dir, lines)
            summary.update(part)
            # 통과 0건이면 apply 를 부르지 않는다 — apply 는 후보가 없으면 exit 2 라
            # 잡이 '실패'로 보였다(2026-09-30 d65c780a). 0건은 결과지 오류가 아니다.
            if not summary["통과"]:
                summary["apply미리보기"] = {"대상": 0}
                break
        if stage == "apply" and code == 0:
            m = next((_apply대상.search(ln) for ln in lines if _apply대상.search(ln)), None)
            summary["apply미리보기"] = {"대상": int(m.group(1)) if m else None}
        if code != 0:
            summary["정지단계"] = stage
            final = _러너코드(code)
            break
    try:
        _dump(args.summary_out, summary)
    except Exception as e:  # noqa: BLE001
        print(f"[요약] summary 쓰기 실패: {type(e).__name__}: {e}", file=sys.stderr)
        final = final or 1
    stop = f" · 정지 {summary['정지단계']}" if summary["정지단계"] else ""
    print(f"###COUPANG### preview 통과 {len(summary['통과'])} · 이미있음 "
          f"{summary['이미있음']} · 기준 {summary['기준'] or '-'}{stop}", flush=True)
    return final


# ------------------------------------------------------------------ commit

def _승인읽기(path):
    """approved.json → ([pid], None) 또는 (None, 사유). 빈 배열은 전량이 아니다(D-13)."""
    doc = _load(path, None)
    if doc is None:
        return None, "승인목록 파일을 못 읽었다"
    if not isinstance(doc, list) or not doc:
        return None, "승인목록이 비었거나 배열이 아니다"
    bad = [p for p in doc if not _pid_ok(p)]
    if bad:
        return None, f"잘못된 pid {len(bad)}건: {bad[:3]}"
    return list(dict.fromkeys(doc)), None


def cmd_commit(args):
    run_dir = os.path.abspath(args.run_dir)
    summary = {"단계": [], "정지단계": None,
               "재조회": {"옛": 0, "새": 0, "빠짐": {}, "늘어남": [], "상한경계": False},
               "복사": [], "신pid없음": 0, "중복0": None, "verify": None}

    def _끝(code, line):
        try:
            _dump(args.summary_out, summary)
        except Exception as e:  # noqa: BLE001
            print(f"[요약] summary 쓰기 실패: {type(e).__name__}: {e}", file=sys.stderr)
            code = code or 1
        print(f"###COUPANG### commit {line}", flush=True)
        return code

    # ── 입력 검사 — 자식 호출 전에 끝낸다(D-13)
    approved, why = _승인읽기(args.approved)
    if approved is None:
        print(f"[입력] {why} — 중단(전량 복사로 넘어가지 않는다)", file=sys.stderr)
        return _끝(2, "복사 0 · 입력 오류")
    if args.limit is None or args.limit < 1:
        print("[입력] --limit 이 1 이상이어야 한다 — 중단", file=sys.stderr)
        return _끝(2, "복사 0 · 입력 오류")
    prev = _load(os.path.join(run_dir, "summary.json"), None)
    if not isinstance(prev, dict) or not isinstance(prev.get("통과"), list):
        print("[입력] 미리보기 요약(summary.json)이 없다 — preview 먼저", file=sys.stderr)
        return _끝(2, "복사 0 · 미리보기 없음")
    옛 = [str(r.get("대표pid")) for r in prev["통과"] if isinstance(r, dict)]

    # ── 재조회 (D-12) — 미리보기와 지금 사이에 그룹이 바뀌었을 수 있다
    code, lines = _단계("gate", run_dir, nick=args.expect_nick)
    summary["단계"].append({"이름": "gate", "exit": code})
    if code != 0:
        summary["정지단계"] = "gate"
        return _끝(_러너코드(code), "복사 0 · 재조회 실패")
    _, cands, rej = _gate_요약(run_dir, lines)
    새 = [str(c.get("대표pid")) for c in cands]
    옛집합, 새집합 = set(옛), set(새)
    늘어남 = [p for p in 새 if p not in 옛집합]
    re_ = summary["재조회"]
    re_.update({"옛": len(옛), "새": len(새), "늘어남": 늘어남,
                "상한경계": bool(늘어남) and len(옛) >= GATE_LIMIT})
    if 늘어남:
        print(f"[commit] 재조회 후보가 미리보기보다 {len(늘어남)}건 늘었다 — 복사 0. "
              f"미리보기를 다시 돌려 확인해라"
              + (" (상한 경계 — 상한 밖 후보가 밀려 들어왔을 수 있다)"
                 if re_["상한경계"] else ""))
        summary["정지단계"] = "재조회"
        return _끝(5, f"복사 0 · 늘어남 {len(늘어남)}")

    사유 = {str(r.get("대표pid")): r.get("사유") for r in rej}
    re_["빠짐"] = {p: 사유.get(p, "후보에없음") for p in approved if p not in 새집합}
    pids = [p for p in approved if p in 새집합]
    if not pids:
        print("[commit] 승인분이 재조회 후보에 하나도 없다 — 복사 0", file=sys.stderr)
        summary["정지단계"] = "재조회"
        return _끝(2, "복사 0 · 승인∩새 없음")

    # ── 복사 (쓰기)
    pids_file = os.path.join(run_dir, f"approved_pids_{time.strftime('%Y%m%d-%H%M%S')}"
                                      f"_{os.getpid()}.json")
    _dump(pids_file, pids)
    copied_path = os.path.join(run_dir, "copied.jsonl")
    before = len(_jsonl(copied_path))
    code, _ = _단계("apply", run_dir, extra=[_COMMIT_FLAG, "--limit", str(args.limit),
                                             "--pids-file", pids_file],
                    nick=args.expect_nick)
    summary["단계"].append({"이름": "apply", "exit": code})
    # 실패했어도 중간까지 복사됐을 수 있다 — 이번 잡이 더한 행은 항상 싣는다.
    added = _jsonl(copied_path)[before:]
    summary["복사"] = added
    summary["신pid없음"] = sum(1 for r in added if not r.get("신pid"))
    if code != 0:
        summary["정지단계"] = "apply"
        return _끝(_러너코드(code), f"복사 {len(added)} · apply 실패")

    # ── 검증 — 종료코드가 아니라 verified.json 으로 판정(Pitfall 5)
    code, _ = _단계("verify", run_dir, extra=["--only", "all"], nick=args.expect_nick)
    summary["단계"].append({"이름": "verify", "exit": code})
    ver = _load(os.path.join(run_dir, "verified.json"), None)
    if isinstance(ver, dict):
        판매가 = ver.get("판매가") or []
        summary["verify"] = {"중복0": ver.get("중복0"), "중복": ver.get("중복") or {},
                             "그룹상품수": ver.get("그룹상품수"),
                             "판매가검산": len(판매가),
                             "판매가어긋남": sum(1 for c in 판매가 if not c.get("동일"))}
        summary["중복0"] = ver.get("중복0")
    if code != 0:
        summary["정지단계"] = "verify"
        return _끝(_러너코드(code), f"복사 {len(added)} · verify 실패")
    if summary["중복0"] is not True:
        print("[commit] ❌ verify 가 중복 0 을 증명하지 못했다 — 쿠팡 그룹을 확인해라",
              file=sys.stderr)
        summary["정지단계"] = "verify"
        return _끝(1, f"복사 {len(added)} · 중복0 {summary['중복0']}")
    return _끝(0, f"복사 {len(added)} · 신pid없음 {summary['신pid없음']} · 중복0 True")


# ------------------------------------------------------------------ CLI

def main(argv=None):
    ap = argparse.ArgumentParser(description="쿠팡 웹 러너(관제탑)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("preview", help="prep→…→apply 미리보기 (쓰기 0)")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--expect-nick", required=True)
    p.add_argument("--summary-out", required=True)
    p.set_defaults(fn=cmd_preview)

    c = sub.add_parser("commit", help="gate 재조회 → 승인분 복사 → verify")
    c.add_argument("--run-dir", required=True)
    c.add_argument("--approved", required=True)
    c.add_argument("--limit", type=int, required=True)
    c.add_argument("--expect-nick", required=True)
    c.add_argument("--summary-out", required=True)
    c.set_defaults(fn=cmd_commit)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except KeyboardInterrupt:
        sys.exit(1)
