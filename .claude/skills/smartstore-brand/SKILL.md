---
name: smartstore-brand
description: 스마트스토어(네이버) 브랜드 에셋 생성 — 로고 / 모바일 배너 / PC 배너. OpenAI gpt-image-2 모델 사용. "로고 만들어줘", "모바일 배너 만들어줘", "PC 배너 만들어줘", "피씨 배너", "스마트스토어 로고", "마켓 배너" 등을 언급하면서 마켓명을 주면 자동 실행.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
---

# 스마트스토어 브랜드 에셋 (로고 / 배너)

마켓명을 받아 스마트스토어용 **로고**, **모바일 배너**, **PC 배너**를 gpt-image-2로 생성한다.
용팀장님이 마켓명 + 종류를 말하면 해당 종류만 만든다. 결과물은 **한 장만** 저장(크롭 전 원본 안 남김).

## 3종 규격 (고정)

| 종류 | 트리거 예시 | 출력 크기 | 비율 |
|------|-------------|-----------|------|
| **로고** | "로고 만들어줘" | 1300×1300 | 1:1 정사각 |
| **모바일 배너** | "모바일 배너 만들어줘" | 750×240 | 3.125:1 |
| **PC 배너** | "PC/피씨 배너 만들어줘" | 1280×200 | 6.4:1 |

- 로고 슬로건: **안심하고 맡기세요** / 배너 서브 메시지: **안심하고 맡기는 쇼핑**
- 톤: warm, kind, trustworthy · 플랫 벡터 · 소프트 블루/그린 웜톤

## 모델 (고정)

- **무조건 `gpt-image-2`** 만 사용 (용팀장님 지시, 2026-07-12). gpt-image-1 / 1.5 / mini 금지.
- 엔드포인트: 신규 생성 → `POST /v1/images/generations`
- gpt-image-2는 3:1·6.4:1 극단 비율을 직접 못 만듦 → **1536×1024로 생성 후 중앙 밴드 크롭 → 목표 크기 리사이즈**. 로고는 1024×1024 생성 후 1300으로 리사이즈.

## Script Location

```
.claude/skills/smartstore-brand/scripts/gen_asset.py
```

## Prerequisites

- Python + `requests`, `python-dotenv`, `Pillow` (워크스페이스에 이미 설치됨).
- **OpenAI API 키**: `thumbnail-bg-replace/scripts/.env` 의 `OPENAI_API_KEY` 를 재사용한다.
  - 키가 없으면 스크립트가 안내 후 종료 → 용팀장님께 키 요청.

## 실행

```bash
cd .claude/skills/smartstore-brand/scripts
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python gen_asset.py <mode> "<마켓명>" ["<출력경로>"]
```

- `mode`: `logo` | `mobile` | `pc`
- 출력경로 생략 시 `50-resources/attachments/` 아래 자동 명명:
  - `<마켓명>_logo.png`
  - `<마켓명>_모바일배너_750x240.png`
  - `<마켓명>_PC배너_1280x200.png`
- Windows 콘솔 이모지/한글 출력 때문에 `PYTHONIOENCODING=utf-8 PYTHONUTF8=1` 필수.

## 처리 흐름

1. `.env`에서 `OPENAI_API_KEY` 로드 (없으면 종료).
2. mode별 프롬프트 생성 → `/v1/images/generations` 호출 (`model=gpt-image-2`).
3. 응답 `data[0].b64_json` 디코딩 → 임시 저장.
4. 로고: 1300×1300 리사이즈. 배너: 가로폭 기준 중앙 밴드 크롭 → 목표 크기 리사이즈.
5. 결과물 한 장만 저장, 임시파일 삭제. try-except로 오류·타임아웃·안전필터 처리(한국어 메시지).

## 검증

생성 후 `Read`로 육안 확인: (a) 마켓명 맞춤법 정확 + 가장 크고 진함, (b) 서브 메시지/슬로건 가독성, (c) 아이콘 테마 적절·과하지 않음, (d) 배경 웜톤, (e) 정확한 출력 크기. 미흡하면 프롬프트·컬러 조정 후 재생성.

## 참고

- 여러 종류를 한 번에 요청하면(예: "로고랑 배너 둘 다") mode를 각각 실행.
- 크롭이 위/아래를 잘라내므로, 아이콘이 잘리면 프롬프트의 "thin central strip / margin" 강조를 조정.
- 결과물은 `50-resources/attachments/`에 저장됨.
