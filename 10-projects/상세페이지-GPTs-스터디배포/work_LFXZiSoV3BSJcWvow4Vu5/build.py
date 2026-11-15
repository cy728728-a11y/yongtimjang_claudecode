# -*- coding: utf-8 -*-
# 절삭유 이중 미스트 분무기 상세페이지 (C 세일즈형, 860px 낱장 PNG)
import os, zipfile
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

BASE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.dirname(BASE)
OUT = os.path.join(BASE, "out")
os.makedirs(OUT, exist_ok=True)

try:
    def F(size, bold=False):
        return ImageFont.truetype(os.path.join(FONT_DIR, "Pretendard-Bold.otf" if bold else "Pretendard-Regular.otf"), size)
    F(30); F(30, True)
except Exception as e:
    raise SystemExit("Pretendard 폰트 로드 실패: %s" % e)

W = 860
IVORY = (248, 246, 242); BEIGE = (237, 232, 224); BROWN = (81, 71, 51)
PILL = (138, 127, 112); BODY = (79, 72, 56); SUB = (138, 131, 120); WHITE = (255, 255, 255)
LM = 48

def src(p):
    return Image.open(os.path.join(BASE, p)).convert("RGB")

def cut(p, box, masks=(), fill=None):
    """원본에서 자르기 + 배경 위 글자 영역만 배경색으로 덮기"""
    im = src(p)
    d = ImageDraw.Draw(im)
    for m in masks:
        c = fill or im.getpixel((m[0] + 2, m[1] + 2))
        d.rectangle(m, fill=c)
    return im.crop(box)

def fit(im, w=None, h=None):
    if w and h:
        r = min(w / im.width, h / im.height)
    elif w:
        r = w / im.width
    else:
        r = h / im.height
    return im.resize((max(1, round(im.width * r)), max(1, round(im.height * r))), Image.LANCZOS)

def circle(im, size, bg):
    im = fit(im, size, size)
    sq = Image.new("RGB", (size, size), bg)
    sq.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    out = Image.new("RGB", (size, size), bg)
    out.paste(sq, (0, 0), mask)
    return out, mask

