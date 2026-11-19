# -*- coding: utf-8 -*-
"""Aside 제작 전 준비 — Opus 토큰을 안 쓰는 일은 여기서 미리 한다(2026-11-19 토큰 절약).

1. 불사자 웹 API 로 product.json · list-row.json 받기(웹 토큰 ~/.eroom/bulsaja-web.json)
2. 원본 이미지 내려받기(originals/ — 상세 원본·현재 상세·썸네일·업로드 썸네일·옵션) + manifest.json
3. 한눈에 보기 모음(originals/_sheets/*.jpg — 파일명 표기) + 옵션·SKU 요약(originals/_facts.md)
4. 작업 폴더에 고정 도구(Aside 스킬 tools/) 복사 + work/job.json(마켓명 포함)

실패해도 예외를 밖으로 던지지 않고 False 를 돌려준다 → 지시서가 예전 방식(Aside 가 직접 받기)으로 나간다.
"""
import concurrent.futures as cf
import html
import json
import os
import re
import shutil
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".claude/skills/sourcing-inspect/scripts"))
ASIDE = Path.home() / ".aside/u/0"
TOOLS = ASIDE / "skills/user/smartstore-detail-page/tools"
MAP = ASIDE / "memory/concepts/smartstore-market-number-map.md"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
FONT = str(TOOLS / "Pretendard-Regular.otf")


def market_name(market):
    """마켓번호 → 스마트스토어명(Aside 대응표)."""
    for line in MAP.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[0] == market:
            return cells[2]
    return None


def fetch_product(pid):
    import requests
    import sourcing_api as s
    h = s._headers(s.load_token())
    r = requests.get(f"{s.API}/api/manage/sourcing-product/{pid}", headers=h, timeout=60)
    r.raise_for_status()
    body = {"request": {"startRow": 0, "endRow": 5, "sortModel": [],
                        "filterModel": {"ID": {"filterType": "text", "type": "equals", "filter": pid}},
                        "viewCountRange": {"mode": "all"}}}
    r2 = requests.post(f"{s.API}/api/manage/list/serverside", headers=h, json=body, timeout=60)
    r2.raise_for_status()
    return r.text, r2.text


def _urls(rc):
    s = html.unescape((rc or "").replace("\\/", "/"))
    return re.findall(r'src="([^"]+)"', s)


def download(d, orig):
    jobs = []
    for i, u in enumerate(_urls((d.get("detailContents") or {}).get("renderContent")), 1):
        jobs.append((f"source-{i:02d}", u))
    for i, u in enumerate(_urls((d.get("uploadDetailContents") or {}).get("renderContent")), 1):
        jobs.append((f"current-detail-{i:02d}", u))
    for i, u in enumerate(d.get("thumbnails") or [], 1):
        jobs.append((f"thumb-{i:02d}", u))
    for i, u in enumerate(d.get("uploadThumbnails") or [], 1):
        jobs.append((f"upload-thumb-{i:02d}", u))
    opts = []
    for i, v in enumerate(((d.get("uploadSkuProps") or {}).get("mainOption") or {}).get("values") or [], 1):
        opts.append({"n": i, "vid": v.get("vid"), "name": v.get("name"), "_name": v.get("_name"),
                     "exclude": v.get("exclude"), "imageUrl": v.get("imageUrl")})
        if v.get("imageUrl"):
            jobs.append((f"option-{i}", v["imageUrl"]))

    def get(j):
        name, u = j
        ext = os.path.splitext(u.split("?")[0])[1].lower() or ".jpg"
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            ext = ".jpg"
        p = orig / f"{name}{ext}"
        err = None
        for t in range(5):
            try:
                time.sleep(0.3 if t == 0 else 3 * t)
                req = urllib.request.Request(u, headers={"User-Agent": UA, "Referer": "https://item.taobao.com/"})
                p.write_bytes(urllib.request.urlopen(req, timeout=20).read())
                im = Image.open(p); im.load()
                return name, p.name, im.size, None
            except Exception as e:
                err = str(e)
        return name, None, None, err

    with cf.ThreadPoolExecutor(3) as ex:
        res = list(ex.map(get, jobs))
    (orig / "manifest.json").write_text(json.dumps({"jobs": jobs, "options": opts, "files": res},
                                                   ensure_ascii=False, indent=1), encoding="utf-8")
    return res, opts


