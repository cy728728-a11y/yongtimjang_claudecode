# -*- coding: utf-8 -*-
"""불사자 옵션 이미지 교체 — 1상품 단위 CLI.

    inspect  --code <코드> [--run-dir R]            판매 중 옵션 조회 → options.json (쓰기 없음)
    generate --run-dir R [--vids 2,3] [--force]     spec.json 대로 gpt-image-2 생성 → gen_<vid>.png
    apply    --run-dir R [--vids 2,3]               업로드 → 옵션 이미지 교체 → 재조회 검증 (쓰기)
    restore  --run-dir R                            before_apply.json 의 이전 이미지로 되돌림 (쓰기)

run-dir 기본값: C:/python_work/data/option-image/<코드>
공통 인자: --account <MCP계정이름> (없으면 scripts/.env 의 BULSAJA_ACCOUNT_KEY)
"""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bulsaja_client import OptionImageMCP, file_meta, upload_file_with_ticket  # noqa: E402
import option_rules as R  # noqa: E402

DATA_ROOT = Path("C:/python_work/data/option-image")


def _jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _jdump(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_dir(args, code=None):
    if args.run_dir:
        return Path(args.run_dir)
    if not code:
        sys.exit("--run-dir 가 필요하다")
    return DATA_ROOT / code.replace("/", "_")


def _vids_filter(args):
    return {v.strip() for v in (args.vids or "").split(",") if v.strip()} or None


def _open(args):
    mcp = OptionImageMCP(getattr(args, "account", None))
    mcp.open()
    print(f"[계정] {mcp.account_key} — {mcp.whoami()}")
    return mcp


# ---------------------------------------------------------------- inspect
def cmd_inspect(args):
    run_dir = _run_dir(args, args.code)
    mcp = _open(args)
    try:
        pid = mcp.find_product_id(args.code)
        wd = mcp.workdata(pid)
    finally:
        mcp.close()
    data = wd["data"]
    options = R.sale_options(data)
    total = len((data.get("uploadSkuProps") or {}).get("mainOption", {}).get("values") or [])
    _jdump(run_dir / "product.json", {
        "code": args.code, "productId": pid, "account": mcp.account_key,
        "name": wd.get("상품명"), "inspected_at": datetime.now().isoformat(timespec="seconds"),
        "thumbnails": data.get("uploadThumbnails") or [],
        "detail_images": R.detail_image_urls(data),
        "coupang_uploaded": bool((data.get("uploadedSuccessUrl") or {}).get("coupang")),
    })
    _jdump(run_dir / "options.json", options)
    print(f"[상품] {wd.get('상품명')}  (옵션 {total}개 중 판매 중 {len(options)}개)")
    print(f"{'번호':>4}  {'상태':<4}  옵션명  |  현재 이미지")
    for o in options:
        print(f"{o['vid']:>4}  {o['status']:<4}  {o['name']}  |  {o['image_url']}")

    # 검수용으로 현재 옵션 이미지를 로컬에 받는다 (cur_<번호>.jpg) — Claude 가 Read 로 연다
    from gen_image import download
    got = 0
    for o in options:
        if not o["image_url"]:
            continue
        ext = ".png" if o["image_url"].lower().endswith(".png") else ".jpg"
        try:
            download(o["image_url"], run_dir / f"cur_{o['vid']}{ext}")
            got += 1
        except Exception as e:
            print(f"[경고] {o['vid']} 현재 이미지 내려받기 실패: {e}")
    print(f"\n[저장] {run_dir}  (options.json · product.json · 현재 이미지 {got}장 cur_<번호>.*)")
    print("다음: cur_*.jpg 를 Read 로 열어 실물·스펙을 확인하고 spec.json 을 쓴 뒤 generate (SKILL.md §spec).")


# ---------------------------------------------------------------- generate
def cmd_generate(args):
    from gen_image import download, generate  # 키가 필요한 단계에서만 import
    run_dir = _run_dir(args)
    options = _jload(run_dir / "options.json")
    spec = _jload(run_dir / "spec.json")
    problems = R.validate_spec(spec, options)
    if problems:
        sys.exit("[spec 오류]\n- " + "\n- ".join(problems))
    targets, skipped = R.plan_targets(spec, options, force=args.force)
    only = _vids_filter(args)
    if only:
        targets = [(o, w) for o, w in targets if o["vid"] in only]
    for o, why in skipped:
        print(f"[건너뜀] {o['vid']} {o['name']}: {why}")
    if not targets:
        sys.exit("생성할 대상이 없다")
    if args.force and not only and len(targets) > 1:
        print(f"[경고] --force 를 --vids 없이 줬다 — {len(targets)}장 전부 재생성(과금)한다")
    size = R.image_size(spec)

    def work(o):
        vid = o["vid"]
        out = run_dir / f"gen_{vid}.png"
        if out.exists() and not args.force:
            return vid, "이미 있음(건너뜀, --force 로 재생성)", str(out)
        src_url = R.source_for(spec, o)
        ext = ".png" if src_url.lower().endswith(".png") else ".jpg"
        src = download(src_url, run_dir / f"src_{vid}{ext}")
        prompt = R.build_prompt(spec, vid)
        (run_dir / f"prompt_{vid}.txt").write_text(prompt, encoding="utf-8")
        t0 = time.time()
        last = None
        for attempt in (1, 2):  # 일시 오류(타임아웃·5xx·안전필터 흔들림)는 1회 자동 재시도
            try:
                generate(src, prompt, out, size=size)
                return vid, f"완료 {time.time() - t0:.0f}초" + (" (재시도)" if attempt == 2 else ""), str(out)
            except RuntimeError as e:
                last = e
        raise last

    print(f"[생성] {len(targets)}장 (동시 {args.parallel})")
    results = []
    with ThreadPoolExecutor(max_workers=args.parallel) as ex:
        for fut in [ex.submit(work, o) for o, _ in targets]:
            try:
                results.append(fut.result())
            except Exception as e:
                results.append(("?", f"실패: {type(e).__name__}: {e}", ""))
    for vid, msg, path in results:
        print(f"  {vid}: {msg}  {path}")
    fails = [r for r in results if r[1].startswith("실패")]
    print(f"\n[결과] 성공 {len(results) - len(fails)} / 실패 {len(fails)}")
    print("다음: gen_<번호>.png 를 전부 눈으로 검수(SKILL.md §검수)한 뒤 apply.")
    if fails:
        sys.exit(1)


# ---------------------------------------------------------------- apply
def _verify(mcp, pid, expected):
    """재조회로 vid → imageUrl 이 기대값과 같은지 확인. 불일치 목록 반환."""
    wd = mcp.workdata(pid)
    now = {o["vid"]: o["image_url"] for o in R.sale_options(wd["data"])}
    return [(vid, now.get(vid)) for vid, url in expected.items() if now.get(vid) != url]


def cmd_apply(args):
    run_dir = _run_dir(args)
    product = _jload(run_dir / "product.json")
    options = {o["vid"]: o for o in _jload(run_dir / "options.json")}
    only = _vids_filter(args)
    files = sorted(run_dir.glob("gen_*.png"))
    targets = []
    for f in files:
        vid = f.stem.split("_", 1)[1]
        if only and vid not in only:
            continue
        if vid not in options:
            print(f"[건너뜀] {vid}: options.json 에 없는 옵션")
            continue
        targets.append((vid, f))
    if not targets:
        sys.exit("반영할 gen_<번호>.png 가 없다 — generate 먼저")

    pid = product["productId"]
    mcp = _open(args)
    try:
        # 1) 되돌리기용 백업 — 옵션값 이미지와 가격탭 이미지를 따로 남긴다 (처음 값만 보존)
        before_p = run_dir / "before_apply.json"
        before = _jload(before_p) if before_p.exists() else {}
        for vid, _ in targets:
            before.setdefault(vid, {"image_url": options[vid]["image_url"],
                                    "price_tab_url": options[vid].get("price_tab_url") or "",
                                    "sku_id": options[vid].get("sku_id") or vid})
        _jdump(before_p, before)

        # 2) 티켓 발급 → 업로드
        metas = [file_meta(f, f"opt-{vid}") for vid, f in targets]
        ticket = mcp.request_upload_ticket(pid, metas)
        uploaded = {}
        for vid, f in targets:
            uploaded[vid] = upload_file_with_ticket(ticket, f"opt-{vid}", f)
            print(f"[업로드] {vid} {options[vid]['name']} → 완료")

        # 3) 옵션 이미지 교체 (확인키 2단계는 클라이언트가 처리)
        images = [{"vid": int(vid) if vid.isdigit() else vid, "imageUrl": url} for vid, url in uploaded.items()]
        r = mcp.update_option_images(pid, images)
        print(f"[교체] 변경 {r.get('변경수')}건")

        # 4) 재조회 검증 — 성공 응답만 믿지 않는다
        bad = _verify(mcp, pid, uploaded)
    finally:
        mcp.close()

    _jdump(run_dir / "after_apply.json", {
        "applied_at": datetime.now().isoformat(timespec="seconds"), "images": uploaded,
        "verify_failed": bad,
    })
    # 원장(append-only) — 무엇을 언제 어느 계정에 바꿨는지. 시트 대신 로컬 jsonl (SKILL.md §원장)
    with open(DATA_ROOT / "ledger.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "at": datetime.now().isoformat(timespec="seconds"), "account": mcp.account_key,
            "code": product.get("code"), "productId": pid, "name": product.get("name"),
            "applied": {vid: {"name": options[vid]["name"],
                              "before": before[vid]["image_url"] if isinstance(before[vid], dict) else before[vid],
                              "after": url}
                        for vid, url in uploaded.items()},
            "verify_failed": bad,
        }, ensure_ascii=False) + "\n")
    if bad:
        print("[검증 실패] 아래 옵션은 재조회 결과가 기대와 다르다:")
        for vid, now in bad:
            print(f"  {vid}: 현재 = {now}")
        sys.exit(1)
    print(f"[검증] {len(uploaded)}건 전부 재조회로 확인됨")
    print(f"[복원] 문제 있으면: run.py restore --run-dir \"{run_dir}\"")


