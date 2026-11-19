# -*- coding: utf-8 -*-
"""AI 직원 첫 출근 키트: 스타일(_base.css) + 본문(_body.html) → HTML → PDF"""
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "AI직원-첫출근-키트"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

EXTRA = """
@page { @bottom-right { content: counter(page) " / " counter(pages); font-size:8pt; color:#5E655F; font-family:"Nanum Gothic","Apple SD Gothic Neo",sans-serif; } }
@page :first { @bottom-right { content: none; } }
.code{background:#1F2421;color:#F7F3EA;border-radius:2.5mm;padding:3.2mm 4mm;margin:2mm 0 3mm;font-family:Menlo,Consolas,monospace;font-size:9.6pt;break-inside:avoid;word-break:break-all}
.code .lab{display:block;font-family:"Nanum Gothic","Apple SD Gothic Neo",sans-serif;font-size:7.8pt;font-weight:700;color:#F3B07F;letter-spacing:.4px;margin-bottom:1.2mm}
code{font-family:Menlo,Consolas,monospace;font-size:.92em;background:#EFE8D8;border-radius:1mm;padding:0 1.2mm}
kbd{display:inline-block;font-family:Menlo,monospace;font-size:8.4pt;border:1px solid #B9B09C;border-bottom-width:2px;border-radius:1.2mm;padding:0 1.5mm;background:#fff;line-height:1.45}
kbd.k2{color:#1F2421;font-size:11pt}
.card.dark code{background:rgba(255,255,255,.15);color:#fff}
h3{break-after:avoid}
table{break-inside:auto} tr{break-inside:avoid;break-after:auto}
tr:nth-child(-n+2){break-after:avoid}
.end{padding:9mm 8mm;min-height:0;font-size:9.6pt}
.end h2{font-size:16.5pt}
.prompt.long{break-inside:auto}
.chap{page-break-before:auto;break-before:auto;margin-top:9mm}
.chap-head{break-inside:avoid;break-after:avoid}
"""

try:
    css = (HERE / "_base.css").read_text(encoding="utf-8").replace("</style>", EXTRA + "\n</style>")
    body = (HERE / "_body.html").read_text(encoding="utf-8")
    html = ('<!DOCTYPE html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
            '<title>AI 직원 첫 출근 키트 — 용팀장</title>\n' + css + "\n</head>\n<body>\n" + body + "\n</body>\n</html>\n")
    hp = HERE / f"{NAME}.html"
    hp.write_text(html, encoding="utf-8")
    pp = HERE / f"{NAME}.pdf"
    subprocess.run([CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pp}", hp.as_uri()], check=True, capture_output=True)
    print("완료:", pp)
except Exception as e:
    print("실패:", e)
