# -*- coding: utf-8 -*-
"""상세페이지 '파이썬 대장' 제작(2026-11-19 토큰 절약 2단계).

Aside 에이전트가 50단계를 도는 대신, 파이썬이 순서를 쥐고 Claude 는 판단만 2~4번 한다.
  1. prep.run — 상품 정보·원본 내려받기, 작업 폴더에 고정 도구 복사, job.json
  2. 좌표 눈금 모음 사진 생성(중복 제거) → Claude 1회: 검수·컷 좌표·장 설계·카피·메타를 JSON 으로
  3. cuts_def.py · spec.json 작성 → tools/tpl.py 로 그리기(글자 넘침이면 오류를 돌려보내 다시 받기, 최대 2회)
  4. qa → protect → 완성본 축소 모음 → Claude 1회: 눈 검수(고칠 장만 다시 받기) → 다시 그리기 1회
  5. finalize(cuts.json·preview·zip·verification) + plan.md · report.md
결과 파일은 Aside 방식과 같아서 batch.py 의 검수·반영·전송을 그대로 탄다.
Claude 호출은 Claude Code(claude -p) 로 하고 도구·MCP·설정을 다 꺼서 기본으로 붙는 내용을 없앤다(571토큰).

사용(단건 시험): python detail_py.py --code <판매자상품코드> --batch <배치이름> [--out <폴더>]
"""
import argparse
import numpy as np
import base64
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import prep  # noqa: E402

HERE = Path(__file__).resolve().parent
APY = str(Path.home() / ".aside/runtime/bin/python3")      # 고정 도구는 Aside 파이썬(cv2·scipy 있음)
RULES = (HERE / "detail_py_rules.md").read_text(encoding="utf-8")
MODEL = "claude-opus-5-5"
FONT = str(prep.TOOLS / "Pretendard-Regular.otf")


def log(m):
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


# ---------------- Claude 한 세션(여러 번 묻기) ----------------
class Chat:
    def __init__(self, system, effort="high"):
        cmd = ["claude", "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
               "--tools", "", "--model", MODEL, "--effort", effort, "--no-session-persistence",
               "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--setting-sources", "",
               "--disable-slash-commands", "--system-prompt", system]
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, cwd="/tmp", bufsize=1)
        self.cost = 0.0
        self.calls = 0
        self.usage = []

    def ask(self, content, timeout=900):
        self.p.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": content}}) + "\n")
        self.p.stdin.flush()
        t0 = time.time()
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("Claude 응답 끊김: " + (self.p.stderr.read() or "")[-400:])
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("type") == "result":
                self.calls += 1
                self.cost = o.get("total_cost_usd") or self.cost
                self.usage.append(o.get("usage"))
                if o.get("is_error"):
                    raise RuntimeError("Claude 오류: " + str(o.get("result"))[:300])
                return o.get("result") or ""
            if time.time() - t0 > timeout:
                raise TimeoutError("Claude 응답 시간초과")

    def close(self):
        try:
            self.p.stdin.close(); self.p.wait(timeout=30)
        except Exception:
            self.p.kill()


def img_block(path_or_im, q=82):
    im = path_or_im if isinstance(path_or_im, Image.Image) else Image.open(path_or_im)
    buf = io.BytesIO(); im.convert("RGB").save(buf, "JPEG", quality=q)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.b64encode(buf.getvalue()).decode()}}


def parse_json(text):
    m = re.search(r"```json\s*(.*?)```", text, re.S)
    s = m.group(1) if m else text[text.find("{"):text.rfind("}") + 1]
    return json.loads(s)


