# -*- coding: utf-8 -*-
"""Aside 가 다시 만든 옵션이미지(option-images/option-images.json 의 redo 항목)를 불사자에 반영한다.
- 반영 전 현재 옵션이미지를 option-images/before_option_images.json 에 백업(되돌리기용)
- 업로드 → 옵션이미지 교체(vid 단위) → 재조회로 주소 확인
- --thumb-vid N : 그 옵션 이미지를 대표 썸네일로도 세움(기존 대표는 뒤로)
사용법: python opt_img.py --outdir <상세 결과 폴더> [--dry-run] [--thumb-vid N] [--send]
"""
import argparse, hashlib, json, sys, time
from pathlib import Path
import common, bulsaja_client


def wd(m, pid):
    return (common.call(m, "bulsaja_product_workdata", {"productId": pid, "mode": "full"}).get("data") or {})


def cur_images(d):
    out = {}
    so = (d.get("uploadSkuProps") or {})
    for v in ((so.get("mainOption") or {}).get("values") or []):
        out[str(v.get("vid"))] = v.get("imageUrl")
    return out


def upload(m, pid, path, cid):
    # 크기 불일치(UPLOAD_FILE_MISMATCH)는 Aside 가 done.txt 뒤에 파일을 한 번 더 고쳐 쓴 탓(2026-11-16) — 새 티켓으로 1회 재시도
    for attempt in (1, 2, 3):
        data = Path(path).read_bytes()
        files = [{"clientId": cid, "sha256": hashlib.sha256(data).hexdigest(), "sizeBytes": len(data)}]
        tick = common.call(m, "bulsaja_image_upload_prepare", {"productId": pid, "purpose": "option", "files": files})
        try:
            return bulsaja_client.upload_file_with_ticket(tick, cid, path)
        except RuntimeError as e:
            busy = "_BUSY" in str(e)   # 503 업로드 몰림(2026-11-17) — 좀 쉬었다 재시도
            if attempt == 3 or not (busy or "UPLOAD_FILE_MISMATCH" in str(e)):
                raise
            time.sleep(60 if busy else 10)


def wait_stable(od, quiet=45, cap=600):
    """option-images 폴더 파일이 quiet 초 동안 안 바뀔 때까지 기다린다(done.txt 뒤 마무리 쓰기 대비)."""
    t0 = time.time()
    while time.time() - t0 < cap:
        newest = max((f.stat().st_mtime for f in Path(od).glob("*") if f.is_file()), default=0)
        if time.time() - newest >= quiet:
            return
        time.sleep(10)


