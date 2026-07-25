#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube 영상 메타데이터 + 자막(transcript)을 가져와 JSON으로 출력.
- 메타데이터: oembed API (키 불필요) → 제목, 채널명, 썸네일
- 자막: youtube-transcript-api (한국어 → 영어 → 그 외 우선순위)
- 썸네일: oembed 우선, 없으면 규칙 기반 maxresdefault URL

출력: stdout에 JSON 한 덩어리 (Claude가 읽어 요약)
"""
import sys
import io
import json
import re
import urllib.request
import urllib.parse

# Windows 콘솔 인코딩 문제 방지 (한글 깨짐)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")


def extract_video_id(url_or_id: str) -> str:
    """다양한 형태의 YouTube URL / ID에서 11자리 video_id 추출."""
    s = url_or_id.strip()
    # 이미 순수 ID면 그대로
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s
    patterns = [
        r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/|/live/)([A-Za-z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, s)
        if m:
            return m.group(1)
    raise ValueError(f"video_id를 URL에서 추출하지 못했습니다: {url_or_id}")


def get_metadata(video_id: str) -> dict:
    """oembed로 제목/채널/썸네일 획득. 실패해도 기본값 반환."""
    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    meta = {
        "title": None,
        "author": None,
        "thumbnail": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
    }
    ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    # 1차: oembed (가장 깔끔, 키 불필요)
    try:
        oembed = "https://www.youtube.com/oembed?" + urllib.parse.urlencode(
            {"url": watch_url, "format": "json"}
        )
        req = urllib.request.Request(oembed, headers=ua)
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        meta["title"] = data.get("title")
        meta["author"] = data.get("author_name")
    except Exception as e:
        meta["_oembed_error"] = str(e)

    # 2차 폴백: watch 페이지 HTML에서 og:title / author 추출
    if not meta["title"]:
        try:
            req = urllib.request.Request(watch_url, headers=ua)
            with urllib.request.urlopen(req, timeout=15) as r:
                html = r.read().decode("utf-8", "ignore")
            m = re.search(r'<meta property="og:title" content="([^"]+)"', html)
            a = re.search(r'"author":"([^"]+)"', html)
            if m:
                meta["title"] = m.group(1)
            if a and not meta["author"]:
                meta["author"] = a.group(1)
        except Exception as e:
            meta["_watch_error"] = str(e)

    return meta


def get_transcript(video_id: str) -> dict:
    """자막 텍스트 + 언어 정보 반환. 1.x 인스턴스 API 우선, 실패 시 폴백."""
    pref = ["ko", "en", "ja", "en-US", "ko-KR"]
    result = {"transcript": None, "language": None, "transcript_error": None}
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        segments = None
        lang = None
        # 1.x 인스턴스 API
        try:
            api = YouTubeTranscriptApi()
            fetched = api.fetch(video_id, languages=pref)
            segments = [{"text": s.text, "start": s.start} for s in fetched]
            lang = getattr(fetched, "language_code", None)
        except TypeError:
            # 구버전 정적 API 폴백
            fetched = YouTubeTranscriptApi.get_transcript(video_id, languages=pref)
            segments = [{"text": s["text"], "start": s["start"]} for s in fetched]

        text = " ".join(seg["text"].replace("\n", " ") for seg in segments).strip()
        text = re.sub(r"\s+", " ", text)
        result["transcript"] = text
        result["language"] = lang
        result["segment_count"] = len(segments)
        if segments:
            result["duration_sec"] = int(segments[-1]["start"])
    except Exception as e:
        result["transcript_error"] = f"{type(e).__name__}: {e}"
    return result


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: yt_fetch.py <youtube_url_or_id>"}, ensure_ascii=False))
        sys.exit(1)

    raw = sys.argv[1]
    try:
        video_id = extract_video_id(raw)
    except ValueError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)

    out = {
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
    }
    out.update(get_metadata(video_id))
    out.update(get_transcript(video_id))
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