# ---------------- 좌표 눈금 모음 ----------------
def grid_tiles(orig):
    """원본(중복 제거) → [(라벨, 눈금 타일)] — 긴 사진은 1600px 단위로 쪼갠다."""
    F = ImageFont.truetype(FONT, 15)
    seen = {}; tiles = []
    files = sorted(orig.glob("source-*"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0)) + \
        sorted(orig.glob("thumb-*")) + \
        sorted([p for p in orig.glob("option-*") if not p.stem.startswith("option-raw")], key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
    for fp in files:
        try:
            h = hashlib.md5(fp.read_bytes()).hexdigest()
            im = Image.open(fp).convert("RGB")
        except Exception:
            continue
        if im.width < 40 or im.height < 40:
            continue
        if h in seen:
            seen[h].append(fp.name); continue
        seen[h] = [fp.name]
        w = 380; s = w / im.width
        for y0 in range(0, im.height, 1600):
            seg = im.crop((0, y0, im.width, min(im.height, y0 + 1600)))
            t = seg.resize((w, max(1, int(seg.height * s)))); d = ImageDraw.Draw(t)
            step = 50 if max(im.size) < 900 else 100
            for y in range((y0 // step + 1) * step if y0 % step else y0, y0 + seg.height, step):
                yy = (y - y0) * s
                d.line([(0, yy), (w, yy)], fill=(255, 0, 0) if y % 100 == 0 else (0, 160, 255), width=1)
                if y % 100 == 0: d.text((2, yy + 1), str(y), font=F, fill=(255, 0, 0))
            for x in range(0, im.width, step):
                d.line([(x * s, 0), (x * s, t.height)], fill=(255, 0, 0) if x % 100 == 0 else (0, 160, 255), width=1)
                if x % 100 == 0 and x: d.text((x * s + 2, 2), str(x), font=F, fill=(255, 0, 0))
            lab = f"{fp.name} {im.width}x{im.height}" + (f" (y {y0}~)" if im.height > 1600 else "")
            tiles.append((lab, t))
    dups = {v[0]: v[1:] for v in seen.values() if len(v) > 1}
    return tiles, dups


def pack(tiles, out_dir, cols=4, maxh=1560):
    F = ImageFont.truetype(FONT, 16)
    sheets = []; row = []; rows = []; H = 0
    def flush_sheet():
        nonlocal rows, H
        if not rows: return
        S = Image.new("RGB", (cols * 386, H), "white"); d = ImageDraw.Draw(S); y = 0
        for r in rows:
            rh = max(t.height for _, t in r) + 22
            for k, (lab, t) in enumerate(r):
                S.paste(t, (k * 386, y + 20)); d.text((k * 386 + 2, y + 1), lab, font=F, fill=(200, 0, 0))
            y += rh
        p = out_dir / f"grid-{len(sheets) + 1}.jpg"; S.save(p, quality=80); sheets.append(p)
        rows = []; H = 0
    for lab, t in tiles:
        row.append((lab, t))
        if len(row) == cols:
            rh = max(x.height for _, x in row) + 22
            if H + rh > maxh: flush_sheet()
            rows.append(row); H += rh; row = []
    if row:
        rh = max(x.height for _, x in row) + 22
        if H + rh > maxh: flush_sheet()
        rows.append(row); H += rh
    flush_sheet()
    return sheets


# ---------------- 파일 쓰기 ----------------
def write_cuts_def(work, J, orig):
    cuts = {}; info = {}; errs = []
    for k, c in (J.get("cuts") or {}).items():
        fp = orig / c["src"]
        if not fp.exists():
            errs.append(f"컷 {k}: 파일 {c['src']} 없음"); continue
        W_, H_ = Image.open(fp).size
        x0, y0, x1, y1 = [int(round(v)) for v in c["bbox"]]
        x0, y0 = max(0, x0), max(0, y0); x1, y1 = min(W_, x1), min(H_, y1)
        if x1 - x0 < 80 or y1 - y0 < 80:
            errs.append(f"컷 {k}: bbox 너무 작음/잘못됨 {c['bbox']} (원본 {W_}x{H_})"); continue
        cuts[k] = (c["src"], (x0, y0, x1, y1))
        info[k] = (c.get("type", "사용장면"), c.get("shows", ""), c.get("fact", ""), c.get("text", "없음(크롭 후)"))
    pr = J.get("protect") or {}
    PROTECT = {"FORCE_COMPLEX_CUTS": [k for k in pr.get("FORCE_COMPLEX_CUTS", []) if k in cuts],
               "COLOR_FIX": {k: tuple(v) for k, v in (pr.get("COLOR_FIX") or {}).items() if k in cuts},
               "AVOID": {k: [tuple(b) for b in v] for k, v in (pr.get("AVOID") or {}).items() if k in cuts},
               "NO_WM": [k for k in pr.get("NO_WM", []) if k in cuts]}
    meta = dict(J.get("meta") or {})
    meta["h1Formulas"] = {int(p["n"]): p.get("formula", "") for p in J.get("pages", [])}
    rej = [tuple(r) + ("",) * (8 - len(r)) for r in (J.get("rejected") or []) if isinstance(r, list)]
    src = ("# 자동 생성(detail_py) — Claude 판단 JSON 에서 옮김\n"
           f"CUTS = {cuts!r}\nINFO = {info!r}\nREJECTED = {rej!r}\nPROTECT = {PROTECT!r}\nMETA = {meta!r}\n")
    (work / "cuts_def.py").write_text(src, encoding="utf-8")
    return errs, cuts


def run_tool(work, name, *args, timeout=600):
    r = subprocess.run([APY, name, *args], cwd=work, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


OVERLAY = re.compile(r"[\u4e00-\u9fff\uac00-\ud7a3]")   # 사진 위 덧붙인 중국어·한글(제품 인쇄 영문·숫자는 둔다)


def trim_cut_text(J, orig, log=log):
    """컷마다 맥 글자인식으로 중국어·한글을 찾는다(2026-11-19, 첫 판 자르기 정확도).
    가장자리(위·아래·좌·우 35% 안)에 있으면 그 글자 밖으로 bbox 를 줄이고(면적 55% 이상 남을 때만),
    가운데라 못 자르면 문제 목록으로 돌려 Claude 에게 다른 컷·bbox 를 받는다. 눈 검수 전에 공짜로 거른다."""
    try:
        from opt_py import read_text
    except Exception as e:
        log(f"  [글자 검사 생략] {e}"); return []
    probs, tmp = [], orig.parent / "_cutchk.png"
    used = set()
    for p in J.get("pages") or []:
        used |= {p.get("cut")} | {c.get("cut") for c in p.get("cells", [])} | {r.get("cut") for r in p.get("rows", []) if isinstance(r, dict)} | \
                {x for pr in p.get("pairs", []) for x in (pr.get("common"), pr.get("this"))}
    for k, c in (J.get("cuts") or {}).items():
        if k not in used or c.get("_chk") == c.get("bbox"):   # 같은 bbox 는 한 번만(다시 그릴 때마다 깎이지 않게)
            continue
        try:
            im = Image.open(orig / c["src"]).convert("RGB")
            x0, y0, x1, y1 = [int(v) for v in c["bbox"]]
            area0 = (x1 - x0) * (y1 - y0)
            for _ in range(4):
                im.crop((x0, y0, x1, y1)).save(tmp)
                hits = [(t, b) for t, _, b in read_text(tmp) if OVERLAY.search(t)]
                if not hits:
                    break
                w, h = x1 - x0, y1 - y0
                t, (bx0, by0, bx1, by1) = hits[0]
                pad = 8
                if by1 <= 0.35:   y0 = y0 + int(by1 * h) + pad
                elif by0 >= 0.65: y1 = y0 + int(by0 * h) - pad
                elif bx1 <= 0.35: x0 = x0 + int(bx1 * w) + pad
                elif bx0 >= 0.65: x1 = x0 + int(bx0 * w) - pad
                else:
                    probs.append(f"컷 {k}: 사진 가운데에 덧붙인 글자 「{t[:15]}」 — bbox 를 다시 잡거나 다른 컷으로"); break
                if (x1 - x0) * (y1 - y0) < 0.55 * area0 or x1 - x0 < 120 or y1 - y0 < 120:
                    probs.append(f"컷 {k}: 글자 「{t[:15]}」를 자르면 너무 작아짐 — 다른 컷으로"); break
            else:
                probs.append(f"컷 {k}: 글자가 계속 남음 — 다른 컷으로")
            x0, y0, x1, y1 = trim_color_edges(im, x0, y0, x1, y1)
            if [x0, y0, x1, y1] != [int(v) for v in c["bbox"]]:
                log(f"  [글자 자동 자르기] {k} {c['bbox']} → {[x0, y0, x1, y1]}")
                c["bbox"] = [x0, y0, x1, y1]
            c["_chk"] = list(c["bbox"])
        except Exception as e:
            log(f"  [글자 검사 실패] {k} {e}")
    tmp.unlink(missing_ok=True)
    return probs


def trim_color_edges(im, x0, y0, x1, y1, band=0.12, max_cut=0.15):
    """가장자리 띠(12%) 안의 진한 빨강·파랑 조각(글자 조각·치수선·표시선)을 찾아 그 너머로 경계를 민다.
    글자인식이 못 읽는 조각용(2026-11-19 바이트 세트: 눈 검수 수정 대부분이 이것). 한 변에 최대 15%만 깎는다."""
    a = np.asarray(im.crop((x0, y0, x1, y1))).astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    hot = ((r > 170) & (g < 100) & (b < 100)) | ((b > 150) & (r < 90) & (g < 140))
    H, W_ = hot.shape
    bh, bw = max(4, int(H * band)), max(4, int(W_ * band))
    def push(rows):   # rows: 가장자리에서 안쪽으로 가는 줄 순서의 불리언 배열들 → 마지막으로 hot 이 있는 깊이
        depth = 0
        for i, line in enumerate(rows):
            if line.sum() >= 3:
                depth = i + 1
        return depth
    top = push([hot[i] for i in range(bh)]); bot = push([hot[H - 1 - i] for i in range(bh)])
    lef = push([hot[:, i] for i in range(bw)]); rig = push([hot[:, W_ - 1 - i] for i in range(bw)])
    lim_h, lim_w = int(H * max_cut), int(W_ * max_cut)
    pad = 6
    if 0 < top <= lim_h: y0 += top + pad
    if 0 < bot <= lim_h: y1 -= bot + pad
    if 0 < lef <= lim_w: x0 += lef + pad
    if 0 < rig <= lim_w: x1 -= rig + pad
    return x0, y0, x1, y1


def render(work, J, orig):
    """cuts_def + spec → tpl.py. 문제 목록(빈 리스트면 성공)."""
    tprobs = trim_cut_text(J, orig)
    if tprobs and J.get("_tchk", 0) < 1:      # 가운데 글자는 한 번만 되묻는다 — 그래도 남으면 눈 검수에 맡긴다
        J["_tchk"] = J.get("_tchk", 0) + 1
    else:
        tprobs = []
    errs, cuts = write_cuts_def(work, J, orig)
    errs = tprobs + errs
    pages = J.get("pages") or []
    for p in pages:  # 없는 컷 참조
        refs = [p.get("cut")] + [c.get("cut") for c in p.get("cells", [])] + [r.get("cut") for r in p.get("rows", []) if isinstance(r, dict)] + \
               [x for pr in p.get("pairs", []) for x in (pr.get("common"), pr.get("this"))]
        for r in refs:
            if r and r not in cuts:
                errs.append(f"{p['n']}장: 없는 컷 {r}")
    if errs:
        return errs
    for f in list((work.parent / "clean").glob("[0-9][0-9].png")) + list(work.parent.glob("[0-9][0-9].png")):
        f.unlink()   # 장 수가 줄면 옛 장이 남아 반영 zip 에 섞인다
    (work / "spec.json").write_text(json.dumps({"warn_page": J.get("warn_page"), "pages": pages}, ensure_ascii=False, indent=1), encoding="utf-8")
    rc, out = run_tool(work, "tpl.py")
    if rc != 0:
        try:
            res = json.loads(out.strip().splitlines()[-1])
            return [f"{e['page']}장 {e['error']}: {e['detail']}" for e in res["errors"]]
        except Exception:
            return ["그리기 실패: " + out[-600:]]
    rc, out = run_tool(work, "qa.py")
    probs = [l for l in out.splitlines() if l.startswith("(")]
    return [f"배치 검사: {l[:200]}" for l in probs]


def cuts_sheet(work, w=260, cols=6):
    """잘라 놓은 컷 모음(키 표기) — 눈 검수 때 자르기 확인용."""
    ns = {}
    exec((work / "cuts_def.py").read_text(encoding="utf-8"), ns)
    orig = work.parent.parent / "originals"; F = ImageFont.truetype(FONT, 16); ths = []
    for k, (f, b) in ns["CUTS"].items():
        im = Image.open(orig / f).convert("RGB").crop(b); h = min(int(im.height * w / im.width), w * 2)
        ths.append((k, im.resize((w, int(im.height * w / im.width))).crop((0, 0, w, h))))
    rows = [ths[i:i + cols] for i in range(0, len(ths), cols)]
    S = Image.new("RGB", (cols * (w + 6), sum(max(t.height for _, t in r) + 22 for r in rows)), (60, 60, 60)); d = ImageDraw.Draw(S); y = 0
    for r in rows:
        for c, (k, t) in enumerate(r):
            S.paste(t, (c * (w + 6), y + 20)); d.text((c * (w + 6) + 2, y + 1), k, font=F, fill=(255, 255, 255))
        y += max(t.height for _, t in r) + 22
    return S


def pages_preview(root, n, s=0.5, per=4):
    ims = [Image.open(root / f"{i:02d}.png").convert("RGB") for i in range(1, n + 1)]
    out = []
    for i in range(0, n, per):
        grp = ims[i:i + per]; W_ = int(860 * s); H_ = max(int(im.height * s) for im in grp)
        S = Image.new("RGB", (len(grp) * (W_ + 8), H_ + 26), (60, 60, 60)); d = ImageDraw.Draw(S)
        F = ImageFont.truetype(FONT, 18)
        for k, im in enumerate(grp):
            S.paste(im.resize((W_, int(im.height * s)), Image.LANCZOS), (k * (W_ + 8), 26))
            d.text((k * (W_ + 8) + 4, 3), f"{i + k + 1}장", font=F, fill=(255, 255, 255))
        out.append(S)
    return out


def merge_pages(J, fix):
    if fix.get("pages"):
        byn = {p["n"]: p for p in fix["pages"]}
        J["pages"] = [byn.get(p["n"], p) for p in J["pages"]]
    for k in ("cuts", "protect", "warn_page"):
        if fix.get(k):
            if isinstance(J.get(k), dict) and isinstance(fix[k], dict):
                J[k].update(fix[k])
            else:
                J[k] = fix[k]
    if fix.get("report"):
        J.setdefault("report", {}).update(fix["report"])
    return J


def write_docs(outdir, t, J, chat, minutes):
    rep = J.get("report") or {}; meta = J.get("meta") or {}
    pages = J.get("pages") or []
    plan = [f"# plan — {t['market']} / {t['productId']} ({t['name']})", "",
            f"- 타깃 1명: {J.get('persona', '')}. 장면: {J.get('scene', '')}",
            f"- 비교 장: {'있음' if any(p['layout'] == 'compare' for p in pages) else '없음'}",
            f"- 스타일 C, 860px {len(pages)}장, 보호 표시 넣음. 제작: detail_py(파이썬 대장, Claude {chat.calls}회 호출)", "",
            "| 장 | H1 | 공식 | 레이아웃 | 컷 |", "|---|---|---|---|---|"]
    for p in pages:
        cuts = [p.get("cut")] + [c.get("cut") for c in p.get("cells", [])] + [r.get("cut") for r in p.get("rows", []) if isinstance(r, dict)]
        plan.append(f"| {p['n']:02d} | {' / '.join(p.get('h1') or p.get('quote') or [])} | {p.get('formula', '')} | {p['layout']} | {', '.join(c for c in cuts if c)} |")
    plan += ["", "## 안 쓴 컷", *[f"- {r[0]} ({r[1]}): {r[7] if len(r) > 7 else ''}" for r in J.get("rejected") or []]]
    (outdir / "plan.md").write_text("\n".join(plan) + "\n", encoding="utf-8")
    v = json.loads((outdir / "verification.json").read_text(encoding="utf-8"))
    cu = v.get("cutUsage", {})
    r = [f"# report — {t['market']} {t['name']}", "", "## 요약",
         f"- 판매자상품코드 {t['code']} / 불사자 내부 ID {t['productId']} / 마켓 {t['market']}",
         f"- 상품검수: {J['inspect']['verdict']} / {J['inspect']['reason']} — {J['inspect'].get('note', '')}",
         f"- 스타일 C {len(pages)}장(860px PNG), 보호 표시 3종 적용",
         f"- 제작 방식: detail_py(파이썬 대장) · 모델 {MODEL} · Claude 호출 {chat.calls}회 · 비용 ${chat.cost:.2f}",
         f"- 대표 썸네일 마켓명 워터마크: {'있음' if meta.get('thumbnailWatermark') else '없음'}(썸네일은 고치지 않음)", "",
         "## 컷 활용률", f"- usable {cu.get('usable')} / 사용 {cu.get('used')} ({round((cu.get('rate') or 0) * 100)}%), 중복 {cu.get('duplicates') or '없음'}", "",
         "## 장별 한 줄", *[f"{i + 1}. {s}" for i, s in enumerate(rep.get("lines") or [])], "",
         "## 원본에서 확인 못 해서 뺀 정보", *[f"- {s}" for s in meta.get("droppedFacts") or []], "",
         "## 아쉬운 점", *[f"{i + 1}. {s}" for i, s in enumerate(rep.get("regrets") or [])], "",
         "## 걸린 시간", f"- {minutes:.1f}분", ""]
    if rep.get("hold"):
        r += ["## 반영 보류 사유", f"- {rep['hold']}", ""]
    r += ["## 실제 상품 반영", "- 불사자 저장·교체·업로드 안 함(반영은 Claude Code 배치가 한다)"]
    (outdir / "report.md").write_text("\n".join(r) + "\n", encoding="utf-8")


# ---------------- 본 흐름 ----------------
def make(t, outdir, brief, log=log, inspect=True):
    """report.md 를 쓰면 'ok'. 비용은 결과 dict 에."""
    t0 = time.time()
    outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    if not prep.run(t, outdir, brief, "claude-code/" + MODEL, log=log):
        return {"result": "prep_fail"}
    work = outdir / "work"; orig = outdir.parent / "originals"
    tmp = outdir / "tmp"; tmp.mkdir(exist_ok=True)
    tiles, dups = grid_tiles(orig)
    sheets = pack(tiles, tmp)
    facts = (orig / "_facts.md").read_text(encoding="utf-8")
    sys_prompt = RULES + ("\n\n# 상품검수 기준표\n" + common.INSPECT_PROMPT.read_text(encoding="utf-8") if inspect else "")
    chat = Chat(sys_prompt)
    try:
        intro = (f"상품: 판매자상품코드 {t['code']} · 마켓 {t['market']} · 상품명 {t['name']}\n"
                 f"판매 옵션: {', '.join(t.get('sellOptions') or []) or '_facts 참고'}\n"
                 f"판매 제외 옵션(상세에 넣지 않는다): {', '.join(t.get('excludedOptions') or []) or '없음'}\n"
                 + ("상품검수를 한다(stage 2 기준: 실제로 팔 타오바오 상품 — 사진·옵션·타오바오 제목으로 판정, 애매하면 drop).\n" if inspect else "상품검수는 하지 않는다(효자상품 시트).\n")
                 + f"같은 사진 파일(중복): {json.dumps(dups, ensure_ascii=False)}\n\n# _facts\n{facts}\n"
                 f"아래 {len(sheets)}장은 원본 좌표 눈금 모음이다. 마지막 장은 대표 썸네일(upload-thumb-01, 워터마크 유무 확인용)이다.")
        content = [{"type": "text", "text": intro}] + [img_block(p) for p in sheets]
        ut = sorted(orig.glob("upload-thumb-01.*"))
        if ut:
            content.append(img_block(Image.open(ut[0]).convert("RGB").resize((500, 500))))
        content.append({"type": "text", "text": "규칙대로 JSON 하나로 답해."})
        J = parse_json(chat.ask(content))
        if not inspect:   # 효자상품 시트 — 검수 생략 지시(2026-11-04). 모델이 판정해도 따르지 않는다
            J["inspect"] = {"verdict": "pass", "reason": "OK", "note": "검수 생략: 효자상품 시트"}
        log(f"  [판단1] {J['inspect']['verdict']} · 컷 {len(J.get('cuts') or {})} · 장 {len(J.get('pages') or [])} · ${chat.cost:.2f}")
        (work / "claude_plan.json").write_text(json.dumps(J, ensure_ascii=False, indent=1), encoding="utf-8")
        (outdir / "inspect.json").write_text(json.dumps(J["inspect"], ensure_ascii=False), encoding="utf-8")
        if J["inspect"]["verdict"] != "pass":
            (outdir / "report.md").write_text(
                f"# report — {t['market']} {t['name']}\n\n## 검수 탈락\n- {J['inspect']['reason']}: {J['inspect'].get('note', '')}\n"
                f"- 근거: {(J.get('meta') or {}).get('inspectionNote', '')}\n- 제작 방식 detail_py · 비용 ${chat.cost:.2f}\n", encoding="utf-8")
            return {"result": "ok", "cost": chat.cost, "calls": chat.calls, "minutes": (time.time() - t0) / 60, "verdict": "drop"}
        # 그리기 — 글자 넘침·컷 오류는 돌려보내 고친 장만 받기(최대 2회)
        for attempt in range(3):
            probs = render(work, J, orig)
            if not probs:
                break
            log(f"  [그리기 문제 {len(probs)}] {probs[:3]}")
            if attempt == 2:
                return {"result": "render_fail", "cost": chat.cost, "calls": chat.calls, "problems": probs}
            fix = parse_json(chat.ask([{"type": "text", "text": "그리기에서 문제가 났다. 해당 장(필요하면 cuts)만 고쳐서 같은 형식 JSON 으로 답해: "
                                                       '{"pages":[고친 장 전체], "cuts":{고친 컷}}\n' + "\n".join(probs)}]))
            J = merge_pages(J, fix)
        rc, out = run_tool(work, "protect.py")
        if rc != 0:
            return {"result": "protect_fail", "detail": out[-400:], "cost": chat.cost}
        # 눈 검수 — 고칠 게 있으면 전체 장 목록을 다시 받아 통째로 바꾸고, 고친 결과를 한 번 더 본다(최대 2회)
        whys = []
        review = {"ok": True}
        for rnd in range(2):
            n = len(J["pages"])
            prev = pages_preview(outdir, n)
            review = parse_json(chat.ask([{"type": "text", "text":
                ("고친 결과다. 다시 본다. " if rnd else "") +
                "첫 이미지는 잘라 놓은 컷 모음(키 표기), 나머지는 완성본(워터마크 포함) 축소 모음이다. 장별 검수 12항목(판매 문구·혜택 줄·H1 공식, 금지어, 중국어, 장식, 글자 겹침·잘림, 끝 여백, 가짜 리뷰, 디자인 값, 앞 장과 레이아웃, 톤, 워터마크가 로고·설명을 가리는지)으로 본다. "
                "컷에 옆 칸·경계선·표시선·라벨·치수선·중국어가 남았거나 제품이 잘렸거나 한 칸에 제품이 둘 이상이면 cuts 의 bbox 를 고친다(못 고치면 그 컷을 빼고 다른 컷으로). "
                "같은 내용 장이 두 번 나오거나 사진이 너무 작아 휑한 장, 카피가 사진과 안 맞는 장도 고친다. 문제가 없으면 {\"ok\":true}, 있으면 "
                '{"ok":false, "why":["무엇이 문제"], "pages":[**전체 장 목록**(장을 빼거나 합치면 n 을 1부터 다시)], "cuts":{고친 컷만}, "protect":{…}, "warn_page":N, "report":{"lines":[장별 한 줄]}} 로만 답해.'}]
                + [img_block(cuts_sheet(work))] + [img_block(im) for im in prev]))
            if review.get("ok"):
                break
            whys += review.get("why") or []
            log(f"  [눈 검수 {rnd + 1}차 수정] {review.get('why')}")
            pages_all = review.pop("pages", None)
            if pages_all:
                J["pages"] = sorted(pages_all, key=lambda p: p["n"])
            J = merge_pages(J, review)
            probs = render(work, J, orig)
            if probs:
                fix = parse_json(chat.ask([{"type": "text", "text": "그리기 문제다. 해당 장만 고쳐 {\"pages\":[고친 장], \"cuts\":{…}} 로 답해:\n" + "\n".join(probs)}]))
                J = merge_pages(J, fix)
                probs = render(work, J, orig)
                if probs:
                    return {"result": "render_fail", "cost": chat.cost, "calls": chat.calls, "problems": probs}
            rc, out = run_tool(work, "protect.py")
        n = len(J["pages"])
        (work / "claude_plan.json").write_text(json.dumps(J, ensure_ascii=False, indent=1), encoding="utf-8")
        # 옵션이미지 기록이 없으면 빈 목록(옵션이미지는 opt_py 가 따로 맡는다)
        oi = outdir / "option-images"; oi.mkdir(exist_ok=True)
        rc, out = run_tool(work, "finalize.py")
        if rc != 0:
            return {"result": "finalize_fail", "detail": out[-600:], "cost": chat.cost}
        minutes = (time.time() - t0) / 60
        write_docs(outdir, t, J, chat, minutes)
        return {"result": "ok", "cost": round(chat.cost, 3), "calls": chat.calls, "minutes": round(minutes, 1), "pages": n,
                "review": whys or "ok", "final_ok": bool(review.get("ok"))}
    finally:
        chat.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", required=True)
    ap.add_argument("--batch", required=True, help="targets.json 이 있는 배치 폴더 이름")
    ap.add_argument("--suffix", default="_opus-py")
    a = ap.parse_args()
    B = common.BATCH_ROOT / a.batch
    t = [x for x in json.loads((B / "targets.json").read_text(encoding="utf-8"))["targets"] if x["code"] == a.code][0]
    outdir = common.PAGES / t["market"] / t["productId"] / f"{date.today().isoformat()}{a.suffix}"
    if outdir.exists():
        shutil.rmtree(outdir)
    import batch
    brief = common.BRIEF_DIR / f"작업지시서-{t['code']}-{date.today().isoformat()}{a.suffix}.md"
    keep = common.BRIEF_DIR / f"작업지시서-{t['code']}-{date.today().isoformat()}.md"
    bak = keep.read_bytes() if keep.exists() else None
    tmpb = batch.write_brief(t, outdir); tmpb.replace(brief)
    if bak is not None: keep.write_bytes(bak)
    res = make(t, outdir, brief, inspect=not t.get("noInspect"))
    res.update(code=t["code"], outdir=str(outdir))
    print(json.dumps(res, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