def sheet(files, out, w=300, cols=4):
    """파일명을 붙인 축소 모음 한 장."""
    f = ImageFont.truetype(FONT, 18)
    ths = []
    for fp in files:
        try:
            im = Image.open(fp).convert("RGB")
        except Exception:
            continue
        if im.width < 20 or im.height < 20:
            continue
        h = min(int(im.height * w / im.width), w * 3)
        ths.append((fp.name, im.resize((w, int(im.height * w / im.width))).crop((0, 0, w, h)), im.size))
    if not ths:
        return None
    rows = [ths[i:i + cols] for i in range(0, len(ths), cols)]
    tot = sum(max(t[1].height for t in r) + 26 for r in rows)
    S = Image.new("RGB", (cols * (w + 6), tot), (255, 255, 255))
    d = ImageDraw.Draw(S)
    y = 0
    for r in rows:
        for k, (nm, t, sz) in enumerate(r):
            S.paste(t, (k * (w + 6), y + 24))
            d.text((k * (w + 6) + 2, y + 2), f"{nm} {sz[0]}x{sz[1]}", font=f, fill=(200, 0, 0))
        y += max(t[1].height for t in r) + 26
    S.save(out, quality=82)
    return out


def facts(d, lr, opts):
    skus = d.get("uploadSkus") or []
    lines = [f"- 타오바오 제목: {d.get('originalProductName')}",
             f"- 상품명(업로드): {d.get('uploadCommonProductName')}",
             f"- 브랜드 필드: {d.get('brand')} · 해외배송비: {d.get('overseaDeliveryFee')}",
             f"- 마켓그룹(목록): {lr.get('marketGroupName')} · 잠금(isBlocked): {lr.get('isBlocked')}",
             f"- 타오바오 주소: {d.get('product_url')}",
             "", "| n | vid | 옵션명 | 원문 | 제외 | 파일 |", "|---|---|---|---|---|---|"]
    for o in opts:
        lines.append(f"| {o['n']} | {o['vid']} | {o['name']} | {o['_name']} | {o['exclude']} | option-{o['n']}.* |")
    sub = (d.get("uploadSkuProps") or {}).get("subOption")
    lines += ["", f"- subOption: {json.dumps(sub, ensure_ascii=False)[:400]}", "", "| SKU | 원문 | 제외 | 판매가 |", "|---|---|---|---|"]
    for s in skus:
        lines.append(f"| {s.get('text')} | {s.get('_text')} | {s.get('exclude')} | {s.get('sale_price')} |")
    return "\n".join(lines) + "\n"


def run(t, outdir, brief_path, model, log=print):
    """준비 성공이면 True. outdir = .../<마켓>/<ID>/<날짜>_opus"""
    try:
        outdir = Path(outdir)
        pid = t["productId"]
        orig = outdir.parent / "originals"
        orig.mkdir(parents=True, exist_ok=True)
        mk = market_name(t["market"])
        if not mk:
            log(f"  [준비] 마켓명 못 찾음 {t['market']} — 예전 방식")
            return False
        if not (orig / "product.json").exists() or not list(orig.glob("source-*")):
            pj, lj = fetch_product(pid)
            (orig / "product.json").write_text(pj, encoding="utf-8")
            (orig / "list-row.json").write_text(lj, encoding="utf-8")
            j = json.loads(pj); d = j.get("data", j)
            res, opts = download(d, orig)
            bad = [r for r in res if r[3]]
            if bad:
                log(f"  [준비] 내려받기 실패 {len(bad)}건(계속): {[b[0] for b in bad][:5]}")
        j = json.loads((orig / "product.json").read_text(encoding="utf-8")); d = j.get("data", j)
        lj = json.loads((orig / "list-row.json").read_text(encoding="utf-8"))
        lr = lj["rowData"][0] if lj.get("rowData") else lj
        opts = json.loads((orig / "manifest.json").read_text(encoding="utf-8"))["options"]
        sh = orig / "_sheets"; sh.mkdir(exist_ok=True)
        groups = {"source": sorted(orig.glob("source-*")), "thumb": sorted(orig.glob("thumb-*")),
                  "option": sorted(orig.glob("option-*"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))}
        made = []
        for g, fs in groups.items():
            for i in range(0, len(fs), 12):
                o = sheet(fs[i:i + 12], sh / f"{g}-{i // 12 + 1}.jpg")
                if o:
                    made.append(o.name)
        (orig / "_facts.md").write_text(facts(d, lr, opts), encoding="utf-8")
        work = outdir / "work"
        work.mkdir(parents=True, exist_ok=True)
        (outdir / "clean").mkdir(exist_ok=True)
        (outdir / "option-images" / "work").mkdir(parents=True, exist_ok=True)
        for f in TOOLS.iterdir():
            if f.is_file():
                shutil.copy2(f, work / f.name)
        (work / "job.json").write_text(json.dumps({
            "productId": pid, "code": t["code"], "market": t["market"], "marketName": mk,
            "date": outdir.name.split("_")[0], "brief": str(brief_path), "model": model},
            ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"  [준비] 원본 {len(list(orig.glob('*.*')))}개 · 모음 {len(made)}장 · 도구 복사 · 마켓명 {mk}")
        return True
    except Exception as e:
        log(f"  [준비] 실패 — 예전 방식으로 진행: {e}")
        return False
