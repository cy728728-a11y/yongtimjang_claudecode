---
name: youtube-summary
description: YouTube 링크를 받아 썸네일 + 1000자 요약을 만들고, 선택적으로 Notion 페이지로 저장. "유튜브 요약", "이 영상 요약", "youtube 요약", "영상 정리", "유튜브 노션에 저장" 등을 언급하거나 youtube.com / youtu.be URL을 주면 자동 실행.
allowed-tools:
  - Bash
  - Read
  - Write
---

# YouTube Summary Skill

YouTube 영상의 **자막을 추출 → 1000자 요약 → (선택) Notion 저장**하는 스킬.

## 동작 흐름

1. **fetch**: `yt_fetch.py`가 영상 메타데이터(제목·채널·썸네일) + 자막을 JSON으로 추출
2. **summarize**: Claude가 자막을 읽고 한국어 **~1000자 요약** 작성 (핵심 흐름·논지 중심)
3. **present**: 채팅에 썸네일 링크 + 요약 표시
4. **publish (선택)**: `yt_publish.py`가 Notion 하위 페이지 생성 (썸네일 이미지 + 메타 콜아웃 + 요약 + 원본 북마크)

## Prerequisites

```bash
# 자막 라이브러리 (최초 1회)
pip install youtube-transcript-api

# Notion 저장을 원할 때만 (세션마다 재설정 필요)
export NOTION_TOKEN="ntn_..."
```

- Notion 저장은 **notion-handler 스킬의 `notion_api.py`를 재사용**한다 (별도 의존성 없음).
- 기본 저장 위치(부모 페이지): **Eroom Space** — `393dee53c249809a9e71f5f531396ddc`
  (다른 곳에 저장하려면 `--parent`에 다른 페이지 ID 지정)

## 사용법

### 1) 메타데이터 + 자막 추출

```bash
python .claude/skills/youtube-summary/scripts/yt_fetch.py "<youtube_url_or_id>" > fetch.json
```

출력 JSON 주요 필드: `video_id`, `title`, `author`, `thumbnail`, `url`,
`transcript`(자막 전문), `language`, `duration_sec`, `segment_count`.

- `transcript_error`가 있으면 자막이 없는 영상 → 요약 불가(사용자에게 알림).
- 콘솔에 한글이 깨져 보여도 파일 안의 UTF-8 데이터는 정상 (Windows cp949 표시 문제).

### 2) Claude가 요약 작성

`fetch.json`의 `transcript`를 읽고 **~1000자** 요약을 텍스트 파일로 저장한다.
요약 원칙:
- 결론/핵심 흐름 먼저, 군더더기 없이. 영상의 실제 논지·순서를 따라감.
- 화자·고유명사·구체 수치는 보존. 없는 내용 추측·창작 금지.
- 한 덩어리 문단 여러 개(줄바꿈 허용), 큰따옴표 남발 지양.

```bash
# (Claude가 Write 툴로 summary.txt 작성)
```

### 3) Notion 저장 (선택)

```bash
export NOTION_TOKEN="ntn_..."
python .claude/skills/youtube-summary/scripts/yt_publish.py \
  --fetch fetch.json \
  --summary summary.txt \
  --parent 393dee53c249809a9e71f5f531396ddc
```

성공 시 `{"ok": true, "page_url": "..."}` 출력. 생성 페이지 구조:

| 블록 | 내용 |
|------|------|
| 페이지 제목 | `[YT] {영상 제목}` |
| image | 썸네일(maxresdefault) |
| callout 📺 | 채널 · 길이 · 자막 언어 |
| heading_2 | "1000자 요약" |
| paragraph | 요약 본문 |
| bookmark | 원본 YouTube 링크 |

## 주의

- 자막이 없는 영상(자동 생성 자막도 없음)은 요약할 수 없다.
- `NOTION_TOKEN`은 세션 환경변수라 Bash 호출마다 다시 `export` 해야 한다. 토큰은 문서·코드에 하드코딩하지 않는다.
- 임시 파일(fetch.json, summary.txt)은 스크래치패드 디렉터리에 두는 것을 권장.

## Version History

- **v1.0.0 (2026-07-04)**: 초기 작성 — 자막 추출 + 1000자 요약 + Notion 저장. 실제 영상(기술노트with 알렉, 바이브코딩 가이드)으로 E2E 검증 완료.
