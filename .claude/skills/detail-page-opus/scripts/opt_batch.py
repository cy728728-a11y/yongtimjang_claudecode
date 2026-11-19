# -*- coding: utf-8 -*-
"""이미 상세가 만들어진 상품의 옵션이미지만 따로 돌리는 배치(2026-11-16 용팀장).
targets: [{code, productId, market, name, marketGroupId, outdir}] — 선별(중국어 있는 상품)된 것만.
Aside 제작(done.txt 대기) → opt_img.run 반영 → 스마트스토어 수정 전송 → 속성·태그 대기열.
사용법: python opt_batch.py --dir <배치폴더>   (폴더 안 targets.json, state.json, run.log)
"""
import argparse, json, sys, time
from datetime import date, datetime
from pathlib import Path
import common, batch, opt_img, prep

HEAD = ("옵션 이미지 고급화 작업. 계정 스킬 smartstore-detail-page(2026-10-23-opus-v1)의 톤·폰트·워터마크 규칙을 그대로 쓴다"
        "(아이보리+진갈색 C 세일즈형, 같은 펜체 마켓명 워터마크).\n"
        "- 판매자상품코드 {code}, 마켓 {market}, 상품명 「{name}」\n"
        "- 이 상품의 상세는 이미 만들어져 있다: {outdir} (originals/·clean/·cuts 를 재료로 써도 된다)\n")

TOOLS_NOTE = ("- **고정 도구 모드(토큰 절약, 2026-11-19)**: 상세는 다시 만들지 않는다. 옵션 이미지만 한다.\n"
              "  {outdir}/work/README.md 의 '하지 않는다'와 **7단계(옵션 이미지)만** 따른다. "
              "원본·옵션 사진은 {outdir}/../originals/ 에 있고(먼저 _facts.md 로 vid↔option-N 확인), "
              "판단은 _sheets/option-*.jpg 모음으로 시작해 필요한 것만 look.py 로 확대한다.\n"
              "  순서: redo/skip 판단 → opt_cut.py → check_N.png 눈 확인 → option-images/work/spec.json(vid 는 아래 목록의 vid) → opt_build.py → preview.jpg 눈 확인. "
              "예전 작업 폴더·불사자 탭·도구 재작성 금지. opt_build 가 option-images.json·preview.jpg·done.txt 를 쓴다.\n")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dir", required=True); ap.add_argument("--limit", type=int)
    ap.add_argument("--tools", action="store_true", help="고정 도구 모드(원본·모음 미리 준비, Aside 는 opt_cut·opt_build 만)")
    ap.add_argument("--until", help="이 시각(YYYY-MM-DD HH:MM) 이후엔 새 상품을 시작하지 않고 마무리 후 멈춤")
    a = ap.parse_args(); d = Path(a.dir)
    targets = json.loads((d / "targets.json").read_text(encoding="utf-8"))
    sp = d / "state.json"; state = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
    n = 0
    for t in targets:
        s = state.setdefault(t["code"], {})
        if s.get("stage") in ("sent", "skip", "failed"):
            continue
        if common.is_bead(t.get("name")):   # 비즈 부자재 절대 제외(2026-11-19 용팀장)
            s.update(stage="skip", note="비즈 부자재 — 제외"); continue
        if a.limit and n >= a.limit:
            break
        if a.until and datetime.now() >= datetime.strptime(a.until, "%Y-%m-%d %H:%M"):
            print(f"[{time.strftime('%H:%M')}] 멈춤 시각 {a.until} 도달 — 새 상품 시작 안 함", flush=True)
            break
        n += 1
        out = Path(t["outdir"]); od = out / "option-images"; od.mkdir(parents=True, exist_ok=True)
        print(f"[{time.strftime('%H:%M')}] {t['code']} {t['market']} {t['name']}", flush=True)
        try:
            if not (od / "done.txt").exists():
                m = common.mcp()
                try:
                    body = opt_img.brief_lines(m, t["productId"], out)
                finally:
                    m.close()
                if not body:
                    s.update(stage="skip", note="옵션 이미지 없음"); continue
                body = body.replace("(상세를 다 만든 뒤, report.md 를 쓰기 전에 한다)", "")
                brief = common.BRIEF_DIR / f"옵션이미지-{t['code']}-{date.today().isoformat()}.md"
                head = HEAD.format(code=t["code"], market=t["market"], name=t["name"], outdir=out)
                if a.tools and prep.run(t, out, brief, common.MODEL, log=lambda x: print(x, flush=True)):
                    s["tools"] = True
                    head += TOOLS_NOTE.format(outdir=out)
                brief.write_text(head + body, encoding="utf-8")
                t0 = time.time()
                r = batch.run_aside_waiting(brief, od / "done.txt", d / f"aside-{t['code']}.log")
                s["minutes"] = round((time.time() - t0) / 60); s["usage"] = common.aside_usage(t0, time.time(), match=brief.name)
                if r != "ok":
                    s.update(stage="failed", note=f"Aside {r}"); print("  제작 실패", r, flush=True); continue
            res, note, gid = opt_img.run(out)
            s.update(optImg=res, note=note); print("  ", res, note, flush=True)
            if res == "skip":
                s["stage"] = "skip"; continue
            if res != "applied":
                s["stage"] = "failed"; continue
            tid, rr = batch.market_send({"productId": t["productId"], "marketGroupId": gid or t.get("marketGroupId")})
            if not tid:
                s.update(stage="failed", note=f"전송 실패 {rr}"); continue
            s.update(stage="sent", taskId=str(tid)); print("   전송 접수", tid, flush=True)
            no = batch.queue_attr_tag(t)
            if no:
                s["ssNo"] = no
            batch.wait_tasks(state, timeout=300, final=False)   # 전송 결과 확인 → 성공이면 그 상품만 태그 재점검
            batch.recheck_sent(state, {x["code"]: x for x in targets})
        except Exception as e:
            s.update(stage="failed", note=f"예외 {e}"); print("  예외", e, flush=True)
        finally:
            common.write_json(sp, state)
    batch.wait_tasks(state)
    batch.recheck_sent(state, {x["code"]: x for x in targets})
    common.write_json(sp, state)
    print("배치 끝", flush=True)


if __name__ == "__main__":
    main()
