#!/usr/bin/env python3
"""검수 페이지 공용 부품 — 썸네일(가로 3열 비교)·상세(세로 8장)가 공유한다.

이미지가 승인 대상이면 텍스트 검수표가 안 통한다(2026-07-28 실전 교훈).
본문 구조는 스킬마다 다르지만 스타일·이미지 태그·페이지 셸은 같다 — 그것만 여기 둔다.
전부 순수 함수(파일 IO 는 `write` 하나) 라서 테스트가 된다.
"""
import html
import os

CSS = """
body{font-family:-apple-system,Segoe UI,sans-serif;background:#111;color:#eee;
     margin:0;padding:24px;}
h1{font-size:18px;color:#fff;}
.card{background:#1c1c1c;border:1px solid #333;border-radius:8px;
      padding:16px;margin-bottom:20px;}
.card h2{font-size:15px;margin:0 0 4px;color:#fff;}
.pid{color:#888;font-size:12px;margin-bottom:8px;}
.reason{color:#f0a020;font-size:13px;margin-bottom:10px;}
.error{color:#e05050;font-size:13px;}
.row{display:flex;gap:14px;flex-wrap:wrap;}
.col{text-align:center;}
.col img{max-width:220px;max-height:220px;border-radius:4px;
         border:2px solid #444;object-fit:contain;background:#000;}
.col .label{font-size:12px;color:#aaa;margin-top:4px;}
.col.gen img{border-color:#3a8;}
.meta{color:#777;font-size:12px;margin-top:8px;}
.sections{display:flex;flex-direction:column;gap:10px;align-items:flex-start;}
.sections img{max-width:420px;max-height:none;}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:12px;
       background:#2a3a5a;color:#cfe;margin-left:8px;}
"""


def img_tag(url, label, cls=""):
    """이미지 1장. 빈 url 이면 빈 문자열(호출부에서 분기하지 않게)."""
    if not url:
        return ""
    return (f'<div class="col {html.escape(cls, quote=True)}">'
            f'<img src="{html.escape(str(url), quote=True)}" loading="lazy">'
            f'<div class="label">{html.escape(str(label), quote=True)}</div></div>')


def shell(title, body_parts, count_label=""):
    """doctype~/html 페이지 전체. body_parts 는 이미 만들어진 HTML 조각 목록."""
    head = html.escape(str(title))
    h1 = f"{head} · {html.escape(str(count_label))}" if count_label else head
    return "\n".join([
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{head}</title><style>{CSS}</style></head><body>",
        f"<h1>{h1}</h1>",
        *body_parts,
        "</body></html>",
    ])


def write(html_text, out_path):
    """문자열을 파일로 쓰고 경로를 반환한다."""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_text)
    return out_path
