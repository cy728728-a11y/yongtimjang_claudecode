#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube 요약을 Notion 페이지로 저장.
- notion-handler 스킬의 notion_api.py를 재사용 (create_page / parse_blocks / append_blocks)
- 부모 페이지 아래에 '[YT] 제목' 하위 페이지를 만들고
  썸네일 이미지 + 메타데이터 콜아웃 + 1000자 요약 + 원본 북마크를 넣는다.

사용:
  export NOTION_TOKEN="..."
  python yt_publish.py --fetch fetch.json --summary summary.txt --parent PAGE_ID

입력 파일:
  --fetch   : yt_fetch.py가 만든 JSON (title, author, thumbnail, url, duration_sec 등)
  --summary : 요약 본문 텍스트 (UTF-8, 한 덩어리)
"""
import sys
import io
import os
import json
import argparse
import importlib.util

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")


def load_notion_api():
    """sibling notion-handler 스킬의 notion_api.py를 동적 로드."""
    here = os.path.dirname(os.path.abspath(__file__))
    # .../.claude/skills/youtube-summary/scripts -> skills 루트로 이동
    skills_root = os.path.abspath(os.path.join(here, "..", ".."))
    api_path = os.path.join(skills_root, "notion-handler", "scripts", "notion_api.py")
    if not os.path.exists(api_path):
        raise FileNotFoundError(f"notion_api.py를 찾지 못했습니다: {api_path}")
    spec = importlib.util.spec_from_file_location("notion_api", api_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fmt_duration(sec):
    if not sec:
        return "-"
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}시간 {m}분" if h else f"{m}분 {s}초"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", required=True, help="yt_fetch.py 결과 JSON 경로")
    ap.add_argument("--summary", required=True, help="요약 본문 텍스트 파일 경로")
    ap.add_argument("--parent", required=True, help="부모 Notion 페이지 ID")
    args = ap.parse_args()

    with open(args.fetch, encoding="utf-8") as f:
        meta = json.load(f)
    with open(args.summary, encoding="utf-8") as f:
        summary = f.read().strip()

    api = load_notion_api()

    title = meta.get("title") or meta.get("video_id")
    author = meta.get("author") or "-"
    url = meta.get("url")
    thumb = meta.get("thumbnail")
    dur = fmt_duration(meta.get("duration_sec"))
    lang = meta.get("language") or "-"

    # 1) 하위 페이지 생성 (제목만)
    page = api.create_page(
        args.parent,
        {"title": f"[YT] {title}"},
        children=None,
        is_database=False,
    )
    if page.get("object") != "page":
        print(json.dumps({"error": "페이지 생성 실패", "detail": page}, ensure_ascii=False))
        sys.exit(1)
    page_id = page["id"]

    # 2) 본문 블록 구성 (parse_blocks가 단순 dict → Notion 포맷 변환)
    meta_line = f"🎬 채널: {author}   ·   ⏱ 길이: {dur}   ·   🗣 자막: {lang}"
    simple_blocks = [
        {"type": "image", "url": thumb},
        {"type": "callout", "text": meta_line, "emoji": "📺"},
        {"type": "heading_2", "text": "1000자 요약"},
        {"type": "paragraph", "text": summary},
        {"type": "divider"},
        {"type": "bookmark", "url": url},
    ]
    # append_blocks가 내부에서 parse_blocks를 호출하므로 단순 블록을 그대로 전달
    resp = api.append_blocks(page_id, simple_blocks)
    if "results" not in resp and resp.get("object") == "error":
        print(json.dumps({"error": "블록 추가 실패", "detail": resp, "page_id": page_id},
                         ensure_ascii=False))
        sys.exit(1)

    print(json.dumps({
        "ok": True,
        "page_id": page_id,
        "page_url": page.get("url"),
        "title": f"[YT] {title}",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
