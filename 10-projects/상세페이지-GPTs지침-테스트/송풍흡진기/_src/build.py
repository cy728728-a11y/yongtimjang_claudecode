# -*- coding: utf-8 -*-
# 송풍·흡진 겸용 집진기 상세페이지 빌드 (스타일 C)
import os, sys, zipfile
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, 'images')
OUT = sys.argv[1]
FONTDIR = r'C:/Users/workspace/10-projects/상세페이지-GPTs-스터디배포'
os.makedirs(OUT, exist_ok=True)

# ── 폰트 로드 확인 ──
try:
    def F(size, bold=False):
        return ImageFont.truetype(os.path.join(FONTDIR, 'Pretendard-Bold.otf' if bold else 'Pretendard-Regular.otf'), size)
    F(30); F(30, True)
except Exception as e:
    print('Pretendard 폰트 파일을 첨부해 주세요', e); sys.exit(1)

W, M = 860, 48
IVORY, BEIGE, BROWN, PILL, BODY, SUB = '#F8F6F2', '#EDE8E0', '#514733', '#8A7F70', '#4F4838', '#8A8378'
TITLE = 58; BODYSZ = 31; LH = int(BODYSZ * 1.6)

def src(n): return Image.open(os.path.join(SRC, f'{n}.jpg')).convert('RGB')

def fit(img, w):
    """가로 w로 리사이즈. 확대일 때만 가벼운 보정 1회."""
    h = round(img.height * w / img.width)
    out = img.resize((w, h), Image.LANCZOS)
    if w > img.width:
        out = ImageEnhance.Contrast(out).enhance(1.03)
        out = ImageEnhance.Sharpness(out).enhance(1.25)
    return out

def cover(img, w, h):
    """비율 맞춰 가운데 기준으로 자른 뒤 리사이즈"""
    r = w / h
    if img.width / img.height > r:
        nw = round(img.height * r); x = (img.width - nw) // 2
        img = img.crop((x, 0, x + nw, img.height))
    else:
        nh = round(img.width / r); y = (img.height - nh) // 2
        img = img.crop((0, y, img.width, y + nh))
    return fit(img, w).resize((w, h), Image.LANCZOS) if img.width < w else img.resize((w, h), Image.LANCZOS)

def seg_w(segs, size):
    return sum(F(size, b).getlength(t) for t, b in segs)

def rich(d, segs, y, size, color, align='center', x0=M):
    """같은 줄 안에서 굵기만 다르게"""
    total = seg_w(segs, size)
    x = (W - total) / 2 if align == 'center' else x0
    for t, b in segs:
        d.text((x, y), t, font=F(size, b), fill=color)
        x += F(size, b).getlength(t)
    return y + int(size * 1.25)

def title(d, lines, y, align='center'):
    for segs in lines:
        assert seg_w(segs, TITLE) <= W - 2 * M, segs
        y = rich(d, segs, y, TITLE, BROWN, align)
    return y

def para(d, lines, y, size=BODYSZ, color=BODY, align='center', x0=M, maxw=W - 2 * M, bold=False):
    for ln in lines:
        f = F(size, bold)
        assert f.getlength(ln) <= maxw, ln
        x = (W - f.getlength(ln)) / 2 if align == 'center' else x0
        d.text((x, y), ln, font=f, fill=color)
        y += int(size * 1.6)
    return y

