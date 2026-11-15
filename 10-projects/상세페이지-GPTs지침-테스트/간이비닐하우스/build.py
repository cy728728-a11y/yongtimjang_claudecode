# -*- coding: utf-8 -*-
# 간이 비닐하우스 상세페이지 낱장 제작 (용팀장 GPTs 지침 기준)
# - 제품 사진은 원본에서 잘라서만 사용 (새로 그리지 않음)
# - 860px 폭 낱장 PNG, 한 장에 메시지 하나
import os
import sys
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

BASE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(BASE, "src")
OUT = os.path.join(BASE, "out")
os.makedirs(OUT, exist_ok=True)

W = 860
PAD = 56
BG = (250, 248, 243)      # 아이보리
INK = (34, 38, 35)        # 본문 진한 색
SUB = (96, 102, 98)       # 보조 글자
ACC = (46, 125, 80)       # 포인트 초록
CARD = (255, 255, 255)
LINE = (226, 222, 212)

FONT_VF = r"C:\Windows\Fonts\NotoSansKR-VF.ttf"
FONT_R = r"C:\Windows\Fonts\malgun.ttf"
FONT_B = r"C:\Windows\Fonts\malgunbd.ttf"


def font(size, weight=400):
    """가변 글꼴 굵기 지정, 실패하면 맑은고딕으로 대체"""
    try:
        f = ImageFont.truetype(FONT_VF, size)
        f.set_variation_by_axes([weight])
        return f
    except Exception:
        return ImageFont.truetype(FONT_B if weight >= 600 else FONT_R, size)


def src(name, box=None, sharpen=False):
    """원본 이미지 열기 + 비율 기준(0~1) 자르기"""
    im = Image.open(os.path.join(SRC, name)).convert("RGB")
    if box:
        x0, y0, x1, y1 = box
        im = im.crop((int(im.width * x0), int(im.height * y0), int(im.width * x1), int(im.height * y1)))
    if sharpen:
        im = ImageEnhance.Sharpness(im).enhance(1.15)
    return im


def fit_w(im, w, max_scale=1.5):
    """가로 w에 맞춤. 원본 대비 최대 1.5배까지만 확대"""
    s = min(w / im.width, max_scale)
    return im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)


def rounded(im, r=18):
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, im.width, im.height], r, fill=255)
    out = Image.new("RGBA", im.size)
    out.paste(im, (0, 0), mask)
    return out


