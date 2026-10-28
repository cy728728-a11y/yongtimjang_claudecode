# -*- coding: utf-8 -*-
"""대표 썸네일 마켓명 워터마크 — 상세와 같은 펜체·18도 대각선. 이미 있으면 건드리지 않는다.

- 대표(첫 번째) 썸네일만 바꾼다. 추가 썸네일은 그대로 둔다(2026-10-29 용팀장 지시).
- 이미 워터마크가 있는지: ① 우리가 넣은 기록(thumb/thumb_wm.json)의 주소가 지금 대표와 같다
  ② Aside verification.json 의 thumbnailWatermark 가 true. 둘 중 하나면 건너뛴다.
- 교체 전 썸네일 목록을 thumb/before_thumbs.json 에 백업. 되돌릴 때는 그 목록을 thumbnail_update 로 다시 넣는다.

사용법:
  python thumb_wm.py --code <판매자상품코드> --outdir <상세 결과 폴더> [--dry-run] [--send]
"""
import argparse
import hashlib
import json
import re
import sys
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

import common
import bulsaja_client

PEN = Path(__file__).resolve().parents[1] / "assets/NanumPenScript-Regular.ttf"
MAP = Path.home() / ".aside/u/0/memory/concepts/smartstore-market-number-map.md"
ANGLE = 18
OPACITY, OPACITY_COMPLEX, BUSY_TH = 0.24, 0.30, 0.25   # 썸네일은 제품이 화면 대부분이라 문턱을 낮춘다
DARK, LIGHT = (40, 38, 34), (250, 248, 244)
MAX_SIZE_FRAC = 0.15   # 글자 크기 상한(사진 폭 대비)
HALO_PX, HALO_RATIO = 7, 0.8   # 반대색 테두리 두께(홀수 px)·불투명도 비율


def market_name(market):
    """마켓번호 → 스마트스토어명(Aside 매핑표). 없으면 None — 이름을 지어내지 않는다."""
    try:
        for line in MAP.read_text(encoding="utf-8").splitlines():
            m = re.match(rf"\|\s*{re.escape(market)}\s*\|[^|]*\|\s*([^|]+?)\s*\|", line)
            if m:
                return m.group(1)
    except Exception:
        pass
    return None


def busy_frac(im):
    """8px 블록 표준편차가 12를 넘는 블록 비율 — 배경이 복잡한 사진이면 불투명도를 올린다."""
    g = im.convert("L"); w, h = g.size; bs = 8; busy = tot = 0
    for y in range(0, h - bs + 1, bs):
        for x in range(0, w - bs + 1, bs):
            tot += 1
            if ImageStat.Stat(g.crop((x, y, x + bs, y + bs))).stddev[0] > 12:
                busy += 1
    return busy / tot if tot else 0.0


def wm_mask(text, width_target, max_size=None):
    """글자 전체 길이가 width_target 이 되게 펜체로 그리고 18도 돌린 마스크.
    글자 수가 적은 마켓명(조흔가게 등)은 글씨가 너무 커지므로 max_size 로 자른다."""
    f100 = ImageFont.truetype(str(PEN), 100)
    base = sum(f100.getlength(c) for c in text)
    size = width_target / (base / 100 + 0.034 * (len(text) - 1))
    if max_size:
        size = min(size, max_size)
    f = ImageFont.truetype(str(PEN), int(round(size)))
    sp = 0.034 * size
    widths = [f.getlength(c) for c in text]
    cw, chh = int(sum(widths) + sp * len(text) + 40), int(size * 1.6)
    m = Image.new("L", (cw, chh), 0); d = ImageDraw.Draw(m)
    x = 20
    for c, w in zip(text, widths):
        d.text((x, chh * 0.7), c, font=f, fill=255, anchor="ls"); x += w + sp
    m = m.crop(m.getbbox())
    r = m.rotate(ANGLE, resample=Image.BICUBIC, expand=True)
    return r.crop(r.getbbox()), int(round(size))


def render(im, text):
    """사진 가운데를 가로지르는 워터마크 한 줄. 색은 글자 아래 밝기와 대비가 큰 쪽."""
    im = im.convert("RGB"); W, H = im.size
    frac = 0.82
    while True:
        r, size = wm_mask(text, W * frac, W * MAX_SIZE_FRAC)
        if r.size[0] <= W - 12 and r.size[1] <= H - 12:
            break
        frac -= 0.02
    lx, ly = (W - r.size[0]) // 2, (H - r.size[1]) // 2
    lum = ImageStat.Stat(im.crop((lx, ly, lx + r.size[0], ly + r.size[1])).convert("L"), r).mean[0]
    color = max((DARK, LIGHT), key=lambda c: abs(lum - (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2])))
    bf = busy_frac(im)
    op = OPACITY_COMPLEX if bf >= BUSY_TH else OPACITY
    # 무늬·명암이 섞인 사진에서도 읽히게 글자 둘레에 반대색 테두리를 옅게 깐다
    halo_col = LIGHT if color == DARK else DARK
    halo = r.filter(ImageFilter.MaxFilter(HALO_PX))
    im.paste(Image.new("RGB", r.size, halo_col), (lx, ly), halo.point(lambda v: round(v * op * HALO_RATIO)))
    im.paste(Image.new("RGB", r.size, color), (lx, ly), r.point(lambda v: round(v * op)))
    return im, {"text": text, "fontSizePx": size, "lengthRatio": round(frac, 2), "angleDeg": ANGLE,
                "opacity": op, "busyFrac": round(bf, 3), "color": "#%02X%02X%02X" % color, "halo": "#%02X%02X%02X" % halo_col,
                "bbox": [lx, ly, lx + r.size[0], ly + r.size[1]], "size": [W, H]}


