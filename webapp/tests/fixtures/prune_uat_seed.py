#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""꺼진 소재 정리 UAT 격리 시드 — Phase 2 / 02-05.

실데이터를 건드리지 않는 격리 인스턴스(별도 포트 · tmp DB · tmp 데이터루트 · tmp 감사 경로)에
회차 1개 · 잡 행 5개 · 산출물을 깐다. uat-verifier(또는 playwright-cli)가 이걸 눌러 본다.

**안전 순서(T-02-32)** — 아래 순서를 바꾸지 마라:
  1. 실계정 alias 목록을 `run_ads.py accounts` 로 받는다(읽기 전용 · 네트워크 0 · 시크릿 미출력)
  2. 가짜 alias(uat-a/b/c) 와 교집합이 하나라도 있으면 아무것도 쓰지 않고 exit 1
  3. 그다음에야 CT_DB_PATH/CT_DATA_ROOT 를 설정하고 webapp 을 import 해서 시드한다

가짜 alias 는 자격증명이 없으므로 격리 인스턴스에서 커밋을 눌러도 CLI 가
"자격증명 없음 — 건너뛴다" 로 끝난다 → 네이버 광고 API 호출 0.

사용:
  .venv-web/bin/python webapp/tests/fixtures/prune_uat_seed.py --root <scratch>/uat-prune
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

저장소 = Path(__file__).resolve().parents[3]
RUN_ADS = 저장소 / ".claude" / "skills" / "naver-ads-weekly" / "scripts" / "run_ads.py"
CLI_PY = 저장소 / ".venv" / "bin" / "python3"
가짜계정 = ["uat-a", "uat-b", "uat-c"]
회차 = "uat-prune"
UAT_토큰 = "uat-prune"


def _지금(시간전: float = 0) -> str:
    """잡 started_at 형식(로컬 tz 포함 ISO)."""
    return (datetime.now().astimezone() - timedelta(hours=시간전)).isoformat(timespec="seconds")


def 실계정_목록() -> list[str]:
    """실데이터 환경 그대로 `run_ads.py accounts` 를 불러 alias 만 받는다. 실패하면 예외."""
    # 격리용 환경변수가 섞여 있어도 accounts 는 자격증명 파일만 읽는다 — 그래도 깨끗한 env 로 부른다
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("CT_") and k != "EROOM_WORKSPACE_TOML"}
    out = subprocess.run([str(CLI_PY), str(RUN_ADS), "accounts"], capture_output=True,
                         text=True, timeout=60, env=env, cwd=str(저장소))
    if out.returncode != 0:
        raise RuntimeError(f"run_ads accounts 실패(rc={out.returncode}): {out.stderr[-300:]}")
    목록 = json.loads(out.stdout.strip().splitlines()[-1])
    return [str(a.get("alias")) for a in 목록]


# ── 산출물 모양 (02-01 CLI 계약) ─────────────────────────────────────────────

_상품명샘플 = ["접이식 캠핑 의자 <b>특가</b>", "无线鼠标 静音 블루투스 마우스", "스테인리스 수납 선반 3단",
            "<b>굵게</b> 보이면 안 되는 상품명", "加厚 방수 차량용 커버", "휴대용 미니 선풍기 USB"]


def _대상행(alias: str, i: int, 사유: str = "AD_ABNORMAL_INTERLOCK") -> dict:
    return {"adId": f"nad-{alias}-{i:05d}", "adgroupId": f"grp-{alias}-{i % 40}",
            "adGroup": f"판매상품_{i % 20 + 1}-{i % 3 + 1}_{alias}", "mallProductId": f"{80000000 + i}",
            "title": f"{_상품명샘플[i % len(_상품명샘플)]} #{i}", "statusReason": 사유,
            "editTm": "2026-09-20T10:00:00.000Z", "regTm": "2026-08-01T10:00:00.000Z"}


def _미리보기문서(계정수: dict[str, int], keep: dict[str, dict] | None = None,
                skip_c: bool = True) -> dict:
    """dry-run 산출물. 계정수 = {alias: 대상 수}."""
    accounts, ad_ids = {}, []
    for alias, n in 계정수.items():
        t = [_대상행(alias, i) for i in range(n)]
        k = (keep or {}).get(alias, {})
        accounts[alias] = {"paused": n + sum(k.values()), "deletable": n, "keep": k,
                           "backup": None, "aborted": None, "skipped": None, "targets": t}
        ad_ids += [r["adId"] for r in t]
    if skip_c:
        accounts["uat-c"] = {"skipped": "자격증명 없음", "aborted": None, "backup": None,
                             "keep": {}, "targets": []}
    return {"generated": _지금()[:19], "mode": "dry-run", "limit": None,
            "total": len(ad_ids), "adIds": ad_ids, "accounts": accounts}


