# Wiki Activity Log

> Append-only. parseable prefix 형식으로 기록.
> `grep "^## \[" log.md | tail -5` 로 최근 활동 확인.

## 형식

```
## [YYYY-MM-DD] ingest | [소스명]
## [YYYY-MM-DD] lint | Wiki Health Check
## [YYYY-MM-DD] query | [질문 → 새 synthesis 페이지 생성]
```

---

## [2026-04-24] init | Wiki 초기화
## [2026-07-05] query | 중국·미국 구매대행 시장 조사 → synthesis 페이지 생성 [[해외구매대행-시장-중국-미국]]
## [2026-08-14] ingest | 이상한마케팅 아카데미 공지방 카톡 대화록(2026-07-15~08-14)
- source: 카카오톡 받은 파일 Talk_2026.8.14 15-03-1.txt (자청/이상한마케팅 아카데미 무료 라이브 공지방)
- enriched: [[자청-마케팅이론-용팀장-적용판]] (9번 섹션 신설 — 라이브 전후 공지방 카피 시퀀스 5패턴: 저빈도 드립/사전질문 접수/분산 카운트다운/깜짝 접점/종료 후 차등 혜택)
- cross-refs: 9번 섹션 ↔ 8번 섹션(라이브 내부 장치) ↔ 10번 섹션(실행 우선순위, 6번째 항목 추가)
- contradictions: 없음
