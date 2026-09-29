#!/usr/bin/env python3
"""썸네일 웹 러너 — 관제탑 견적 잡이 부르는 얇은 껍데기 (Phase 7 / THUMB-02·03).

  estimate : inputs.json 의 그룹마다 `run_thumbs.py prep` 을 **자식 프로세스로** 차례로
             돌리고(크레딧 0), 그룹별 estimate.json 을 합산해 summary.json 한 장을 쓴다.

**CLI 를 import 하지 않는다** — subprocess 로만 부른다. run_thumbs 의 전역 상태·무플래그
동작을 건드리지 않고, 자식 stdout 이 이 프로세스의 stdout(=잡 로그 파일)을 그대로
물려받아 웹 SSE tail 이 산다(RESEARCH §Pattern 1).
**크레딧 숫자를 곱하지 않는다** — 예상·최대크레딧은 prep 이 쓴 값을 더하기만 한다(L-02).

사용 (웹앱 argv.ThumbArgv 가 이 모양으로 조립한다):
  python thumb_web.py estimate --run-dir D --inputs D/inputs.json \\
      --expect-nick N --summary-out D/summary.json

inputs.json: {"그룹": {"<불사자 그룹명>": ["pid", ...]}, "코드": {"pid": "판매자상품코드"}}

종료코드:
  0 = 1개 이상 그룹 성공 · 1 = 전 그룹 오류 · 2 = inputs 깨짐/빈 그룹
  4 = 자식 계정 불일치(즉시 정지 — 다음 그룹을 돌리지 않는다)
"""
import argparse
import json
import os
import re
import subprocess
import sys

try:
    # line_buffering — 잡 로그 파일로 리다이렉트돼도 줄 단위로 바로 보이게(run_thumbs 와 같다).
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RUN_THUMBS = os.path.join(SCRIPT_DIR, "run_thumbs.py")
# scripts → bulsaja-thumbnail → skills → .claude → 저장소 루트
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", ".."))

# 그룹 합계에 더하는 견적 필드 — 이름: (estimate 키, 셈법)
_합계키 = (("선택", "선택"), ("K", "대상"), ("M", "이미가공"), ("A", "정합검사"),
          ("D", "삭제대상"), ("E", "조회실패"), ("현황판제외", "현황판제외"))
# 그룹 항목에 싣는 estimate 필드
_그룹필드 = ("시트id", "대상", "이미가공", "정합검사", "삭제대상", "조회실패",
           "현황판제외", "예상크레딧", "최대크레딧")


