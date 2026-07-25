---
name: thumbnail-bg-replace
description: 상품 이미지의 배경만 프로급 스튜디오 톤으로 교체한 1:1 이커머스 썸네일 생성. OpenAI gpt-image-2 모델 사용. "썸네일 만들어", "썸네일 배경 교체", "배경 바꿔", "스튜디오 배경", "상품 썸네일", "thumbnail" 등을 언급하거나 상품 이미지 경로를 주며 배경 교체를 요청하면 자동 실행. 불사자 상품 대상 작업 시 전역 완료 대장(thumbnail-done.json)과 대조해 이미 작업한 상품은 자동 skip.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
---

# 썸네일 배경 교체 (Studio Thumbnail)

상품 사진을 받아, **배경만** desaturated 파스텔 스튜디오 톤으로 교체한 1:1(1000×1000) 이커머스 썸네일을 만든다. 제품 자체는 최대한 원본대로 유지한다.

## ⚠️ 서브에이전트/워크플로우로 위임 실행될 때 필수 (2026-07-24 사고 재발 방지)

이 스킬을 워크플로우 하위 에이전트로 배치 실행할 때, **자신의 턴이 끝나면 그 배치에 대한 감시·재개 수단은 사라진다** — "생성이 계속 진행 중이며 완료되면 알려드리겠다" 식으로 미완료 상태로 턴을 마치면, 상위 파이프라인이 이를 완료로 오인하고 다음 단계(마켓 업로드 등)로 넘어가버린다(실제 사고 사례: 100건 중 15건만 로컬 생성·0건 반영된 채 다음 단계 진행). 배치가 오래 걸려도 실제로 생성(`stage2_gen.py`)과 반영(`stage2_upload.py`)이 끝날 때까지 자신의 턴 안에서 기다리고, 정말 못 끝냈으면 "N/100건 반영완료, M건 미완료"라고 정직하게 보고한다.

## 모델 (고정)

- **무조건 `gpt-image-2`** ("2.0 버전")만 사용한다. gpt-image-1 / 1.5 / mini 금지. (용팀장님 지시, 2026-07-12)
- 엔드포인트: 배경 교체·편집 → `POST /v1/images/edits`
- 생성 사이즈 `1024x1024` → PIL로 정확히 `1000x1000` 리사이즈.

## Script Location

워크스페이스 루트 기준:
```
.claude/skills/thumbnail-bg-replace/scripts/thumbnail_bg_replace.py
```

## Prerequisites

- Python + `requests`, `python-dotenv`, `Pillow` (워크스페이스 전역/venv에 이미 설치됨).
- **OpenAI API 키**: 스킬 폴더 `scripts/.env` 에 `OPENAI_API_KEY=sk-...` 형태로 저장.
  - `.env`가 없거나 키가 없으면 스크립트가 안내 후 종료 → 용팀장님께 키 요청.

## 실행

```bash
cd .claude/skills/thumbnail-bg-replace/scripts
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python thumbnail_bg_replace.py "<입력이미지경로>" ["<출력경로>"]
```

- 인자 1: 입력 상품 이미지 경로 (필수)
- 인자 2: 출력 경로 (생략 시 입력파일명에 `-thumb.png` 붙여 같은 폴더에 저장)
- Windows 콘솔 이모지 출력 때문에 `PYTHONIOENCODING=utf-8 PYTHONUTF8=1` 필수.

## 프롬프트 (기본)

배경 팔레트 중 랜덤 1색(Milk Tea, Powder Yellow, Sand Beige, Sweet Peach 등 파스텔 desaturated) · 좌상단 시네마틱 조명 → 우하단 롱 소프트 그림자(3D) · 제품 프레임 85% 점유 · 45도 쿼터뷰 · 텍스트/로고 없음 · 제품 원본 유지. 스크립트 내 `PROMPT` 상수로 관리, 필요 시 배경색·구도 조정.

## 처리 흐름