def current_thumbs(m, pid):
    r = common.call(m, "bulsaja_product_workdata", {"productId": pid})
    return (r.get("data") or {}).get("uploadThumbnails") or []


def already_marked(outdir, thumbs):
    """(이미 있음?, 이유)"""
    rec = outdir / "thumb/thumb_wm.json"
    try:
        if rec.exists() and json.loads(rec.read_text(encoding="utf-8")).get("newUrl") == (thumbs or [None])[0]:
            return True, "우리가 넣은 워터마크 썸네일이 대표로 올라가 있음"
    except Exception:
        pass
    try:
        v = json.loads((outdir / "verification.json").read_text(encoding="utf-8"))
        if v.get("thumbnailWatermark") is True:
            return True, "Aside 확인: 대표 썸네일에 이미 마켓명 워터마크"
    except Exception:
        pass
    return False, ""


def make(m, pid, market, outdir):
    """워터마크 썸네일 파일만 만든다. (결과 dict | None, 메모)"""
    name = market_name(market)
    if not name:
        return None, f"마켓 {market} 매핑 없음 — 워터마크 보류"
    thumbs = current_thumbs(m, pid)
    if not thumbs:
        return None, "대표 썸네일 없음"
    done, why = already_marked(outdir, thumbs)
    if done:
        return None, f"건너뜀: {why}"
    td = outdir / "thumb"; td.mkdir(parents=True, exist_ok=True)
    resp = requests.get(thumbs[0], timeout=60); resp.raise_for_status()
    orig = Image.open(BytesIO(resp.content))
    (td / "thumb0_orig.jpg").write_bytes(resp.content)
    out, meta = render(orig, name)
    out.save(td / "thumb0_wm.jpg", quality=92)
    common.write_json(td / "before_thumbs.json", {"productId": pid, "thumbnails": thumbs})
    return {"thumbs": thumbs, "file": td / "thumb0_wm.jpg", "meta": meta}, f"워터마크 썸네일 생성 {td / 'thumb0_wm.jpg'}"


def upload(m, pid, path):
    data = Path(path).read_bytes()
    files = [{"clientId": "thumb0", "sha256": hashlib.sha256(data).hexdigest(), "sizeBytes": len(data)}]
    tick = common.call(m, "bulsaja_image_upload_prepare", {"productId": pid, "purpose": "thumbnail", "files": files})
    return bulsaja_client.upload_file_with_ticket(tick, "thumb0", path)


def apply(m, pid, outdir, made):
    """대표만 새 파일로 바꿔 저장 → 재조회로 확인. (성공?, 메모)"""
    url = upload(m, pid, made["file"])
    new = [url] + made["thumbs"][1:]
    pre = common.call(m, "bulsaja_thumbnail_update", {"productId": pid, "thumbnails": new})
    tok = pre.get("confirmationToken")
    if tok:
        common.call(m, "bulsaja_thumbnail_update",
                    {"productId": pid, "thumbnails": new, "confirm": True, "confirmationToken": tok})
    now = current_thumbs(m, pid)
    if (now or [None])[0] != url:
        return False, f"재조회 불일치: 대표 {str(now[:1])[:120]}"
    common.write_json(outdir / "thumb/thumb_wm.json", {"newUrl": url, "oldUrl": made["thumbs"][0], **made["meta"]})
    return True, "대표 썸네일 워터마크 반영"


def run(code, pid, market, outdir, dry=False):
    """배치·단건 공용. (결과 'applied'|'made'|'skipped'|'failed', 메모)"""
    m = common.mcp()
    try:
        made, note = make(m, pid, market, outdir)
        if not made:
            return ("skipped" if note.startswith("건너뜀") else "failed"), note
        if dry:
            return "made", note
        ok, note2 = apply(m, pid, outdir, made)
        return ("applied" if ok else "failed"), note2
    except Exception as e:
        return "failed", f"예외 {e}"
    finally:
        m.close()


def main():
    ap = argparse.ArgumentParser(description="대표 썸네일 마켓명 워터마크")
    ap.add_argument("--code", required=True)
    ap.add_argument("--outdir", required=True, help="상세 결과 폴더(…/<마켓>/<내부ID>/<날짜>_opus)")
    ap.add_argument("--dry-run", action="store_true", help="파일만 만들고 불사자는 안 바꾼다")
    ap.add_argument("--send", action="store_true", help="반영 뒤 스마트스토어 수정 전송")
    a = ap.parse_args()
    outdir = Path(a.outdir)
    market, pid = outdir.parts[-3], outdir.parts[-2]
    res, note = run(a.code, pid, market, outdir, a.dry_run)
    print(f"[썸네일] {a.code} {res} — {note}", flush=True)
    if res == "applied" and a.send:
        m = common.mcp()
        try:
            g = common.call(m, "bulsaja_product_workdata", {"productId": pid, "mode": "full"})
            gid = (g.get("data") or {}).get("uploadSelectedMarketGroupId")
        finally:
            m.close()
        import batch
        tid, r = batch.market_send({"productId": pid, "marketGroupId": gid})
        print(f"[전송] {a.code} taskId={tid} {r}", flush=True)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
