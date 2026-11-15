# 비교보기.html 안에 사진을 직접 넣어서(한 파일로) 어디서 열어도 보이게 만든다
import base64, io, re, sys
from pathlib import Path
from PIL import Image

root = Path(sys.argv[1])
html = (root / "비교보기.html").read_text(encoding="utf-8")

def enc(p):
    try:
        im = Image.open(p).convert("RGB")
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=85)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print("실패", p, e); return ""

orig = [enc(root / f"_src/images/{i}.jpg") for i in range(1, 13)]
mine = [enc(root / f"0{i}.png") for i in range(1, 9)]
js = ("const ORIG=" + repr(orig).replace("'", '"') + ";\nconst MINE=" + repr(mine).replace("'", '"') + ";\n")
html = html.replace("  for (let i = 1; i <= 12; i++) add('orig', `_src/images/${i}.jpg`, `원본 ${i}`);\n  for (let i = 1; i <= 8; i++) add('mine', `0${i}.png`, `${i}장`);",
  js + "  ORIG.forEach((s,i)=>add('orig', s, `원본 ${i+1}`));\n  MINE.forEach((s,i)=>add('mine', s, `${i+1}장`));")
(root / "비교보기.html").write_text(html, encoding="utf-8")
print("완료", round(len(html)/1e6,1), "MB")