class Page:
    def __init__(self, h=2000):
        self.im = Image.new("RGB", (W, h), BG)
        self.d = ImageDraw.Draw(self.im)
        self.y = 0

    def text_w(self, s, f):
        return self.d.textlength(s, font=f)

    def center(self, s, f, color=INK, gap=14):
        x = (W - self.text_w(s, f)) / 2
        self.d.text((x, self.y), s, font=f, fill=color)
        self.y += f.size + gap

    def rich_center(self, parts, f, gap=14):
        """[(글자, 색)] 한 줄 가운데 정렬 — 키워드 색 강조용"""
        total = sum(self.text_w(s, f) for s, _ in parts)
        x = (W - total) / 2
        for s, c in parts:
            self.d.text((x, self.y), s, font=f, fill=c)
            x += self.text_w(s, f)
        self.y += f.size + gap

    def badge(self, s):
        f = font(24, 700)
        tw = self.text_w(s, f)
        bw, bh = tw + 40, 46
        x = (W - bw) / 2
        self.d.rounded_rectangle([x, self.y, x + bw, self.y + bh], 23, fill=ACC)
        self.d.text((x + 20, self.y + 8), s, font=f, fill="white")
        self.y += bh + 26

    def photo(self, im, w=W - PAD * 2, r=18, gap=36):
        im = fit_w(im, w)
        x = (W - im.width) // 2
        self.im.paste(rounded(im, r), (x, self.y), rounded(im, r))
        self.y += im.height + gap
        return im.height

    def cards(self, items, cols=2, gap=20, cap_size=26):
        """[(이미지, 캡션)] 카드 배치"""
        cw = (W - PAD * 2 - gap * (cols - 1)) // cols
        f = font(cap_size, 600)
        row_h = 0
        for i, (im, cap) in enumerate(items):
            col = i % cols
            if col == 0 and i:
                self.y += row_h + gap
                row_h = 0
            x = PAD + col * (cw + gap)
            ar = 1.4  # 가로:세로 비율 통일
            if im.width / im.height > ar:
                nw = int(im.height * ar); x0 = (im.width - nw) // 2
                im = im.crop((x0, 0, x0 + nw, im.height))
            else:
                nh = int(im.width / ar); y0 = (im.height - nh) // 2
                im = im.crop((0, y0, im.width, y0 + nh))
            ph = fit_w(im, cw - 24)
            ch = ph.height + 24 + 64
            self.d.rounded_rectangle([x, self.y, x + cw, self.y + ch], 18, fill=CARD, outline=LINE)
            px = x + (cw - ph.width) // 2
            self.im.paste(rounded(ph, 12), (px, self.y + 12), rounded(ph, 12))
            tw = self.text_w(cap, f)
            self.d.text((x + (cw - tw) / 2, self.y + 12 + ph.height + 18), cap, font=f, fill=INK)
            row_h = max(row_h, ch)
        self.y += row_h + 40

    def points(self, items):
        """하단 포인트 박스 (가로 나열)"""
        n = len(items)
        gap = 16
        bw = (W - PAD * 2 - gap * (n - 1)) // n
        f1 = font(22, 500)
        f2 = font(27, 700)
        bh = 118
        for i, (small, big) in enumerate(items):
            x = PAD + i * (bw + gap)
            self.d.rounded_rectangle([x, self.y, x + bw, self.y + bh], 16, fill=CARD, outline=LINE)
            for s, f, c, yy in ((small, f1, SUB, 24), (big, f2, ACC, 60)):
                tw = self.text_w(s, f)
                self.d.text((x + (bw - tw) / 2, self.y + yy), s, font=f, fill=c)
        self.y += bh + 40

    def checklist(self, items):
        f = font(27, 500)
        fb = font(27, 700)
        for head, body in items:
            h = 92
            self.d.rounded_rectangle([PAD, self.y, W - PAD, self.y + h], 16, fill=CARD, outline=LINE)
            self.d.ellipse([PAD + 28, self.y + 36, PAD + 46, self.y + 54], fill=ACC)
            self.d.text((PAD + 66, self.y + 28), head, font=fb, fill=INK)
            hx = PAD + 66 + self.text_w(head, fb) + 18
            self.d.text((hx, self.y + 28), body, font=f, fill=SUB)
            self.y += h + 14
        self.y += 26

    def save(self, n):
        self.y += 24
        out = self.im.crop((0, 0, W, self.y))
        path = os.path.join(OUT, f"{n:02d}.png")
        out.save(path)
        print("저장:", path, out.size)


def head(p, badge, line1, line2_parts, sub):
    p.y = 80
    p.badge(badge)
    if line1:
        p.center(line1, font(54, 800), gap=12)
    p.rich_center(line2_parts, font(54, 800), gap=26)
    p.center(sub, font(29, 400), color=SUB, gap=50)


