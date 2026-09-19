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
## [2026-09-19] query | 노트북-맥북 Tailscale 연동 설치 → entity 페이지 생성 [[tailscale]]
- source: 카페 원격 설치 세션 실측 (크롬 원격 데스크톱 경유)
- enriched: [[tailscale]] 신규 — 구성 결과·macOS 네트워크 확장 함정·닭과달걀 문제·FileVault 주의
- cross-refs: [[불사자-자동화]] [[CS-자동화]] (아직 미작성 — 향후 연결)
- contradictions: 없음
## [2026-09-19] ingest | 맥실버 서버화 세션 (SSH 키·Claude Code 설치·workspace clone)
- source: 원격 구성 세션 실측
- enriched: [[tailscale]] — '맥실버 서버화' 섹션 신설, 적용 표에 일상 사용법 추가
- 주요 함정 기록: `!` 는 TTY 아님 / 원격 붙여넣기 `^[[200~` 깨짐 / tmux 대신 screen
- contradictions: 없음
## [2026-09-19] ingest | 맥 기존 환경 확인 → [[tailscale]] 정정
- 발견: 맥은 원래 작업 머신이었다. 워크스페이스는 ~/Documents/yongtimjang_claudecode, venv·.env·MCP 모두 기존 보유
- 정정: 3단계(파이썬·MCP 이식) 불필요. 새로 만든 중복 clone ~/workspace 삭제
- 신규 발견 이슈: 맥에 GitHub push 자격증명 없음 → 9/15 커밋 1건이 나흘간 고립돼 있었음 (노트북 경유로 구조 완료)
- contradictions: [!correction] 플래그로 기존 서술 정정