1. `.env`에서 `OPENAI_API_KEY` 로드 (없으면 종료).
2. 입력 이미지 → `/v1/images/edits` 멀티파트 호출 (`model=gpt-image-2`).
3. 응답 `data[0].b64_json` 디코딩 → 임시 저장.
4. PIL로 1000×1000 리사이즈 후 최종 저장.
5. try-except로 API 오류·타임아웃·이미지 없음(안전필터) 처리, 한국어 메시지.

## 검증

생성 후 `Read`로 육안 확인: (a) 제품 원본 보존, (b) 배경 팔레트 단색 스튜디오, (c) 우하단 소프트 그림자, (d) 텍스트/로고 없음, (e) 1000×1000. 품질 미흡 시 프롬프트/배경색 조정 후 재생성.

## 불사자 상품 배치 작업: 완료 대장 (중복 방지) — 필수

불사자 상품을 대상으로 썸네일 작업 명령을 받으면, **작업 시작 전 반드시 전역 완료 대장과 대조**해서
이미 작업한 상품은 skip 한다. run 폴더 체크포인트(`gen_status.json`)는 같은 배치 안에서만 유효하고,
이 대장은 **배치를 넘어** 기억한다.

- **대장 파일**: `20-operations/21-bulsaja-category-runs/thumbnail-done.json`
- **공용 모듈**: `.claude/skills/thumbnail-bg-replace/scripts/thumb_ledger.py`
- **계정 키**: `bulsaja`(용팀장 계정) / `bulsaja-yongssaem`(용쌤 계정).
  `run_yong.py` 래퍼가 `BULSAJA_ACCOUNT=bulsaja-yongssaem`을 주입하므로 용쌤 작업은 자동 인식.
- **계정 명시 필수**: `stage2_gen.py`·`stage2_upload.py`는 `--account`(또는 `BULSAJA_ACCOUNT`)
  없이는 실행 거부. 계정이 틀리면 대장 대조가 조용히 무력화되어 전량 재생성 과금이 나기 때문
  (gen은 래퍼 없이 직접 실행하는 경우가 많아 특히 주의 — 용쌤 작업이면 `--account bulsaja-yongssaem`).
- **완료 판정**: `status`가 `ok`(교체 반영) 또는 `kept-original`(생성 후 원본 유지 결정) → skip 대상.
- **기록 시점**: 불사자 대표이미지 저장 성공 시 `stage2_upload.py`가 자동 기록.
  파이프라인 밖에서 작업했으면 `mark`로 수동 기록.
- **강제 재작업**: 용팀장님이 명시적으로 다시 하라고 할 때만 `--ignore-ledger` 사용.
- **보고 형식**: 작업 시작 시 "전체 N건 중 이미 완료 M건 skip → 실제 대상 K건"으로 보고.

```bash
cd .claude/skills/thumbnail-bg-replace/scripts
# 계정별 완료 건수
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python thumb_ledger.py stats
# 특정 상품 완료 여부
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python thumb_ledger.py check --account bulsaja-yongssaem <productId> ...
# 수동 기록 / 과거 run 이관
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python thumb_ledger.py mark --account <계정> --run <run명> <productId> ...
PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python thumb_ledger.py seed --run-dir <RUN폴더> --account <계정> --date YYYY-MM-DD
```

배치 스크립트(현재 원본: `20-operations/21-bulsaja-category-runs/0723_yong1-1/scripts/`)는
대장 연동이 반영되어 있음 — `stage2_gen.py`가 시작 시 대장 skip, `stage2_upload.py`가 성공 시 대장 기록.

이관 이력: 2026-07-23 `0723_yong1-1` 100건 (교체 99 + 원본유지 1, 계정 bulsaja-yongssaem).

## 참고

- gpt-image-2는 장면을 새로 렌더링하므로 제품이 픽셀 단위로 100% 동일하진 않음(디테일 미세 재해석 가능). 원본 완전 보존이 중요하면 사용자에게 안내.
- 결과물을 워크스페이스로 정리하려면 `50-resources/attachments/`로 복사.