# ---------------------------------------------------------------- restore
def cmd_restore(args):
    run_dir = _run_dir(args)
    product = _jload(run_dir / "product.json")
    before = _jload(run_dir / "before_apply.json")
    if not before:
        sys.exit("before_apply.json 이 비어 있다")
    pid = product["productId"]
    # 구형(문자열만 저장) 백업도 읽는다
    norm = {v: (b if isinstance(b, dict) else {"image_url": b, "price_tab_url": "", "sku_id": v})
            for v, b in before.items()}
    mcp = _open(args)
    try:
        # 1) 옵션값 이미지 되돌리기 (vid 지정 = 가격탭도 같은 주소로 바뀐다)
        images = [{"vid": int(v) if v.isdigit() else v, "imageUrl": b["image_url"]} for v, b in norm.items()]
        r = mcp.update_option_images(pid, images)
        changed = r.get("변경수")
        # 2) 원래 가격탭 이미지가 옵션값과 달랐던 것만 skuId 로 따로 되돌린다
        tabs = [{"skuId": str(b["sku_id"]), "imageUrl": b["price_tab_url"]}
                for b in norm.values() if b["price_tab_url"] and b["price_tab_url"] != b["image_url"]]
        if tabs:
            r2 = mcp.update_option_images(pid, tabs)
            print(f"[복원] 가격탭 이미지 별도 복원 {r2.get('변경수')}건")
        bad = _verify(mcp, pid, {v: b["image_url"] for v, b in norm.items()})
    finally:
        mcp.close()
    print(f"[복원] 변경 {changed}건, 검증 실패 {len(bad)}건")
    if bad:
        for vid, now in bad:
            print(f"  {vid}: 현재 = {now}")
        sys.exit(1)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="불사자 옵션 이미지 교체 (1상품)")
    ap.add_argument("--account", help="불사자 MCP 계정 이름 (기본: scripts/.env)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("inspect"); p.add_argument("--code", required=True); p.add_argument("--run-dir")
    p.set_defaults(fn=cmd_inspect)
    p = sub.add_parser("generate"); p.add_argument("--run-dir", required=True); p.add_argument("--vids")
    p.add_argument("--force", action="store_true"); p.add_argument("--parallel", type=int, default=3)
    p.set_defaults(fn=cmd_generate)
    p = sub.add_parser("apply"); p.add_argument("--run-dir", required=True); p.add_argument("--vids")
    p.set_defaults(fn=cmd_apply)
    p = sub.add_parser("restore"); p.add_argument("--run-dir", required=True)
    p.set_defaults(fn=cmd_restore)

    args = ap.parse_args()
    try:
        args.fn(args)
    except SystemExit:
        raise
    except Exception as e:
        sys.exit(f"[실패] {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
