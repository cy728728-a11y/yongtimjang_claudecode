# -*- coding: utf-8 -*-
"""강의안 pptx → 같은 폴더 같은 이름 .md (장별 화면 텍스트 + 발표자 노트)"""
import datetime
import os
import sys

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE


def shape_texts(shapes):
    out = []
    for sh in shapes:
        try:
            if sh.shape_type == MSO_SHAPE_TYPE.GROUP:
                out += shape_texts(sh.shapes)
            elif sh.shape_type == MSO_SHAPE_TYPE.PICTURE:
                out.append("[이미지]")
            elif sh.has_text_frame and sh.text_frame.text.strip():
                out.append(sh.text_frame.text.strip())
        except Exception:
            continue
    return out


def convert(src):
    prs = Presentation(src)
    dst = os.path.splitext(src)[0] + ".md"
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(src)).strftime("%Y-%m-%d %H:%M")
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# {os.path.basename(src)}", "",
             f"- 원본: `{src}`", f"- 원본 수정시각: {mtime}", f"- 변환 시각: {now}",
             f"- 장 수: {len(prs.slides)}", ""]
    skip = ("용팀장 무료 라이브", "1:1 상담 신청 · 부담 없이 →")
    for i, s in enumerate(prs.slides, 1):
        texts = [t for t in shape_texts(s.shapes) if not t.startswith(skip)]
        # 연속된 [이미지] 정리
        body = []
        for t in texts:
            if t == "[이미지]" and body and body[-1] == "[이미지]":
                continue
            body.append(t)
        head = next((t for t in body if t != "[이미지]"), "").split("\n")[0][:40]
        lines.append(f"## {i}장 · {head}")
        lines += [t.replace("\n", " / ") for t in body[1:] if t] if body else []
        if s.has_notes_slide:
            note = s.notes_slide.notes_text_frame.text.strip()
            if note:
                lines.append("")
                lines += ["> 노트: " + n if j == 0 else "> " + n for j, n in enumerate(note.split("\n"))]
        lines.append("")
    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return dst


if __name__ == "__main__":
    for p in sys.argv[1:]:
        try:
            print("저장:", convert(p))
        except Exception as e:
            print("실패:", p, e)
