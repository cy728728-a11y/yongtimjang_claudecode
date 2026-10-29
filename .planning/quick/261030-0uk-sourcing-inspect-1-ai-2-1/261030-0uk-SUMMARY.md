---
quick_id: 261030-0uk
status: complete
date: 2026-10-30
---

# 1차 AI 생략(--machine-only) + 2차 타오바오 중복 1회 판정 — 완료

## 실험 (run `1030_skip1st_exp`, 불사자 쓰기 없음 — 이미지검색 조회만)
- 3회차(1020_k500a·1021_k500b·1023_k500c) 1차 AI 탈락 270건 → 이미지검색 270/270 → 2차 판정
- **246건(91%) 재탈락.** 통과 24건 중 대부분은 매칭 타오바오 상품이 팔 만한 다른 물건(유리→스테인리스·아크릴 등)
- 진짜 누락 2~3건: 중국어 '适应于+차종' 호환 표기(→ 기준표에 명시), 가솔린 선외기 엔진(사용자 판단 대기)
- 270건 안에서도 같은 타오바오 상품 9건(약 3%) 자연 발생

## 변경
- `run_inspect.py prep --stage 1 --machine-only`: 기계 탈락만 machine.json, 나머지 auto.json(pass, by=auto). merge 가 바닥에 깐다
- 2차 prep: `dedupe_views` 로 itemId(없으면 썸네일 URL) 대표 1건만 AI 판정 → `dup_map.json` → merge `spread_dups` 가 복사(사용자 feedback 은 그 뒤 적용)
- worker-prompt IP 행: 适用/适配/适应于/专用 + 차종·모델명 = 호환 표기
- SKILL.md 흐름 · 테스트 3건 추가 · test_rules 의 금지 카테고리 개수 고정값(3290, 10/22 이후 3285) 을 하한으로 완화

## 검증
- test_run_inspect / test_rules 전부 ok
- 1023_k500c 스냅샷 3,000건 machine-only: 2.8초, 기계탈락 1,317 / 자동통과 1,683, merge 누락 0
- 실험 run 복사본 2차 prep: 중복 11건 묶임 → merge 복사 확인 (테스트 run 삭제)