def run(outdir, dry=False, thumb_vid=None):
    outdir = Path(outdir); pid = outdir.parts[-2]
    od = outdir / "option-images"
    wait_stable(od)
    items = [x for x in json.loads((od / "option-images.json").read_text(encoding="utf-8")) if x.get("action") == "redo"]
    if not items:
        return "skip", "다시 만든 옵션이미지 없음", None
    m = common.mcp()
    try:
        d = wd(m, pid); before = cur_images(d)
        if not before:   # 조회가 가끔 빈 값으로 온다(2026-11-16 Ru61c) — 한 번 더
            time.sleep(5); d = wd(m, pid); before = cur_images(d)
        gid = d.get("uploadSelectedMarketGroupId")
        miss = [x["vid"] for x in items if str(x["vid"]) not in before]
        if miss:
            return "fail", f"상품에 없는 옵션번호 {miss}", gid
        if dry:
            return "dry", f"{len(items)}장 교체 예정", gid
        bk = od / "before_option_images.json"
        if not bk.exists():
            common.write_json(bk, {"productId": pid, "images": before, "thumbnails": d.get("uploadThumbnails")})
        imgs = []
        for x in items:
            f = Path(x.get("file") or f"{x['vid']}.png")
            if not f.is_absolute():   # Aside 가 파일명만 적는 경우(2026-11-18 PONlO6)
                f = od / f.name
            url = upload(m, pid, str(f), f"opt{x['vid']}")
            imgs.append({"vid": x["vid"], "groupIndex": 0, "imageUrl": url})
        pre = common.call(m, "bulsaja_option_image_update", {"productId": pid, "images": imgs})
        tok = pre.get("confirmationToken")
        if not tok:
            return "fail", f"확인키 없음 {str(pre)[:300]}", gid
        common.call(m, "bulsaja_option_image_update", {"productId": pid, "images": imgs, "confirm": True, "confirmationToken": tok})
        after = cur_images(wd(m, pid))
        bad = [i["vid"] for i in imgs if after.get(str(i["vid"])) != i["imageUrl"]]
        common.write_json(od / "applied.json", {"productId": pid, "images": imgs, "verifyFail": bad})
        note = f"{len(imgs)}장 교체" + (f" · 확인 실패 {bad}" if bad else " · 재조회 일치")
        if thumb_vid is not None:
            url = next(i["imageUrl"] for i in imgs if str(i["vid"]) == str(thumb_vid))
            th = [url] + [t for t in (d.get("uploadThumbnails") or []) if t != url]
            th = th[:20]
            p2 = common.call(m, "bulsaja_thumbnail_update", {"productId": pid, "thumbnails": th})
            t2 = p2.get("confirmationToken")
            if t2:
                common.call(m, "bulsaja_thumbnail_update", {"productId": pid, "thumbnails": th, "confirm": True, "confirmationToken": t2})
                note += " · 대표 썸네일 교체"
        return ("fail" if bad else "applied"), note, gid
    finally:
        m.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", required=True); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--thumb-vid"); ap.add_argument("--send", action="store_true")
    a = ap.parse_args()
    try:
        res, note, gid = run(a.outdir, a.dry_run, a.thumb_vid)
        print(res, note)
        if res == "applied" and a.send:
            import batch
            pid = Path(a.outdir).parts[-2]
            print("전송", batch.market_send({"productId": pid, "marketGroupId": gid}))
    except Exception as e:
        print("오류", e); sys.exit(1)


# ── 배치 연결: 상세 지시서에 붙일 옵션이미지 지시(같은 Aside 세션에서 만든다, 2026-11-16 용팀장 승인) ──
def brief_lines(m, pid, outdir):
    """판매 중인 대표옵션 값과 현재 이미지 주소 → 지시서 문단. 옵션 이미지가 없으면 빈 문자열."""
    d = wd(m, pid)
    so = d.get("uploadSkuProps") or {}
    vals = [v for v in ((so.get("mainOption") or {}).get("values") or []) if v.get("imageUrl") and not v.get("exclude")]
    if not vals:
        return ""
    od = Path(outdir) / "option-images"
    rows = "\n".join(f"  - vid {v.get('vid')} | 옵션명 「{v.get('name')}」 | {v.get('imageUrl')}" for v in vals)
    return (
        "\n## 옵션 이미지 고급화 (상세를 다 만든 뒤, report.md 를 쓰기 전에 한다)\n"
        f"- 판매 중 옵션과 현재 옵션 이미지:\n{rows}\n"
        "1. 한 장씩 열어 본다. **중국어 글자·중국 판매처 로고·중국어 안내 띠/표가 있으면 다시 만든다.** 글자 없이 제품만 깔끔하면 건드리지 않는다(skip).\n"
        "2. 다시 만들 때: 1000×1000 정사각 PNG, 제품이 화면의 70% 안팎. **제품은 원본 사진 그대로** — 글자·로고·인포그래픽을 지우고 제품을 잘라 아이보리 배경에 올리는 '빼기 편집'만. 없는 각도·부품·색을 그리지 않는다. 제품에 실제로 인쇄된 글자는 지우지 않는다.\n"
        "   아래쪽 진갈색 띠에 한국어 라벨 한 줄(옵션명을 다듬은 짧은 이름 + 꼭 필요한 규격 1개). 옵션명과 다른 사실을 쓰지 않는다. 옵션끼리 배경·제품 크기·라벨 위치 통일. 마켓명 워터마크는 상세보다 연하게.\n"
        f"3. 저장: {od}/<vid>.png, 목록 {od}/option-images.json = [{{\"vid\":..,\"옵션명\":..,\"action\":\"redo\"|\"skip\",\"사유\":..,\"file\":..}}], 나란히 보는 {od}/preview.jpg, 끝나면 {od}/done.txt 에 다시 만든 장 수·건너뛴 장 수.\n"
        "- 옵션 이미지도 불사자 저장·업로드 금지(반영은 Claude Code 가 한다).\n")