def _dump_atomic(path, obj):
    """임시 파일 → os.replace. 웹이 반쯤 쓴 summary 를 읽지 않게."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
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


def _pid_ok(pid):
    """자식 argv 에 들어갈 pid 모양 — 선행 하이픈(플래그로 읽힘)·공백·빈 값 거부."""
    return isinstance(pid, str) and bool(pid) and not pid.startswith("-") \
        and not re.search(r"\s", pid)


def _입력읽기(path):
    """inputs.json → ({그룹명: [pid]}, {pid: 코드}) 또는 (None, 사유)."""
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except Exception as e:  # noqa: BLE001
        return None, f"inputs 읽기 실패: {type(e).__name__}: {str(e)[:120]}"
    if not isinstance(doc, dict):
        return None, "inputs 가 객체가 아니다"
    groups = doc.get("그룹")
    if not isinstance(groups, dict) or not groups:
        return None, "그룹이 없다"
    out = {}
    for name, pids in groups.items():
        if not isinstance(name, str) or not name.strip():
            return None, "빈 그룹명"
        if not isinstance(pids, list) or not pids:
            return None, f"그룹 '{name}' 의 pid 목록이 비었다"
        bad = [p for p in pids if not _pid_ok(p)]
        if bad:
            return None, f"그룹 '{name}' 에 잘못된 pid {len(bad)}건: {bad[:3]}"
        out[name] = list(dict.fromkeys(pids))   # 순서 유지 중복 제거
    codes = doc.get("코드") or {}
    if not isinstance(codes, dict):
        return None, "코드 맵이 객체가 아니다"
    return out, {str(k): str(v) for k, v in codes.items()}


def _그룹폴더(name, used):
    """그룹명 → run-dir 밑 폴더 이름 (Pitfall 8 · T-07-08).

    `/`·`\\`·공백·제어문자 → `_`, 선행 `.` 제거(`..` 로 위로 못 올라간다), 80자 컷.
    맥 파일시스템은 대소문자를 안 가리므로 충돌 검사는 소문자로 — 겹치면 `_2`, `_3` …
    """
    base = re.sub(r"[/\\\s\x00-\x1f]", "_", name).lstrip(".")[:80] or "group"
    cand, n = base, 1
    while cand.lower() in used:
        n += 1
        cand = f"{base}_{n}"
    used.add(cand.lower())
    return cand


def _읽기(path):
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        return doc if isinstance(doc, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _prep(sub, name, pids, nick):
    """그룹 하나의 prep 을 자식으로 — stdout 은 물려받는다. 반환: 종료코드."""
    av = [sys.executable, RUN_THUMBS, "prep",
          "--run-dir", sub,
          # `=` 로 붙인다 — 그룹명이 `-` 로 시작해도 자식 argparse 가 플래그로 읽지 않게.
          f"--group-name={name}",
          "--ids", *pids,
          "--only-pending",
          "--expect-nick", nick,
          "--estimate-out", os.path.join(sub, "estimate.json")]
    print(f"###GROUP### {name} 시작 ({len(pids)}건)", flush=True)
    try:
        code = subprocess.call(av, cwd=REPO_ROOT)
    except OSError as e:
        print(f"###GROUP### {name} 실행불가 {type(e).__name__}: {e}", flush=True)
        return 2
    print(f"###GROUP### {name} exit {code}", flush=True)
    return code


def _합산(entries):
    """성공 그룹만 더한다. 크레딧은 prep 이 쓴 값의 합 — 곱셈 없음(L-02)."""
    tot = {k: 0 for k, _ in _합계키}
    tot.update({"예상크레딧": 0, "최대크레딧": 0})
    for g in entries:
        if g.get("오류"):
            continue
        for k, field in _합계키:
            tot[k] += len(g.get(field) or ())
        tot["예상크레딧"] += int(g.get("예상크레딧") or 0)
        tot["최대크레딧"] += int(g.get("최대크레딧") or 0)
    return tot


def _thumb_line(tot):
    return (f"###THUMB### 선택 {tot['선택']} · 대상 {tot['K']} · 이미가공 {tot['M']} · "
            f"정합 {tot['A']} · 삭제 {tot['D']} · 조회실패 {tot['E']} · "
            f"예상 {tot['예상크레딧']} · 최대 {tot['최대크레딧']}")


def cmd_estimate(args):
    run_dir = os.path.abspath(args.run_dir)
    groups, codes = _입력읽기(args.inputs)
    if groups is None:
        print(f"[입력] {codes} — 중단", file=sys.stderr)
        print(_thumb_line(_합산([])), flush=True)
        return 2
    try:
        os.makedirs(run_dir, exist_ok=True)
    except OSError as e:
        print(f"[입력] run-dir 을 못 만든다: {e}", file=sys.stderr)
        return 2

    entries, used = [], set()
    stop = None
    for name, pids in groups.items():
        sub = os.path.join(run_dir, _그룹폴더(name, used))
        # 방어선 — 정규화가 깨져도 run-dir 밖으로는 못 나간다.
        if os.path.dirname(os.path.abspath(sub)) != run_dir:
            entries.append({"그룹명": name, "run_dir": sub, "오류": "그룹 폴더 경로 이상"})
            continue
        # 선택 = 웹이 넘긴 id 원본 수(현황판제외 포함). 자식이 못 쓰면 이 값이 남는다.
        entry = {"그룹명": name, "run_dir": sub, "선택": list(pids)}
        for k in _그룹필드:
            entry.setdefault(k, {} if k in ("이미가공", "삭제대상", "조회실패", "현황판제외")
                             else ([] if k in ("대상", "정합검사") else
                                   (0 if "크레딧" in k else "")))
        try:
            os.makedirs(sub, exist_ok=True)
            code = _prep(sub, name, pids, args.expect_nick)
        except Exception as e:  # noqa: BLE001
            code = None
            entry["오류"] = f"{type(e).__name__}: {str(e)[:120]}"
        est = _읽기(os.path.join(sub, "estimate.json"))
        if est:
            for k in _그룹필드:
                if k in est:
                    entry[k] = est[k]
            if est.get("선택"):
                entry["선택"] = est["선택"]
        if code == 4:
            # 계정 불일치 — 다음 그룹도 같은 계정이다. 돌리지 않고 즉시 멈춘다(L-05).
            entry["오류"] = "계정불일치"
            entries.append(entry)
            stop = 4
            break
        if "오류" not in entry:
            if code != 0:
                entry["오류"] = f"exit {code}"
            elif not est:
                entry["오류"] = "exit 0 · estimate.json 없음"
            elif est.get("오류"):
                entry["오류"] = str(est["오류"])[:200]
            else:
                entry["오류"] = None
        entries.append(entry)

    tot = _합산(entries)
    summary = {"계정": args.expect_nick, "코드": codes, "그룹": entries, "합계": tot}
    if stop == 4:
        summary["오류"] = "계정불일치"
    try:
        _dump_atomic(args.summary_out, summary)
    except Exception as e:  # noqa: BLE001
        print(f"[요약] summary 쓰기 실패: {type(e).__name__}: {e}", file=sys.stderr)
        print(_thumb_line(tot), flush=True)
        return 1
    print(_thumb_line(tot), flush=True)
    if stop == 4:
        return 4
    ok = [g for g in entries if not g.get("오류")]
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="썸네일 웹 러너(관제탑)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("estimate", help="그룹별 prep → 합산 견적(크레딧 0)")
    e.add_argument("--run-dir", required=True)
    e.add_argument("--inputs", required=True)
    e.add_argument("--expect-nick", required=True)
    e.add_argument("--summary-out", required=True)
    e.set_defaults(func=cmd_estimate)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