class Page:
    def __init__(self, h, bg=IVORY):
        self.im = Image.new("RGB", (W, h), bg)
        self.d = ImageDraw.Draw(self.im)
        self.bg = bg

    def rich(self, y, parts, size, color, center=True, x=LM):
        """parts: [(텍스트, 굵게여부)] 한 줄. 같은 줄 안에서 굵기로만 강조"""
        widths = [self.d.textlength(t, font=F(size, b)) for t, b in parts]
        tw = sum(widths)
        cx = (W - tw) / 2 if center else x
        for (t, b), w in zip(parts, widths):
            self.d.text((cx, y), t, font=F(size, b), fill=color)
            cx += w
        return y + int(size * 1.6)

    def text(self, y, s, size, color, bold=False, center=True, x=LM):
        return self.rich(y, [(s, bold)], size, color, center, x)

    def pill(self, x, y, s, size=22, center=False):
        f = F(size, True)
        tw = self.d.textlength(s, font=f)
        pw, ph = tw + 36, size + 20
        if center:
            x = (W - pw) / 2
        self.d.rounded_rectangle([x, y, x + pw, y + ph], radius=ph // 2, fill=PILL)
        self.d.text((x + 18, y + 8), s, font=f, fill=WHITE)
        return y + ph

    def band(self, y, h, lines, size=30):
        self.d.rectangle([0, y, W, y + h], fill=BROWN)
        ty = y + (h - len(lines) * int(size * 1.6)) // 2 + 4
        for s in lines:
            ty = self.text(ty, s, size, WHITE, bold=True)
        return y + h

    def photo(self, im, x, y, panel=None):
        if panel:
            self.d.rectangle(panel, fill=WHITE)
        self.im.paste(im, (int(x), int(y)))

    def save(self, n, end=None):
        if end:
            self.im = self.im.crop((0, 0, W, end + 60))
        self.im.save(os.path.join(OUT, "%02d.png" % n))

# ───────── 사진 준비 (원본 픽셀 그대로, 자르기·글자영역 덮기·리사이즈만) ─────────
P_HERO = cut("thumbs/t6.png", (110, 60, 790, 700))
P_TIP = cut("opts/o03_plain400.png", (170, 150, 640, 425))
P_MAIN = cut("thumbs/t3.png", (30, 222, 690, 572), masks=[(20, 215, 430, 312), (280, 468, 800, 600)], fill=WHITE)
P_ADJ = cut("thumbs/t3.png", (518, 652, 628, 768))
P_IN = cut("thumbs/t3.png", (518, 476, 628, 594))
P_NOZ = cut("thumbs/t3.png", (52, 652, 162, 768))
P_DIR = cut("thumbs/t3.png", (293, 652, 403, 768))
P_Y = cut("thumbs/t4.png", (22, 18, 700, 158), masks=[(278, 12, 512, 70), (668, 118, 800, 160)], fill=WHITE)
P_CU = cut("thumbs/t4.png", (28, 400, 768, 512), masks=[(252, 392, 530, 438)], fill=WHITE)
P_OY = cut("opts/o19_Y300.jpg", (150, 50, 670, 690), masks=[(0, 596, 196, 699)])
P_OM = cut("opts/o07_metal300.png", (50, 105, 625, 635))
P_OC = cut("opts/o13_cu300.png", (150, 100, 580, 690), masks=[(0, 590, 192, 699)], fill=WHITE)
P_TANK = cut("opts/o26_tank1.png", (115, 125, 605, 585))
P_HOT = cut("opts/o49_cuhot.png", (196, 446, 560, 655))
P_ACID = cut("opts/o50_cuacid.png", (206, 482, 600, 660))
P_MAG = cut("opts/o02_plain300mag.png", (680, 588, 796, 690))

# ───────── 01 대표: 결과 중심 제목 + 대표 사진 + 요약 띠 ─────────
p = Page(1320)
y = 60
y = p.pill(0, y, "공작기계 절삭 냉각용", center=True) + 32
y = p.rich(y, [("분무기 ", False), ("하나로", True)], 58, BROWN)
y = p.rich(y, [("두 곳을 ", True), ("동시에 식힌다", False)], 58, BROWN)
y += 4
y = p.text(y, "이중 미스트 노즐 · 절삭유 안개 분무기", 30, SUB) + 32
img = fit(P_HERO, w=W - 2 * LM)
p.photo(img, LM, y, panel=[LM, y, W - LM, y + img.height])
y += img.height + 60
p.band(y, 1320 - y, ["노즐 두 개가 각자 방향을 잡고,", "공기와 액체를 섞어 안개로 뿜어냅니다"], 30)
p.save(1)

# ───────── 02 후킹: 큰 따옴표 문장 + 보조 1줄 ─────────
p = Page(1400, BEIGE)
y = 110
y = p.text(y, "“", 96, BROWN, bold=True) - 50
y = p.rich(y, [("한쪽은 ", False), ("공구 끝", True), (",", False)], 54, BROWN)
y = p.rich(y, [("한쪽은 ", False), ("가공물 위", True), ("로", False)], 54, BROWN)
y = p.rich(y, [("노즐 둘이 ", False), ("따로 겨눕니다", True)], 54, BROWN)
y += 24
y = p.text(y, "분무기 한 대, 분사 지점은 두 곳", 30, SUB) + 60
img = fit(P_TIP, w=W - 2 * LM)
p.photo(img, LM, y, panel=[LM, y, W - LM, y + img.height])
p.save(2, y + img.height)

# ───────── 03 핵심 장점: 사진 꽉 채움 + 아래 글 ─────────
p = Page(1600)
img = fit(P_MAIN, w=W)
p.d.rectangle([0, 0, W, img.height + 120], fill=WHITE)
p.photo(img, 0, 60)
y = img.height + 120 + 60
y = p.pill(0, y, "핵심 장점", center=True) + 28
y = p.rich(y, [("물 펌프 없이 ", True), ("공기압만으로", False)], 56, BROWN) + 20
y = p.text(y, "압축공기를 연결하면 액체를 스스로 빨아올려", 32, BODY)
y = p.text(y, "물과 공기를 섞은 안개로 뿜어냅니다.", 32, BODY)
y = p.text(y, "공기 입구 하나, 액체 입구 하나로 연결도 간단합니다.", 32, BODY)
p.save(3, y - 10)

# ───────── 04 구조·조작부: 사진 2×2 그리드 ─────────
p = Page(1400)
y = 60
y = p.rich(y, [("필요한 만큼만, ", False), ("원하는 방향으로", True)], 56, BROWN) + 4
y = p.text(y, "블록 위 나사 두 개로 공기량과 액체량을 따로 맞춥니다", 28, SUB) + 40
items = [
    (P_ADJ, "정밀 조절", ["공기량·오일량 조절 나사가", "따로 있어 분사 세기를 맞춥니다"]),
    (P_IN, "입구 두 개", ["공기 한 줄, 액체 한 줄로", "들어가는 구조입니다"]),
    (P_NOZ, "구리 노즐", ["분사구 끝은 전체가", "구리로 된 노즐입니다"]),
    (P_DIR, "각자 방향", ["두 관이 따로 휘어져", "각도를 더 넓게 잡습니다"]),
]
cs = 220; colw = (W - 2 * LM) // 2
for i, (im, lab, lines) in enumerate(items):
    cx = LM + (i % 2) * colw + (colw - cs) // 2
    cy = y + (i // 2) * 420
    c, m = circle(im, cs, WHITE)
    p.im.paste(c, (cx, cy), m)
    ty = cy + cs + 32
    tw = p.d.textlength(lab, font=F(22, True)) + 36
    p.pill(LM + (i % 2) * colw + (colw - tw) / 2, ty, lab)
    ty += 62
    for s in lines:
        tcx = LM + (i % 2) * colw + (colw - p.d.textlength(s, font=F(30))) / 2
        p.d.text((tcx, ty), s, font=F(30), fill=BODY); ty += 48
p.save(4, ty - 10)

# ───────── 05 관 두 종류: 와이드 사진 + 설명 번갈아 ─────────
p = Page(1300, BEIGE)
y = 60
y = p.rich(y, [("작업대에 맞춰 고르는 ", False), ("두 가지 관", True)], 56, BROWN) + 40
for im, lab, title, lines in [
    (P_Y, "Y형 관", "가까운 두 지점에 딱", ["밸브 몸체가 작아 자리를 덜 차지하고", "가까이 붙은 두 곳을 함께 겨눕니다"]),
    (P_CU, "구리관", "한 번 잡으면 그대로", ["열과 충격에 강한 구리관이라", "위치를 고정하면 방향이 틀어지지 않습니다"]),
]:
    img = fit(im, w=W - 2 * LM)
    p.photo(img, LM, y, panel=[LM, y - 24, W - LM, y + img.height + 24])
    y += img.height + 24 + 32
    p.pill(LM, y, lab)
    p.d.text((LM + p.d.textlength(lab, font=F(22, True)) + 56, y - 4), title, font=F(38, True), fill=BROWN)
    y += 66
    for s in lines:
        y = p.text(y, s, 30, BODY, center=False)
    y += 50
p.save(5, y - 60)

# ───────── 06 옵션 ①~④: 세로 목록 ─────────
def option_rows(p, y, rows, photo_right=False):
    ps = 250
    for num, im, name, lines in rows:
        img = fit(im, ps, ps)
        px = W - LM - ps if photo_right else LM
        tx = LM if photo_right else LM + ps + 36
        p.d.rectangle([px, y, px + ps, y + ps], fill=WHITE)
        p.photo(img, px + (ps - img.width) // 2, y + (ps - img.height) // 2)
        ty = y + 40
        p.d.rounded_rectangle([tx, ty, tx + 52, ty + 52], radius=10, fill=BROWN)
        p.d.text((tx + 26 - p.d.textlength(num, font=F(28, True)) / 2, ty + 9), num, font=F(28, True), fill=WHITE)
        p.d.text((tx + 70, ty + 4), name, font=F(34, True), fill=BROWN)
        ty += 82
        for s in lines:
            p.d.text((tx, ty), s, font=F(30), fill=BODY); ty += 48
        y += ps + 44
    return y

p = Page(1470)
y = 60
y = p.text(y, "옵션 구성", 56, BROWN, bold=True)
y = p.text(y, "관 종류를 고르고, 길이와 자석 받침 여부를 고릅니다", 28, SUB) + 36
y = option_rows(p, y, [
    ("1", P_HERO, "기본형 · 파란 관", ["300 · 400 · 500mm", "강자석 받침 추가 선택"]),
    ("2", P_OY, "Y형 · 검정 관", ["300 · 400 · 500mm", "강자석 받침 추가 선택"]),
    ("3", P_OM, "금속관", ["300 · 400 · 500mm", "흡입관·체크밸브·필터 헤드 포함"]),
    ("4", P_OC, "구리관", ["300 · 400 · 500mm", "강자석 받침 추가 선택"]),
])
p.save(6, y - 44)

# ───────── 07 3L 용기 세트: 사진↔글 2열 ─────────
p = Page(1500)
y = 60
y = p.pill(0, y, "옵션 8 · 세트 구성", center=True) + 28
y = p.rich(y, [("탱크까지 ", False), ("한 번에", True)], 58, BROWN)
y = p.text(y, "3L 용기 + 이중 분무기 1개", 30, SUB) + 40
img = fit(P_TANK, w=470)
p.photo(img, LM, y, panel=[LM, y, LM + img.width, y + img.height])
tx = LM + img.width + 36
ty = y + 10
for head, lines in [
    ("함께 드리는 것", ["3m 흡입관", "체크밸브", "필터 헤드", "강자석 받침"]),
    ("분사할 수 있는 액체", ["물 · 알코올 · 냉각액", "기계유 · 등유 · 식용유"]),
]:
    p.d.text((tx, ty), head, font=F(30, True), fill=BROWN); ty += 54
    for s in lines:
        p.d.text((tx, ty), s, font=F(28), fill=BODY); ty += 44
    ty += 30
y = max(y + img.height, ty) + 60
p.band(y, 170, ["용기에 액체를 채우고 공기만 연결하면", "따로 펌프를 달 필요가 없습니다"], 30)
p.save(7, y + 170)

# ───────── 08 옵션 ⑤~⑦: 사진 오른쪽 목록 ─────────
p = Page(1220, BEIGE)
y = 60
y = p.rich(y, [("작업 환경이 ", False), ("까다롭다면", True)], 56, BROWN)
y = p.text(y, "특수 구리관과 강자석 받침", 28, SUB) + 36
y = option_rows(p, y, [
    ("5", P_HOT, "구리관 · 고온용", ["열이 많은 작업 자리에", "쓰는 구리관 300mm"]),
    ("6", P_ACID, "구리관 · 내산알칼리", ["저농도 산·알칼리,", "유기 용제 분사용 300mm"]),
    ("7", P_MAG, "강자석 받침", ["옵션명에 '자석'이 붙은", "구성에 함께 들어갑니다"]),
], photo_right=True)
p.save(8, y - 44)

# ───────── 09 스펙 + 구매 전 확인 ─────────
p = Page(1420)
y = 60
y = p.text(y, "한눈에 보는 구성", 56, BROWN, bold=True) + 30
specs = [("300 / 400 / 500", "mm", "관 길이"), ("2", "곳", "동시 분사 지점"), ("3", "L", "세트 용기 용량"), ("3", "m", "세트 흡입관 길이")]
for big, unit, lab in specs:
    p.d.rectangle([0, y, W, y + 128], fill=BROWN)
    bw = p.d.textlength(big, font=F(64, True)); uw = p.d.textlength(unit, font=F(30, True))
    p.d.text((LM + 10, y + 26), big, font=F(64, True), fill=WHITE)
    p.d.text((LM + 22 + bw, y + 56), unit, font=F(30, True), fill=WHITE)
    lw = p.d.textlength(lab, font=F(30))
    p.d.text((W - LM - 10 - lw, y + 46), lab, font=F(30), fill=(237, 232, 224))
    y += 140
y += 40
y = p.pill(LM, y, "구매 전 확인") + 30
for a, b in [
    ("작동하려면 압축공기 연결이 필요합니다.", ""),
    ("구리관은 손으로 살짝 구부려 각도를 잡으세요.", "세게 꺾으면 관이 눌려 분사가 약해집니다."),
    ("내산알칼리 구리관은 저농도 용액용이며,", "강자석 받침은 '자석' 옵션에만 들어 있습니다."),
]:
    p.d.text((LM, y), "·", font=F(32, True), fill=BROWN)
    p.d.text((LM + 26, y), a, font=F(30), fill=BODY); y += 48
    if b:
        p.d.text((LM + 26, y), b, font=F(30), fill=BODY); y += 48
    y += 18
p.im = p.im.crop((0, 0, W, y + 60 - 18))
p.save(9)

# ───────── ZIP + 미리보기 ─────────
files = sorted(f for f in os.listdir(OUT) if f[:2].isdigit() and f.endswith(".png"))
with zipfile.ZipFile(os.path.join(OUT, "detail.zip"), "w") as z:
    for f in files:
        z.write(os.path.join(OUT, f), f)
ims = [Image.open(os.path.join(OUT, f)) for f in files]
sc = 0.3
tw = int(W * sc)
th = max(int(i.height * sc) for i in ims)
pv = Image.new("RGB", (tw * len(ims) + 10 * (len(ims) - 1), th), (200, 200, 200))
for k, i in enumerate(ims):
    pv.paste(i.resize((tw, int(i.height * sc))), (k * (tw + 10), 0))
pv.save(os.path.join(OUT, "preview.jpg"), quality=88)
for f, i in zip(files, ims):
    print(f, i.size)
