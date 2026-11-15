# 완성된 상세 이미지에 '용감한용팀장' 대각선 워터마크를 촘촘히 깔아 새 폴더에 저장한다
import sys, math, zipfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
font_path = Path(sys.argv[3])
dst.mkdir(parents=True, exist_ok=True)
TEXT = "용감한용팀장"
ANGLE = 30          # 대각선 각도
SIZE = 30           # 글자 크기
STEP_X, STEP_Y = 300, 190   # 반복 간격

def stamp(w, h):
    """회전 전 큰 판에 글자를 엇갈리게 깔고, 30도 돌린 뒤 이미지 크기로 자른다"""
    font = ImageFont.truetype(str(font_path), SIZE)
    d = int(math.hypot(w, h)) + 400
    layer = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    for row, y in enumerate(range(0, d, STEP_Y)):
        off = (STEP_X // 2) * (row % 2)
        for x in range(-STEP_X, d, STEP_X):
            # 밝은 배경·어두운 사진 둘 다에서 보이게: 진갈색 글자 + 흰 테두리, 반투명
            dr.text((x + off, y), TEXT, font=font, fill=(81, 71, 51, 70),
                    stroke_width=2, stroke_fill=(255, 255, 255, 55))
    layer = layer.rotate(ANGLE, resample=Image.BICUBIC)
    l, t = (d - w) // 2, (d - h) // 2
    return layer.crop((l, t, l + w, t + h))

try:
    outs = []
    for p in sorted(src.glob("0*.png")):
        im = Image.open(p).convert("RGBA")
        im = Image.alpha_composite(im, stamp(*im.size)).convert("RGB")
        o = dst / p.name; im.save(o, optimize=True); outs.append(o)
        print("완료", p.name, im.size)
    with zipfile.ZipFile(dst / "상세페이지_전체.zip", "w") as z:
        for o in outs: z.write(o, o.name)
except Exception as e:
    print("실패:", e); sys.exit(1)
