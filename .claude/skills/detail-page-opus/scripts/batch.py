# -*- coding: utf-8 -*-
"""고퀄 상세 밤 배치 — targets.json 상품을 한 개씩: Aside 제작 → 자동 검수 → 불사자 반영 → 스마트스토어 수정 전송.

- 한 상품이 실패·보류돼도 다음 상품으로 넘어간다. 진행 상태는 state.json 에 남아 재실행하면 이어서 한다.
- Aside 가 제작 전에 상품검수(sourcing-inspect 기준표)부터 하고, 탈락이면 상세를 만들지 않는다(inspect_drop).
- Aside 보고서에 "확인 필요" 절이 있거나 자동 검수에 걸리면 반영하지 않고 보류한다(아침에 사람이 본다).
- 끝나면 summary.md(아침 요약)를 쓴다.

사용법:
  caffeinate -i python batch.py --batch 2026-10-27 [--no-market]
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

from PIL import Image

import common
import thumb_wm

STALL_SEC = 300        # Aside 로그가 이 시간 동안 0바이트면 멈춘 것으로 보고 한 번 다시 띄운다
MAKE_TIMEOUT = 3600    # 제작 상한
TASK_TIMEOUT = 1200    # 스마트스토어 전송 결과 대기 상한


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def write_brief(t, outdir):
    """작업지시서 — 계정 스킬을 그대로 따르게 하고, 상품별 사실만 적는다."""
    today = date.today().isoformat()
    p = common.BRIEF_DIR / f"작업지시서-{t['code']}-{today}.md"
    excl = ", ".join(t.get("excludedOptions") or []) or "없음"
    sell = ", ".join(t.get("sellOptions") or []) or "불사자에서 확인"
    # 검수 기준표는 Aside 가 읽을 수 있게 지시서 폴더로 매번 새로 복사(정본은 sourcing-inspect/rules)
    crit = common.BRIEF_DIR / "상품검수-기준표.md"
    try:
        crit.write_text(common.INSPECT_PROMPT.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception as e:
        log(f"  [경고] 검수 기준표 복사 실패 {e}")
    p.write_text(
        f"계정 스킬 smartstore-detail-page(2026-10-23-opus-v1, 10/27 규칙 2줄 추가본)를 그대로 따른다.\n"
        f"- 판매자상품코드 {t['code']}, 불사자 내부 ID {t['productId']}, 마켓 {t['market']}, 상품명 {t['name']}\n"
        f"- 업로드 마켓그룹 {t.get('marketGroupName')} → 마켓 {t['market']} 로 매핑한다.\n"
        f"- 판매 옵션: {sell}\n"
        f"- 판매 제외 옵션(상세에 넣지 않는다): {excl}\n"
        f"- 반영하면 안 될 만큼 불확실한 것(옵션명과 모양의 짝을 모름, 판매 구성과 원본이 다름 등)만 report.md 에 '## 반영 보류 사유' 절로 적는다. 참고 메모는 다른 절에 쓰고 이 제목을 쓰지 않는다.\n"
        f"- 저장: {outdir}/\n"
        f"- 원본: 같은 상품 폴더에 originals/ 가 있으면 재사용, 없으면 불사자 현재 상세 이미지·옵션 이미지를 내려받아 originals/ 에 저장\n"
        + (f"- **상품검수는 하지 않는다**(효자상품 작업대장 — 판매된 상품이고 이룸님이 이미 확인함, 2026-11-04 용팀장 지시). "
           f"{outdir}/inspect.json 에 {{\"verdict\":\"pass\",\"reason\":\"OK\",\"note\":\"검수 생략: 효자상품 시트\"}} 만 쓰고 바로 상세를 만든다\n"
           if t.get("noInspect") else
        f"- **제작 전에 상품검수부터 한다**(용팀장 지시: 상세는 검수 통과 상품만). 기준표 {crit} 를 읽고 "
        f"stage 2 기준(실제로 팔 타오바오 상품 — 원본 썸네일·옵션 사진·타오바오 제목을 직접 보고)으로 판정해 "
        f"{outdir}/inspect.json 에 {{\"verdict\":\"pass|drop\",\"reason\":\"OK|LAW|DANGER|TARGET|IP|FASHION|SHIP|OTHER|SMALL|NOSELL|CATEGORY\",\"note\":\"한 줄\"}} 로 쓴다. "
        f"판매 옵션 구성에 금지 항목이 들어 있으면(예: 수전 포함 세트) 그것도 drop 이다. 애매하면 drop. "
        f"drop 이면 상세 PNG 를 만들지 말고 report.md 에 '## 검수 탈락' 절(사유·근거)만 쓰고 끝낸다\n")
        + f"- 스타일 C, 보호 표시 넣음\n"
        f"- verification.json 에 모델명 {common.MODEL} 기록\n"
        f"- 대표 썸네일(첫 번째)에 마켓명 워터마크가 이미 있는지 눈으로 보고 verification.json 에 thumbnailWatermark: true/false 로 남긴다(썸네일은 고치지 않는다)\n"
        f"- 불사자 저장·교체·업로드 금지(반영은 Claude Code 가 한다)\n",
        encoding="utf-8")
    return p


LIMIT_RE = re.compile(r"limit|rate|429|quota|usage|overloaded|resets?|not available|credit|billing|unauthori", re.I)
BLOCK_WAIT = 900       # 한도에 막히면 15분마다 다시 시도
BLOCK_MAX = 7 * 3600   # 5시간 창이 풀릴 때까지 넉넉히 — 넘으면 그 상품은 실패로 넘긴다


def limit_error(logfile):
    """Aside CLI 가 'Error …' 로 끝났고 그 문구가 한도·계정 쪽이면 True."""
    try:
        tail = Path(logfile).read_text(encoding="utf-8", errors="ignore")[-3000:]
    except Exception:
        return False
    errs = [l for l in tail.splitlines() if "Error" in l]
    return bool(errs) and bool(LIMIT_RE.search(errs[-1]))


def run_aside_waiting(brief, report, logfile):
    """한도에 막히면 풀릴 때까지 15분 간격으로 같은 상품을 다시 띄운다(2026-11-04 용팀장 지시)."""
    t0 = time.time()
    while True:
        r = run_aside(brief, report, logfile)
        if r != "blocked" or time.time() - t0 > BLOCK_MAX:
            return r
        log(f"  사용량 한도로 막힘 — {BLOCK_WAIT // 60}분 뒤 같은 상품 다시 (막힌 지 {round((time.time() - t0) / 60)}분)")
        time.sleep(BLOCK_WAIT)


def run_aside(brief, report, logfile):
    """Aside 제작. 로그가 STALL_SEC 동안 비면 한 번 다시 띄운다. report.md 가 생기면 성공."""
    for attempt in (1, 2):
        cmd = [str(common.ASIDE), "exec", "-m", common.MODEL, "--effort", "high",
               f"{brief} 를 읽고 그대로 작업해줘"]
        with open(logfile, "w") as lf:
            proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT)
        t0 = time.time()
        while True:
            time.sleep(15)
            if report.exists():
                time.sleep(30)            # 마무리 파일 쓰기 여유
                if proc.poll() is None:
                    proc.terminate()      # CLI 만 정리(앱 세션은 이미 끝남)
                return "ok"
            el = time.time() - t0
            if el > STALL_SEC and Path(logfile).stat().st_size == 0:
                proc.kill()
                log(f"  Aside 응답 없음 {attempt}회 — {'재시도' if attempt == 1 else '포기'}")
                break
            if el > MAKE_TIMEOUT:
                proc.kill()
                return "timeout"
            if proc.poll() is not None and not report.exists() and limit_error(logfile):
                return "blocked"          # 사용량 한도·계정 문제 — 호출한 쪽이 기다렸다 같은 상품을 다시 만든다
            if proc.poll() is not None and el > 60 and not report.exists():
                # CLI 가 먼저 끊겨도(Replay buffer 등) 앱 세션은 돈다 — report 를 계속 기다린다
                pass
    return "stalled"


def inspect_result(outdir):
    """Aside 가 쓴 검수 판정. 파일이 없거나 깨지면 통과로 보지 않는다(애매하면 drop)."""
    try:
        r = json.loads((outdir / "inspect.json").read_text(encoding="utf-8"))
        return r if isinstance(r, dict) else {"verdict": "drop", "reason": "OTHER", "note": "inspect.json 형식 이상"}
    except Exception:
        return {"verdict": "drop", "reason": "OTHER", "note": "inspect.json 없음 — 검수 미확인"}


def auto_check(outdir):
    """자동 검수. 문제 목록과 확인 필요 절(있으면)을 돌려준다."""
    probs = []
    finals = sorted(outdir.glob("[0-9][0-9].png"))
    cleans = sorted((outdir / "clean").glob("[0-9][0-9].png"))
    if not finals:
        probs.append("최종 PNG 없음")
    if len(finals) != len(cleans):
        probs.append(f"최종 {len(finals)}장 ≠ clean {len(cleans)}장")
    for f in finals:
        try:
            if Image.open(f).width != 860:
                probs.append(f"{f.name} 폭 860 아님")
        except Exception as e:
            probs.append(f"{f.name} 열기 실패 {e}")
    if not (outdir / "verification.json").exists():
        probs.append("verification.json 없음")
    rep = (outdir / "report.md").read_text(encoding="utf-8") if (outdir / "report.md").exists() else ""
    need = re.search(r"^#{2,3} 반영 보류 사유[^\n]*\n(.*?)(?=^#{1,3} |\Z)", rep, re.S | re.M)
    return probs, (need.group(0).strip()[:1500] if need else None), len(finals)


# 429 판정 — 조각 높이(860x1429)·파일명 같은 숫자 속 '429' 를 오류로 읽지 않게 앞뒤가 숫자·x 가 아닐 때만
RATE = re.compile(r"(?<![\dx])429(?!\d)|Rate limit|Too Many Requests|IMAGE_UPLOAD_BUSY", re.I)


def mark_priority_done(t):
    """광고 우선순위 목록에 '작업 끝'으로 기록 — 다음 주 목록에 다시 나와도 건너뛴다(전송·검수 탈락 모두)."""
    try:
        import fetch_ad_priority as fap
        d = fap._load(fap.DONE, {})
        for k in (t.get("productId"), t.get("storeNo")):
            if k:
                d[str(k)] = datetime.now().isoformat(timespec="seconds")
        fap._save(fap.DONE, d)
    except Exception as e:
        log(f"  [경고] 우선순위 완료 기록 실패 {e}")


def is_429(r):
    return bool(RATE.search(r.stdout + r.stderr))


QUICK = (0, 120)                          # 1차 시도: 짧게만 기다리고 미룬다
PATIENT = (0, 180, 360, 720, 1200, 1800)  # 미룬 반영 몰아서: 길게 기다린다


def run_429(cmd, env, waits=QUICK):
    """run.py 실행 — 불사자 429 면 waits 대로 쉬고 다시."""
    for wait in waits:
        if wait:
            log(f"  [429] {wait}초 쉬고 반영 재시도")
            time.sleep(wait)
        r = subprocess.run(cmd, cwd=common.REMIX, capture_output=True, text=True, env=env)
        if not is_429(r):
            return r
    return r


def apply(t, outdir, waits=QUICK):
    """bulsaja-detail-remix run.py 로 dry-run → 실제 반영 → 재조회 확인."""
    a = outdir / "_apply"
    a.mkdir(exist_ok=True)
    z = a / "final.zip"
    if z.exists():
        z.unlink()
    subprocess.run(f"cd '{outdir}' && zip -q '{z}' [0-9][0-9].png", shell=True, check=True)
    base = [str(common.PY), "run.py", f"--code={t['code']}", "--zip", str(z), "--out", str(a)]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    dry = run_429(base + ["--dry-run"], env, waits)
    chunks = re.findall(r"\[조각 \d+/(\d+)\] .*\((?:png|jpg|jpeg), 860x(\d+)\)", dry.stdout)
    if is_429(dry):
        return None, "불사자 429 — 반영 미룸"
    if dry.returncode != 0 or not chunks or any(int(h) > 2300 for _, h in chunks):
        return False, f"dry-run 이상: {dry.stdout[-400:]} {dry.stderr[-300:]}"
    n = int(chunks[0][0])
    real = run_429(base, env, waits)
    if is_429(real) and "[반영 완료]" not in real.stdout:
        return None, "불사자 429 — 반영 미룸"
    if real.returncode != 0 or "[반영 완료]" not in real.stdout:
        return False, f"반영 실패: {real.stdout[-400:]} {real.stderr[-300:]}"
    m = common.mcp()
    try:
        html = m.get_detail_html(t["productId"])
    finally:
        m.close()
    if html.count("/mcp-assets/") != n:
        return False, f"재조회 불일치: 조각 {n} vs 상세 {html.count('/mcp-assets/')}"
    return True, f"{n}조각 반영 · 백업 {a / 'before_apply.html'}"


def market_send(t):
    """스마트스토어 수정 전송 접수 → taskId."""
    m = common.mcp()
    try:
        args = {"productIds": [t["productId"]], "market": "SMARTSTORE", "marketGroupId": t["marketGroupId"]}
        pre = common.call(m, "bulsaja_market_update", args)
        tok = pre.get("confirmationToken")
        if not tok:
            return None, f"확인키 없음 {str(pre)[:300]}"
        r = common.call(m, "bulsaja_market_update", {**args, "confirm": True, "confirmationToken": tok})
        res = (r.get("결과") or [{}])[0]
        if res.get("taskId"):
            lock(m, t["productId"])
        return res.get("taskId"), res.get("결과")
    finally:
        m.close()


def lock(m, pid):
    """수정 업로드한 상품은 불사자 잠금(= 숨김) — 물갈이 삭제에 안 휩쓸리게(2026-11-04 용팀장 지시). 실패해도 전송은 유지."""
    try:
        args = {"productIds": [pid], "hide": True}
        tok = common.call(m, "bulsaja_product_hide", args).get("confirmationToken")
        if tok:
            common.call(m, "bulsaja_product_hide", {**args, "confirm": True, "confirmationToken": tok})
        log(f"  잠금 {pid}")
    except Exception as e:
        log(f"  [경고] 잠금 실패 {pid} {e}")


def wait_tasks(state, timeout=TASK_TIMEOUT, final=True):
    """접수한 전송 작업들의 최종 상태를 모은다.
    작업 목록 조회는 최근 30건만 준다 — 배치 끝에 몰아서 보면 몇 시간 전 접수분은 이미 밀려나
    '시간 초과'로 남는다(2026-11-03 13건 중 8건). 그래서 전송 직후마다 짧게 확인하고, 끝에 한 번 더 본다."""
    pending = {s["taskId"]: code for code, s in state.items() if s.get("taskId") and not s.get("taskStatus")}
    t0 = time.time()
    while pending and time.time() - t0 < timeout:
        time.sleep(30)
        try:
            m = common.mcp()
            try:
                r = common.call(m, "bulsaja_upload_tasks", {"mode": "list"})
            finally:
                m.close()
        except Exception as e:
            log(f"  전송 상태 조회 실패 {e}"); continue
        for job in r.get("마켓작업") or []:
            tid = str(job.get("taskId"))
            if tid in pending and job.get("상태") not in ("진행중", "대기", "대기중"):
                state[pending.pop(tid)]["taskStatus"] = job.get("상태")
    if final:
        for tid, code in pending.items():
            state[code]["taskStatus"] = "확인 안 됨(시간 초과)"


def summary(bdir, targets, state):
    lines = [f"# 고퀄 상세 배치 요약 — {bdir.name}", ""]
    done = [c for c, s in state.items() if s.get("stage") == "sent"]
    held = [c for c, s in state.items() if s.get("stage") == "held"]
    drop = [c for c, s in state.items() if s.get("stage") == "inspect_drop"]
    fail = [c for c, s in state.items() if s.get("stage") in ("failed", "timeout", "stalled")]
    tok = sum((s.get("usage") or {}).get("tokens", 0) for s in state.values())
    cost = sum((s.get("usage") or {}).get("cost_usd", 0) for s in state.values())
    mins = [s.get("minutes") for s in state.values() if s.get("minutes")]
    lines += [f"- 완료(스마트스토어 전송) {len(done)} · 검수 탈락 {len(drop)} · 보류(확인 필요) {len(held)} · 실패 {len(fail)} / 대상 {len(targets)}",
              f"- 제작 시간 평균 {round(sum(mins)/len(mins)) if mins else '-'}분 · 토큰 합 {tok:,} · API 환산 ${cost:.2f}",
              "", "| 판매자상품코드 | 마켓 | 상품명 | 결과 | 장수 | 분 | 토큰 | 메모 |", "|---|---|---|---|---|---|---|---|"]
    for t in targets:
        s = state.get(t["code"], {})
        u = s.get("usage") or {}
        res = {"sent": f"✅ 전송 {s.get('taskStatus', '')}", "held": "🟡 보류", "inspect_drop": "⛔ 검수 탈락", "applied": "반영만", "made": "⏸ 제작완료·반영 미룸"}.get(
            s.get("stage"), f"❌ {s.get('stage', '미실행')}")
        lines.append(f"| {t['code']} | {t['market']} | {t['name']} | {res} | {s.get('pages', '')} | "
                     f"{s.get('minutes', '')} | {u.get('tokens', ''):,} | {s.get('note', '')[:120]} |"
                     if u.get("tokens") else
                     f"| {t['code']} | {t['market']} | {t['name']} | {res} | {s.get('pages', '')} | "
                     f"{s.get('minutes', '')} | | {s.get('note', '')[:120]} |")
    for c in held:
        lines += ["", f"## 🟡 {c} 확인 필요", "", state[c].get("need") or state[c].get("note", ""),
                  "", f"폴더: `{state[c].get('outdir')}`"]
    (bdir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return bdir / "summary.md"


def main():
    ap = argparse.ArgumentParser(description="고퀄 상세 밤 배치")
    ap.add_argument("--batch", default=date.today().isoformat())
    ap.add_argument("--no-market", action="store_true", help="스마트스토어 전송은 하지 않는다")
    args = ap.parse_args()

    bdir = common.BATCH_ROOT / args.batch
    targets = json.loads((bdir / "targets.json").read_text(encoding="utf-8"))["targets"]
    sp = bdir / "state.json"
    state = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
    log(f"배치 {args.batch} 시작 — {len(targets)}건")

    for deferred_pass, i, t in [(False, i, t) for i, t in enumerate(targets, 1)] + \
                               [(True, i, t) for i, t in enumerate(targets, 1)]:
        s = state.setdefault(t["code"], {})
        if s.get("stage") in ("sent", "held", "inspect_drop") or (args.no_market and s.get("stage") == "applied"):
            continue
        if deferred_pass and s.get("stage") not in ("made", "applied"):
            continue   # 2회차는 반영이 미뤄진 상품만
        # 재실행·자정 넘김에도 같은 폴더를 쓴다(날짜가 바뀌면 새 폴더로 다시 만드는 버그, 2026-10-28)
        outdir = Path(s["outdir"]) if s.get("outdir") else \
            common.PAGES / t["market"] / t["productId"] / f"{date.today().isoformat()}_opus"
        s["outdir"] = str(outdir)
        log(f"{'[미룬 반영] ' if deferred_pass else ''}({i}/{len(targets)}) {t['code']} {t['market']} {t['name']}")
        try:
            if not (outdir / "report.md").exists():
                outdir.mkdir(parents=True, exist_ok=True)
                brief = write_brief(t, outdir)
                t0 = time.time()
                r = run_aside_waiting(brief, outdir / "report.md", bdir / f"aside-{t['code']}.log")
                s["minutes"] = round((time.time() - t0) / 60)
                s["usage"] = common.aside_usage(t0, time.time())
                if r != "ok":
                    s.update(stage=r, note=f"Aside 제작 {r}"); log(f"  제작 실패: {r}"); continue
            ins = inspect_result(outdir)
            if ins.get("verdict") != "pass" and not t.get("noInspect"):   # 효자상품 시트는 검수 생략
                s.update(stage="inspect_drop", inspect=ins, note=f"검수 탈락 {ins.get('reason')} {ins.get('note', '')}")
                mark_priority_done(t)
                log(f"  {s['note']}"); continue
            probs, need, pages = auto_check(outdir)
            s["pages"] = pages
            if probs or need:
                s.update(stage="held", need=need, note="; ".join(probs) or "보고서 확인 필요")
                log(f"  보류: {s['note']}"); continue
            if s.get("stage") != "applied":
                ok, msg = apply(t, outdir, PATIENT if deferred_pass else QUICK)
                if ok is None:
                    s.update(stage="made", note=msg); log(f"  {msg}"); continue
                if not ok:
                    s.update(stage="failed", note=msg); log(f"  반영 실패: {msg}"); continue
                s.update(stage="applied", note=msg); log(f"  {msg}")
            if not s.get("thumb"):
                # 대표 썸네일 워터마크 — 실패해도 상세 전송은 그대로 한다
                tr, tn = thumb_wm.run(t["code"], t["productId"], t["market"], outdir)
                if tr == "failed" and "429" in tn:
                    tr = None
                else:
                    s["thumb"] = tr
                s["thumbNote"] = tn; log(f"  썸네일: {tn}")
            if not args.no_market:
                tid, res = market_send(t)
                if not tid:
                    s.update(stage="failed", note=f"전송 접수 실패 {res}"); log(f"  전송 접수 실패 {res}"); continue
                s.update(stage="sent", taskId=str(tid)); log(f"  스마트스토어 전송 접수 {res}")
                mark_priority_done(t)
                wait_tasks(state, timeout=300, final=False)   # 최근 30건에서 밀려나기 전에 결과 확인
        except Exception as e:
            s.update(stage="failed", note=f"예외 {e}"); log(f"  예외: {e}")
        finally:
            common.write_json(sp, state)

    if not args.no_market:
        log("스마트스토어 전송 결과 대기")
        wait_tasks(state)
        common.write_json(sp, state)
    out = summary(bdir, targets, state)
    log(f"배치 끝 — 요약 {out}")
    if not args.no_market:
        # 상세는 이미 돼 있어 건너뛴 상품도 대표 썸네일 워터마크가 없으면 넣고 수정 전송(2026-11-03 용팀장 지시)
        log("썸네일 워터마크 따라잡기")
        r = subprocess.run([sys.executable, "-u", str(Path(__file__).with_name("thumb_catchup.py")),
                            "--targets", str(bdir / "targets.json")], capture_output=True, text=True)
        log("  " + ((r.stdout.strip().splitlines() or [r.stderr.strip()[-300:]])[-1]))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
