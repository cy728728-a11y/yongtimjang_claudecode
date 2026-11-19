# -*- coding: utf-8 -*-
"""옵션이미지 파이썬 제작(Aside 없이) — 시험판(2026-11-19 용팀장 요청: 토큰 절약).

판단을 맥 내장 기능으로 대신한다.
- 덧붙인 글자 찾기: Vision 글자인식(중국어·한국어·영어). 2글자 이상·신뢰도 0.5 이상만 센다.
- 제품 떼어내기: Vision 피사체 분리(아이폰 '피사체 들어올리기'와 같은 기능).
- 합성: Aside 고정 도구 opt_build.py 를 그대로 써서 모양(아이보리·진갈색 띠·펜체 워터마크)을 맞춘다.
판정
- 글자 없음 → skip(그대로 둠)
- 글자가 제품 밖에만 있음 → redo(떼어내면 글자가 빠진다)
- 한글·한자 글자가 제품 위에 걸침(도장·번역 띠 등) → aside(사람 눈 같은 판단 필요 → Aside 로 넘김)
- 떼어내기 실패·면적 이상·떼어낸 뒤에도 글자가 남음 → aside
불사자에는 아무것도 올리지 않는다(결과 파일만).

사용(시험): python opt_py.py pilot --n 30 --out ~/python_work/data/detail-opus/opt-py-pilot
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import Vision
from AppKit import NSBitmapImageRep
from Foundation import NSData
from Quartz import CIImage

TOOLS = Path.home() / ".aside/u/0/skills/user/smartstore-detail-page/tools"
BATCHES = Path.home() / "python_work/data/detail-opus/batches"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
HANGUL_CJK = re.compile(r"[一-鿿가-힣]")
MIN_CONF = 0.3   # 0.5 는 빨간 굵은 글씨·디자인 글씨를 놓쳤다(시험 1회차 8줄)


# ── Vision ────────────────────────────────────────────────────────────────
def _handler(path):
    data = open(path, "rb").read()
    return Vision.VNImageRequestHandler.alloc().initWithData_options_(NSData.dataWithBytes_length_(data, len(data)), None)


def read_text(path, upscale=True):
    """[(글자, 신뢰도, (x0,y0,x1,y1) 0~1, 위가 0)] — 못 찾으면 2배 확대해서 한 번 더."""
    out = _read_text(path)
    if out or not upscale:
        return out
    im = Image.open(path).convert("RGB")
    big = str(path) + ".x2.png"
    im.resize((im.width * 2, im.height * 2), Image.LANCZOS).save(big)
    try:
        return _read_text(big)
    finally:
        os.remove(big)


def _read_text(path):
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLanguages_(["zh-Hans", "ko-KR", "en-US"])
    req.setRecognitionLevel_(0)
    _handler(path).performRequests_error_([req], None)
    out = []
    for r in req.results() or []:
        c = r.topCandidates_(1)
        if not c:
            continue
        s = str(c[0].string()).strip()
        if len(re.sub(r"\s", "", s)) < 2 or c[0].confidence() < MIN_CONF:
            continue
        b = r.boundingBox()
        x0, y0, w, h = b.origin.x, b.origin.y, b.size.width, b.size.height
        out.append((s, float(c[0].confidence()), (x0, 1 - y0 - h, x0 + w, 1 - y0)))
    return out


def _buf2np(buf):
    rep = NSBitmapImageRep.alloc().initWithCIImage_(CIImage.imageWithCVPixelBuffer_(buf))
    png = rep.representationUsingType_properties_(4, {})  # 4 = PNG
    return np.asarray(Image.open(__import__("io").BytesIO(bytes(png))).convert("L")).astype(np.float32) / 255.0


def subject_mask(path):
    """피사체 마스크(0~1 float, 원본 크기). 가장 큰 물건 + 그 35% 이상 되는 물건만 남긴다
    (집게·잎 같은 곁 조각 제거, 시험 1회차 11줄). 못 찾으면 None."""
    from Foundation import NSIndexSet
    h = _handler(path)
    req = Vision.VNGenerateForegroundInstanceMaskRequest.alloc().init()
    h.performRequests_error_([req], None)
    res = req.results() or []
    if not res:
        return None
    obs = res[0]
    idx = list(obs.allInstances())
    masks = []
    for i in idx:
        buf, _ = obs.generateScaledMaskForImageForInstances_fromRequestHandler_error_(NSIndexSet.indexSetWithIndex_(i), h, None)
        if buf is not None:
            masks.append(_buf2np(buf))
    if not masks:
        return None
    areas = [float((m > 0.5).sum()) for m in masks]
    top = max(areas)
    keep = [m for m, a in zip(masks, areas) if a >= 0.35 * top]
    return np.maximum.reduce(keep)


def humans(path):
    """사람 상자들 (x0,y0,x1,y1) 0~1, 위가 0"""
    req = Vision.VNDetectHumanRectanglesRequest.alloc().init()
    _handler(path).performRequests_error_([req], None)
    out = []
    for r in req.results() or []:
        b = r.boundingBox()
        out.append((b.origin.x, 1 - b.origin.y - b.size.height, b.origin.x + b.size.width, 1 - b.origin.y))
    return out


def red_overlay(path, m):
    """제품 밖에 빨간 글씨·도장 같은 진한 빨강이 있나(글자인식이 못 읽는 디자인 글씨 대비)."""
    im = np.asarray(Image.open(path).convert("RGB")).astype(np.int16)
    if im.shape[:2] != m.shape:
        return False
    red = (im[..., 0] > 170) & (im[..., 1] < 90) & (im[..., 2] < 90) & (m < 0.2)
    return float(red.mean()) > 0.002


# ── 판정 ─────────────────────────────────────────────────────────────────
def judge(path):
    """→ (action, reason, alpha|None, texts)"""
    texts = read_text(path)
    m = subject_mask(path)
    if not texts and (m is None or not red_overlay(path, m)):
        return "skip", "덧붙인 글자 없음", None, texts
    if m is None:
        return "aside", "제품 떼어내기 실패", None, texts
    H, W = m.shape
    frac = float((m > 0.5).mean())
    if frac < 0.08 or frac > 0.92:   # 너무 작으면 엉뚱한 물건(확대 동그라미 등)을 뗐을 가능성
        return "aside", f"떼어낸 면적 이상 {frac:.0%}", None, texts
    for x0, y0, x1, y1 in humans(path):   # 천막 대신 사람만 떼는 실수(시험 1회차)
        hb = m[int(y0 * H):int(y1 * H), int(x0 * W):int(x1 * W)]
        if hb.size and float((hb > 0.5).sum()) > 0.3 * float((m > 0.5).sum()):
            return "aside", "떼어낸 게 사람 위주", None, texts
    for s, cf, (x0, y0, x1, y1) in texts:
        bx = m[int(y0 * H):max(int(y1 * H), int(y0 * H) + 1), int(x0 * W):max(int(x1 * W), int(x0 * W) + 1)]
        ov = float((bx > 0.5).mean()) if bx.size else 0
        if ov > 0.5 and HANGUL_CJK.search(s):
            return "aside", f"제품 위 글자 「{s[:20]}」", None, texts
    # 떼어낸 결과에 글자가 남았는지 다시 확인
    im = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
    a = m[..., None]
    chk = (im * a + 255 * (1 - a)).astype(np.uint8)
    tmp = str(path) + ".chk.png"
    Image.fromarray(chk).save(tmp)
    left = [s for s, _, _ in read_text(tmp)]          # 어떤 글자든 남으면(치수선 숫자 포함) 넘긴다
    os.remove(tmp)
    if left:
        return "aside", f"떼어낸 뒤에도 글자 「{left[0][:20]}」", None, texts
    return "redo", "글자: " + " / ".join(s for s, _, _ in texts)[:80], m, texts


def label_of(name):
    """옵션명 → 라벨(짧게 다듬기만, 사실 추가 없음)."""
    s = re.sub(r"[一-鿿]+", "", str(name or "")).strip()
    s = re.sub(r"(?<=\d)\s*[xX*×]\s*(?=\d)", " × ", s)
    s = re.sub(r"\s+", " ", s)
    f = ImageFont.truetype(str(TOOLS / "Pretendard-Bold.otf"), 44)
    while s and f.getlength(s) > 880:
        s = s[:-1]
    return s.strip() or "옵션"


# ── 상품 하나 ─────────────────────────────────────────────────────────────
def get(url, cache):
    if url in cache:
        return cache[url]
    data = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30).read()
    cache[url] = data
    return data


def make(code, market_name, opts, root, py):
    """opts: [{vid, name, url}] → root/<code>/ 에 결과. 반환: [{vid, action, reason, label}]"""
    d = root / code
    if d.exists():
        shutil.rmtree(d)
    run = d / "run"                     # opt_build 은 originals 를 결과 폴더의 형제로 찾는다
    work, orig, wk = run / "work", d / "originals", run / "option-images/work"
    for p in (work, orig, wk):
        p.mkdir(parents=True, exist_ok=True)
    for f in ("opt_build.py", "Pretendard-Bold.otf", "Pretendard-Regular.otf", "NanumPenScript-Regular.ttf"):
        shutil.copy(TOOLS / f, work / f)
    (work / "job.json").write_text(json.dumps({"marketName": market_name}, ensure_ascii=False), encoding="utf-8")
    cache, memo, spec, cut, res = {}, {}, [], {}, []
    for o in opts:
        data = get(o["url"], cache)
        md5 = hashlib.md5(data).hexdigest()
        src = f"option-{o['vid']}.jpg"
        (orig / src).write_bytes(data)
        if md5 not in memo:                       # 같은 사진은 한 번만 판정
            memo[md5] = judge(orig / src)
        act, why, alpha, _ = memo[md5]
        lab = label_of(o["name"])
        res.append({"vid": o["vid"], "action": act, "reason": why, "label": lab})
        if act == "redo":
            np.save(wk / f"alpha_{o['vid']}.npy", alpha)
            ys, xs = np.where(alpha > 0.5)
            cut[str(o["vid"])] = {"keep": [0, 0, alpha.shape[1], alpha.shape[0]],
                                  "bbox": [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]}
            spec.append({"vid": o["vid"], "action": "redo", "src": src, "label": lab, "name": o["name"], "reason": why, "mode": "cutout"})
        else:
            spec.append({"vid": o["vid"], "action": "skip", "src": src, "name": o["name"], "reason": why})
    (wk / "cut.json").write_text(json.dumps(cut), encoding="utf-8")
    (wk / "spec.json").write_text(json.dumps({"items": spec}, ensure_ascii=False), encoding="utf-8")
    if any(x["action"] == "redo" for x in spec):
        r = subprocess.run([py, "opt_build.py"], cwd=work, capture_output=True, text=True)
        if r.returncode:
            for x in res:
                if x["action"] == "redo":
                    x.update(action="aside", reason="합성 실패 " + r.stderr.strip().splitlines()[-1][:80])
    (d / "py_result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


# ── 시험: Aside 가 이미 만든 상품과 비교 ───────────────────────────────────
FONT = None


def tile(img, w, text, sub=""):
    global FONT
    FONT = FONT or ImageFont.truetype(str(TOOLS / "Pretendard-Regular.otf"), 17)
    t = Image.new("RGB", (w, w + 48), (255, 255, 255))
    if img is not None:
        im = img.convert("RGB")
        im.thumbnail((w, w))
        t.paste(im, ((w - im.width) // 2, (w - im.height) // 2))
    dr = ImageDraw.Draw(t)
    dr.text((6, w + 4), text[:34], font=FONT, fill=(20, 20, 20))
    dr.text((6, w + 25), re.sub(r"[\u4e00-\u9fff]+", "…", sub)[:34], font=FONT, fill=(150, 60, 40))
    return t


def compare_sheet(code, title, rows, out):
    """한 줄 = 옵션 하나: 원본 | Aside | 파이썬"""
    w = 300
    sheet = Image.new("RGB", (3 * (w + 8) + 8, 40 + len(rows) * (w + 56)), (70, 70, 70))
    dr = ImageDraw.Draw(sheet)
    dr.text((10, 8), f"{code} · {title}   [원본 | Aside | 파이썬]", font=ImageFont.truetype(str(TOOLS / "Pretendard-Bold.otf"), 20), fill=(255, 255, 255))
    for i, (orig, a_img, a_txt, p_img, p_txt) in enumerate(rows):
        y = 40 + i * (w + 56)
        sheet.paste(tile(orig, w, "원본"), (8, y))
        sheet.paste(tile(a_img, w, "Aside", a_txt), (w + 16, y))
        sheet.paste(tile(p_img, w, "파이썬", p_txt), (2 * w + 24, y))
    sheet.save(out, quality=85)


def pilot(n, root, py):
    sys.path.insert(0, str(Path(__file__).parent))
    import prep
    root.mkdir(parents=True, exist_ok=True)
    (root / "compare").mkdir(exist_ok=True)
    picked = []
    for bd in ("opt-1117", "opt-1116"):
        st = json.loads((BATCHES / bd / "state.json").read_text())
        for t in json.loads((BATCHES / bd / "targets.json").read_text()):
            if st.get(t["code"], {}).get("stage") != "sent" or t["name"].startswith("비즈"):
                continue
            od = Path(t["outdir"]) / "option-images"
            if (od / "before_option_images.json").exists() and (od / "option-images.json").exists():
                picked.append(t)
            if len(picked) >= n:
                break
        if len(picked) >= n:
            break
    summary = []
    for t in picked:
        od = Path(t["outdir"]) / "option-images"
        before = json.loads((od / "before_option_images.json").read_text())["images"]
        aside = {str(e["vid"]): e for e in json.loads((od / "option-images.json").read_text())}
        opts = [{"vid": v, "name": aside.get(str(v), {}).get("옵션명", ""), "url": u} for v, u in before.items()
                if str(v) in aside and u]
        try:
            res = make(t["code"], prep.market_name(t["market"]) or t["market"], opts, root, py)
        except Exception as e:
            print("실패", t["code"], e, flush=True)
            continue
        rows = []
        for r in res:
            v = str(r["vid"]); a = aside[v]
            af = a.get("file")
            af = (Path(af) if af and os.path.isabs(af) else od / Path(af).name) if af else None
            pf = root / t["code"] / "run/option-images" / f"{v}.png"
            rows.append((Image.open(root / t["code"] / "originals" / f"option-{v}.jpg"),
                         Image.open(af) if af and af.exists() else None, a.get("action", ""),
                         Image.open(pf) if r["action"] == "redo" and pf.exists() else None,
                         {"redo": "다시 만듦", "skip": "그대로 둠", "aside": "Aside로 넘김"}[r["action"]] + " · " + r["reason"][:22]))
        compare_sheet(t["code"], t["name"][:24], rows, root / "compare" / f"{t['code']}.jpg")
        summary.append({"code": t["code"], "name": t["name"], "market": t["market"],
                        "items": [{**r, "aside": aside[str(r["vid"])].get("action")} for r in res]})
        print(t["code"], [(r["vid"], r["action"]) for r in res], flush=True)
    (root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pilot")
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--out", default=str(Path.home() / "python_work/data/detail-opus/opt-py-pilot"))
    a = ap.parse_args()
    try:
        pilot(a.n, Path(a.out).expanduser(), sys.executable)
    except Exception as e:
        print("오류", e)
        sys.exit(1)