def _커밋문서(미리보기: dict) -> dict:
    """미리보기 E 의 자식 커밋 산출물: uat-a 성공 100 · 실패 5 · 재시도소진 2 · 제외 5 · 새로꺼짐 4 / uat-b 백업 실패."""
    a = 미리보기["accounts"]["uat-a"]["targets"]
    b = 미리보기["accounts"]["uat-b"]["targets"]
    items = [{"adId": r["adId"], "status": 200, "결과": "성공", "err": None} for r in a[:100]]
    items += [{"adId": r["adId"], "status": 500, "결과": "실패", "err": f"server <b>boom</b> {i}"}
              for i, r in enumerate(a[100:105])]
    items += [{"adId": r["adId"], "status": 429, "결과": "재시도소진", "err": "too many requests"}
              for r in a[105:107]]
    excluded = ([{"adId": r["adId"], "사유": "다시_켜짐"} for r in a[107:110]]
                + [{"adId": r["adId"], "사유": "재조회에_없음"} for r in a[110:112]])
    return {"generated": _지금()[:19], "mode": "commit", "limit": 8000,
            "total": len(items), "adIds": [x["adId"] for x in items],
            "accounts": {
                "uat-a": {"paused": 116, "deletable": 112, "keep": {},
                          "backup": "/uat/paused_uat-a_tag.json", "aborted": None, "skipped": None,
                          "targets": a, "items": items, "result": {"ok": 100, "gone": 0, "fail": 7},
                          "excluded": excluded, "new_since_preview": 4},
                "uat-b": {"paused": len(b), "deletable": len(b), "keep": {}, "backup": None,
                          "aborted": "backup_failed", "skipped": None, "targets": b},
            }}


def _보드행(alias: str, i: int, 규칙: str, **덮기) -> dict:
    행 = {"adId": f"nad-board-{alias}-{규칙[0]}-{i:03d}", "adGroup": f"판매상품_{i % 9 + 1}-1_{alias}",
          "title": f"{_상품명샘플[i % len(_상품명샘플)]} 보드{i}", "mallProductId": f"{70000000 + i}",
          "bid": 70, "useGroupBid": True, "groupBid": 70}
    행.update(덮기)
    return 행