def pill(d, text, y, x=None, size=22, fill=PILL):
    f = F(size, True); tw = f.getlength(text); pw = tw + 36; ph = size + 18
    x = (W - pw) / 2 if x is None else x
    d.rounded_rectangle([x, y, x + pw, y + ph], radius=ph // 2, fill=fill)
    d.text((x + 18, y + 8), text, font=f, fill='white')
    return y + ph

def canvas(h, bg=IVORY):
    im = Image.new('RGB', (W, h), bg); return im, ImageDraw.Draw(im)

def save(im, n):
    assert 1000 <= im.height <= 1500, (n, im.height)
    im.save(os.path.join(OUT, f'{n:02d}.png'))
    print(n, im.size)

# ── 원본 컷 ──
s5, s6 = src(5), src(6)
a = s5.crop((62, 790, 728, 1474)); b = s6.crop((62, 0, 728, 226))
E = Image.new('RGB', (666, a.height + b.height)); E.paste(a, (0, 0)); E.paste(b, (0, a.height))
F_ = s6.crop((64, 812, 726, 1474))
A = src(1).crop((0, 30, 790, 1130))
B = src(2).crop((34, 34, 756, 1036))
C = src(3).crop((0, 40, 790, 1000))
D = src(4).crop((0, 100, 790, 770))
H = src(11).crop((0, 520, 790, 1380))
s9 = src(9)
rows = [(0, 252), (344, 598), (694, 948), (1037, 1290)]
G = []
for (y1, y2) in rows:
    for (x1, x2) in [(27, 379), (403, 755)]:
        G.append(s9.crop((x1 + 6, y1 + (0 if y1 == 0 else 6), x2 - 6, y2)))
GCAP = ['목재 톱밥·나무 가루', '벽 홈파기 분진', '벽면 연마 분진', '타공 분진',
        '석고 분진', '알루미늄 절삭 가루', '타일 접착제 분진', '스티로폼·종이 가루']

# ── 01 첫 장: 사용 장면 ──
pw = W - 2 * M; ph = fit(E, pw)
im, d = canvas(60 + 40 + 28 + 2 * 72 + 20 + 50 + 32 + ph.height + 60)
y = pill(d, '흡입·송풍 겸용 집진기', 60) + 28
y = title(d, [[('홈 파는 동안', False)], [('분진은 ', False), ('그 자리에서 흡입', True)]], y) + 20
y = para(d, ['6단 조절 공업용 송풍·흡진기'], y, color=SUB) + 32 - 18
im.paste(ph, (M, y)); save(im, 1)

# ── 02 후킹 문장 ──
ph = fit(H, pw)
im, d = canvas(70 + 90 + 2 * 72 + 24 + 50 + 44 + ph.height + 60, BEIGE)
d.text((W / 2 - 30, 40), '“', font=F(150, True), fill=PILL)
y = 70 + 90
y = title(d, [[('홈 파고 나서 ', False), ('바닥 쓸 일', True)], [('확 줄었어요', True)]], y) + 24
y = para(d, ['작업하는 동안 분진을 바로 빨아들이니까요'], y, color=SUB) + 44 - 18
im.paste(ph, (M, y)); save(im, 2)

# ── 03 흡입·송풍 두 입구 ──
ph = fit(D, pw)
im, d = canvas(60 + 2 * 72 + 32 + ph.height + 32 + 44 + 16 + 2 * LH + 60)
y = title(d, [[('빨아들이고 ', False), ('불어내고', True)], [('한 대로 끝', True)]], 60, align='left') + 32
im.paste(ph, (M, y)); y += ph.height + 32
cw = (pw - 32) // 2
for i, (lab, lines) in enumerate([('01  흡입구', ['가운데 둥근 입구로', '분진을 빨아들여요']),
                                  ('02  송풍구', ['아래 옆쪽 입구로', '바람을 내보내요'])]):
    x = M + i * (cw + 32)
    yy = pill(d, lab, y, x=x, fill=BROWN) + 16
    para(d, lines, yy, align='left', x0=x, maxw=cw)
save(im, 3)

# ── 04 구리 모터: 사진 꽉 채움 ──
ph = fit(C, W)
im, d = canvas(60 + 2 * 72 + 24 + 2 * LH + 22 + ph.height + 60)
y = title(d, [[('오래 써도', False)], [('과열을 막는 ', False), ('구리 모터', True)]], 60) + 24
y = para(d, ['흡진하는 동안 계속 열을 식혀', '모터가 지나치게 뜨거워지지 않게 해요'], y) + 22
im.paste(ph, (0, y)); save(im, 4)

# ── 05 내구 구조: 2장 그리드 ──
cw = (pw - 16) // 2; chh = 560
im, d = canvas(60 + 2 * 72 + 36 + chh + 28 + 44 + 16 + 2 * LH + 60, BEIGE)
y = title(d, [[('딱딱한 조각에도', False)], [('쉽게 상하지 않게', True)]], 60) + 36
im.paste(cover(A, cw, chh), (M, y)); im.paste(cover(B, cw, chh), (M + cw + 16, y)); y += chh + 28
for i, (lab, lines) in enumerate([('알루미늄 바람통', ['열처리한 알루미늄이라', '부딪혀도 튼튼해요']),
                                  ('고경도 회전 날개', ['단단한 소재라', '딱딱한 조각에도 버텨요'])]):
    x = M + i * (cw + 16)
    yy = pill(d, lab, y, x=x) + 16
    para(d, lines, yy, align='left', x0=x, maxw=cw)
save(im, 5)

# ── 06 목재 톱밥: 사진 위 꽉, 글 아래 ──
ph = fit(F_, W)
im, d = canvas(ph.height + 56 + 2 * 72 + 24 + 2 * LH + 50)
im.paste(ph, (0, 0)); y = ph.height + 56
y = title(d, [[('목재 톱밥도', False)], [('한 번에 깔끔하게', True)]], y) + 24
para(d, ['먼지, 나뭇잎, 톱밥까지', '한 대로 빨아들여요'], y)
save(im, 6)

# ── 07 분진 8종 그리드 ──
cw = (pw - 16) // 2; chh = 206; rowh = chh + 12 + 44 + 20
im, d = canvas(60 + 2 * 72 + 32 + 4 * rowh - 20 + 60)
y = title(d, [[('작업마다 나오는 분진', False)], [('한 대로 정리', True)]], 60) + 32
for i, (g, cap) in enumerate(zip(G, GCAP)):
    x = M + (i % 2) * (cw + 16); yy = y + (i // 2) * rowh
    im.paste(cover(g, cw, chh), (x, yy))
    d.text((x, yy + chh + 12), cap, font=F(30, True), fill=BODY)
save(im, 7)

# ── 08 스펙 띠 + 구매 전 확인 ──
hw = 560; ph = fit(H, hw)
band = 2 * 140
im, d = canvas(60 + 72 + 32 + ph.height + 40 + band + 48 + 44 + 18 + 3 * LH + 50)
y = title(d, [[('한눈에 보는 ', False), ('제품 정보', True)]], 60) + 32
im.paste(ph, ((W - hw) // 2, y)); y += ph.height + 40
d.rectangle([0, y, W, y + band], fill=BROWN)
specs = [('6단', '세기 조절'), ('2WAY', '흡입·송풍 겸용'), ('구리', '모터'), ('알루미늄', '바람통')]
for i, (big, small) in enumerate(specs):
    cx = W / 4 + (i % 2) * W / 2; yy = y + (i // 2) * 140 + 22
    fb = F(52, True); d.text((cx - fb.getlength(big) / 2, yy), big, font=fb, fill='white')
    fs = F(22); d.text((cx - fs.getlength(small) / 2, yy + 70), small, font=fs, fill='#EDE8E0')
d.line([W / 2, y + 30, W / 2, y + band - 30], fill='#6B604A', width=1)
d.line([60, y + 140, W - 60, y + 140], fill='#6B604A', width=1)
y += band + 48
y = pill(d, '구매 전 확인', y, x=M) + 18
para(d, ['1  전원 코드를 꽂아 쓰는 유선 제품이에요',
         '2  홈파기·절단기·연마기·목공 톱과 함께 써요',
         '3  쓰는 공구와 연결 입구 크기를 먼저 맞춰 보세요'], y, size=30, align='left')
save(im, 8)

# ── ZIP + 미리보기 ──
files = [f'{i:02d}.png' for i in range(1, 9)]
with zipfile.ZipFile(os.path.join(OUT, '상세페이지_전체.zip'), 'w') as z:
    for f in files: z.write(os.path.join(OUT, f), f)
ims = [Image.open(os.path.join(OUT, f)) for f in files]
th = [i.resize((215, round(i.height * 215 / 860))) for i in ims]
pv = Image.new('RGB', (4 * 225 + 10, 2 * (max(t.height for t in th) + 10) + 10), '#DDD8CF')
mh = max(t.height for t in th)
for i, t in enumerate(th): pv.paste(t, (10 + (i % 4) * 225, 10 + (i // 4) * (mh + 10)))
pv.save(os.path.join(OUT, '미리보기.png'))
print('done')