def build():
    # 1. 메인 후킹
    p = Page()
    head(p, "조립식 간이 비닐하우스", "추운 계절에도", [("우리집 텃밭은 ", INK), ("따뜻하게", ACC)],
         "비와 추위를 막아주는 조립식 온실")
    p.photo(src("thumb-01.jpg", (0.005, 0.1, 0.995, 0.87)))
    p.points([("외피", "비·추위 차단"), ("프레임", "20mm 강관"), ("구성", "PE 필름 포함")])
    p.save(1)

    # 2. 핵심 장점 - 외피
    p = Page()
    head(p, "외피", "", [("비는 막고, ", INK), ("햇빛은 들이고", ACC)],
         "그물망으로 보강한 150g 이중 필름")
    p.photo(src("thumb-02.jpg", (0, 0.28, 1, 0.72)))
    p.cards([(src("detail-01.jpg", (0.53, 0.505, 0.96, 0.72)), "격자 그물망 보강"),
             (src("thumb-01.jpg", (0.22, 0.25, 0.75, 0.62)), "빛이 드는 반투명 필름")])
    p.points([("초기 빛 투과율", "약 85%"), ("비·추위 막고", "보온·보습")])
    p.save(2)

    # 3. 특징 - 튼튼한 프레임
    p = Page()
    head(p, "프레임", "", [("성인이 매달려도 ", INK), ("든든하게", ACC)],
         "직경 20mm 아연도금 강관 프레임")
    p.photo(src("detail-05.jpg", (0.36, 0.128, 1, 0.82)))
    p.points([("주 기둥", "직경 20mm"), ("소재", "아연도금 강관")])
    p.save(3)

    # 4. 구조/디테일 - 연결부
    p = Page()
    head(p, "연결 부품", "", [("연결부까지 ", INK), ("전부 금속으로", ACC)],
         "플라스틱 연결부 없이 끼워서 고정")
    p.cards([(src("detail-04.jpg", (0.008, 0.075, 0.452, 0.39)), "T자 금속 연결부"),
             (src("detail-04.jpg", (0.505, 0.075, 0.985, 0.39)), "기둥 연결부"),
             (src("detail-04.jpg", (0.008, 0.645, 0.452, 0.92)), "십자 금속 연결부"),
             (src("detail-01.jpg", (0.03, 0.505, 0.475, 0.725)), "필름 고정 스프링 홈")])
    p.points([("잠금 장치로", "빠르게 고정"), ("필름은", "홈에 끼워 고정")])
    p.save(4)

    # 5. 사용 편의 - 조립 과정
    p = Page()
    head(p, "조립 과정", "", [("순서대로 끼우면 ", INK), ("완성", ACC)],
         "두 사람이 함께하면 더 수월해요")
    steps = [((12, 98, 371, 276), "① 바닥 틀 펼치기"), ((381, 98, 736, 276), "② 바닥 틀 연결"),
             ((12, 287, 371, 515), "③ 기둥 세우기"), ((381, 287, 736, 515), "④ 아치 올리기"),
             ((12, 526, 371, 755), "⑤ 아치 모두 연결"), ((381, 526, 736, 755), "⑥ 가로대 고정")]
    im7 = src("detail-07.jpg")
    p.cards([(im7.crop((a + 4, b + 4, c - 4, d - 4)), cap) for (a, b, c, d), cap in steps])
    p.save(5)

    # 6. 활용 공간
    p = Page()
    head(p, "설치 모습", "", [("옥상·마당·텃밭 ", INK), ("어디든", ACC)],
         "고객님들이 직접 설치한 모습이에요")
    p.photo(src("detail-09.jpg", (0.0, 0.125, 1, 0.99)))
    p.save(6)

    # 7. 사이즈 안내
    p = Page(2600)
    head(p, "사이즈", "", [("공간에 맞춰 ", INK), ("골라 쓰세요", ACC)],
         "폭 1.2~2.4m · 길이 2~5m 선택")
    p.photo(src("detail-02.jpg", (0.03, 0.03, 0.97, 0.97)), w=560)
    sizes = {
        "폭 1.2m": ["2 × 1.85", "2.6 × 1.85", "3 × 1.85"],
        "폭 1.5m": ["2 × 1.9", "2.6 × 1.9", "3 × 1.9", "4 × 1.9", "5 × 1.9"],
        "폭 2m": ["2 × 1.95", "2.6 × 1.95", "3 × 1.95", "4 × 1.95", "5 × 1.95"],
        "폭 2.4m": ["2.6 × 2", "3 × 2", "4 × 2"],
    }
    fh = font(26, 700)
    fc = font(23, 500)
    p.center("길이 × 높이 (단위 m)", font(24, 500), color=SUB, gap=20)
    for k, vals in sizes.items():
        h = 112
        p.d.rounded_rectangle([PAD, p.y, W - PAD, p.y + h], 16, fill=CARD, outline=LINE)
        p.d.text((PAD + 26, p.y + 40), k, font=fh, fill=ACC)
        x = PAD + 150
        cy = p.y + 18
        for v in vals:
            tw = p.text_w(v, fc) + 28
            if x + tw > W - PAD - 20:
                x = PAD + 150
                cy += 40
            p.d.rounded_rectangle([x, cy, x + tw, cy + 34], 17, fill=(238, 245, 240))
            p.d.text((x + 14, cy + 3), v, font=fc, fill=INK)
            x += tw + 10
        p.y += h + 12
    p.y += 14
    p.center("외경 기준이며, 측정 방법에 따라 약 2% 차이가 있을 수 있어요", font(22, 400), color=SUB)
    p.save(7)

    # 8. 구매 전 확인
    p = Page()
    head(p, "구매 전 확인", "", [("받기 전에 ", INK), ("꼭 확인하세요", ACC)],
         "오래 잘 쓰기 위한 안내예요")
    p.photo(src("detail-08.jpg", (0.02, 0.30, 0.98, 0.51)))
    p.checklist([
        ("구성", "프레임 + PE 필름 커버"),
        ("포장", "길이 약 1.26m 상자로 배송"),
        ("설치", "두 사람이 함께 설치를 권장해요"),
        ("강풍", "아주 센 바람이 오면 커버를 걷어 주세요"),
        ("환기", "더운 날엔 문을 열어 공기를 순환해 주세요"),
        ("한파", "영하로 내려가면 보온 장치를 함께 쓰세요"),
    ])
    p.save(8)


if __name__ == "__main__":
    try:
        build()
    except Exception as e:
        print("오류:", e)
        sys.exit(1)