def _보드결과() -> dict:
    """3계정 · 보드 행 ~40개. ② 일부 + ⑥(연동끊김/검수중/거부 · productLive 섞기 · 키 없음 1상품)."""
    사유들 = ["AD_ABNORMAL_INTERLOCK", "AD_UNDER_REVIEW", "AD_DISAPPROVED"]
    out = {"generated": "2026-09-30", "accounts": {}}
    for k, alias in enumerate(가짜계정):
        두번째 = [_보드행(alias, 100 * k + i, "②", imp=20000 + i, clk=50 + i, ctr=0.25, rank=7.5,
                     cost=9000 + i) for i in range(4)]
        여섯 = []
        for i in range(9):
            상품 = 100 * k + 50 + i // 2  # 한 상품에 소재 2개씩(마지막은 1개)
            행 = _보드행(alias, 상품, "⑥", adId=f"nad-board-{alias}-6-{i:03d}",
                       statusReason=사유들[i % 3], editTm="2026-09-21T10:00:00.000Z")
            # 0~3번 상품: productLive 전부 False(→ 광고 정지) / 나머지 True / uat-a 의 마지막 상품은 키 없음(→ ?)
            if not (alias == "uat-a" and i == 8):
                행["productLive"] = (i // 2) < 2
            여섯.append(행)
        out["accounts"][alias] = {
            "summary": {"ads": 30, "live": 21, "cost": 50000, "purAmt": 0, "purCnt": 0},
            "rules": {"①노출0": [], "②썸네일교체": 두번째, "③원인분석": [], "④효자후보": [],
                      "⑤효자확정": [], "⑥삭제대상": 여섯}}
    return out


# ── 시드 ────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="꺼진 소재 정리 UAT 격리 시드")
    ap.add_argument("--root", required=True, help="격리 루트(scratch). 저장소·실데이터 밖이어야 한다")
    ap.add_argument("--port", type=int, default=8799)
    args = ap.parse_args()

    S = Path(args.root).expanduser().resolve()
    실데이터 = (Path.home() / "python_work" / "data").resolve()
    if S == 저장소 or 저장소 in S.parents or S == 실데이터 or 실데이터 in S.parents:
        print(f"격리 루트가 저장소/실데이터 안이다 — 시드 중단: {S}")
        return 1

    # 1) 실계정 교집합 확인 — 이 확인 전에는 아무것도 쓰지 않는다
    try:
        실계정 = 실계정_목록()
    except Exception as e:
        print(f"실계정 목록 확인 실패 — 시드 중단: {type(e).__name__}: {e}")
        return 1
    겹침 = sorted(set(실계정) & set(가짜계정))
    if 겹침:
        print(f"가짜 alias 가 실계정과 겹친다 — 시드 중단: {겹침}")
        return 1

    # 2) webapp import 전에 격리 환경변수
    os.environ["CT_DB_PATH"] = str(S / "uat.db")
    os.environ["CT_DATA_ROOT"] = str(S / "data")
    os.environ["CT_JOB_LOG_DIR"] = str(S / "logs")
    os.environ["CT_AUDIT_PATH"] = str(S / "audit.jsonl")
    os.environ["EROOM_WORKSPACE_TOML"] = str(S / "workspace.toml")
    sys.path.insert(0, str(저장소))
    try:
        from webapp import jobs, paths  # noqa: E402
        if Path(jobs.db_path()).resolve() != (S / "uat.db") or paths.data_root().resolve() != (S / "data"):
            print("격리 경로가 적용되지 않았다 — 시드 중단")
            return 1

        S.mkdir(parents=True, exist_ok=True)
        (S / "workspace.toml").write_text(f'[paths]\ndata_root = "{S / "data"}"\n', encoding="utf-8")
        run_dir = S / "data" / "naver-ads" / "runs" / 회차
        (run_dir / "web").mkdir(parents=True, exist_ok=True)
        (S / "logs").mkdir(parents=True, exist_ok=True)
        (run_dir / "result.json").write_text(json.dumps(_보드결과(), ensure_ascii=False), encoding="utf-8")
        (run_dir / "prep_summary.json").write_text(json.dumps(
            {"window7": ["2026-09-22", "2026-09-28"], "window30": ["2026-08-30", "2026-09-28"]}),
            encoding="utf-8")
        for alias in 가짜계정:
            d = run_dir / "accounts" / alias
            d.mkdir(parents=True, exist_ok=True)
            (d / "ads.json").write_text(json.dumps({"ads": [], "groups": []}), encoding="utf-8")

        jobs.init_db()
        cx = sqlite3.connect(jobs.db_path())

        def 행(kind, 문서, 시작, parent=None, 접두="prune_preview") -> str:
            job_id = str(uuid.uuid4())
            결과 = run_dir / "web" / f"{접두}_{job_id}.json"
            결과.write_text(json.dumps(문서, ensure_ascii=False), encoding="utf-8")
            로그 = S / "logs" / f"{job_id}.log"
            로그.write_text("[시드] UAT 가짜 잡 — 실제 CLI 는 돌지 않았다\n", encoding="utf-8")
            cx.execute("INSERT INTO jobs (id, kind, run_dir, accounts, argv, status, log_path, "
                       "targets_path, result_path, parent_job_id, exit_code, started_at, ended_at) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (job_id, kind, 회차, "[]", "[]", "done", str(로그), None, str(결과), parent,
                        0, 시작, 시작))
            return job_id

        keep = {"uat-a": {"AD_DISAPPROVED": 12, "AD_UNDER_REVIEW": 5},
                "uat-b": {"AD_UNDER_REVIEW": 3}}
        A = 행("prune_preview", _미리보기문서({"uat-a": 2000, "uat-b": 1000}, keep), _지금())
        B = 행("prune_preview", _미리보기문서({"uat-a": 10}), _지금(25))
        C = 행("prune_preview", _미리보기문서({"uat-a": 6000, "uat-b": 3000}), _지금())
        E문서 = _미리보기문서({"uat-a": 112, "uat-b": 8}, skip_c=False)
        E = 행("prune_preview", E문서, _지금(1))
        D = 행("prune_commit", _커밋문서(E문서), _지금(0.5), parent=E, 접두="prune_result")
        cx.commit()
        cx.close()

        기준 = f"http://127.0.0.1:{args.port}"
        print(json.dumps({
            "root": str(S), "run_dir": 회차, "token": UAT_토큰,
            "jobs": {"A_preview_3000": A, "B_preview_expired": B, "C_preview_over_limit": C,
                     "E_preview_120": E, "D_commit_with_failures": D},
            "urls": {"login": f"{기준}/?t={UAT_토큰}", "board": f"{기준}/?run_dir={회차}",
                     **{k: f"{기준}/jobs/{v}/result" for k, v in
                        {"A": A, "B": B, "C": C, "D": D, "E": E}.items()}},
        }, ensure_ascii=False, indent=1))
        return 0
    except Exception as e:
        print(f"시드 실패: {type(e).__name__}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
