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
## [2026-09-19] ingest | 맥 원격 세션 한글 깨짐 해결 + 공유 모드 구성 → [[tailscale]]
- 해결: screen -U + .screenrc defutf8 + work 스크립트 LANG. 핵심은 기존 세션을 죽여야 설정이 먹는다는 것
- 정정: 맥 tailnet 이탈 원인은 잠자기가 아니라 Tailscale 앱 종료였음
- 추가: ss = 공유 모드(screen -x)로 맥 화면과 노트북이 같은 화면을 동시에 봄
- contradictions: [!correction] 잠자기 오진단 정정
## [2026-10-02] ingest | 무료강의 공지방 카톡 5건 (자청 초자립·디노 2회차·부자곰·N잡연구소)
- source: 50-resources/attachments/무료강의-공지방-레퍼런스/ (사용자 제공, Downloads 원본 + zip)
- created: [[무료강의-공지방-시퀀스]] (5구간 비교: 사전육성/카운트다운/라이브중 푸시/결제 클로징/사후 + 용팀장 조합 시퀀스·문구 템플릿)
- enriched: [[자청-마케팅이론-용팀장-적용판]] (9장 보강 — 8/12 결제 클로징 구조, 8/27 조건부 재판매)
- cross-refs: [[무료강의-공지방-시퀀스]] ↔ [[자청-마케팅이론-용팀장-적용판]]
- contradictions: 없음 (단, 디노·부자곰 내부 수치 불일치는 페이지에 약점으로 기록)
## [2026-11-08] ingest | sebia.ai 노션 「질문 한 줄로 60초 애니메이션 만든 프롬프트」 (힉스필드 콘텐츠 팩토리)
- source: https://app.notion.com/p/60-40206e67232081809cf7e3611a59f9de (공개 페이지, 원문 사본 00-inbox/2026-11-08_힉스필드-…_원문.md)
- created: [[힉스필드-콘텐츠-팩토리]] (entity — 만약에 숏폼 뼈대 3요소, 프롬프트 갈아 끼울 4자리, 20초 vs 60초 교훈 6가지, 크레딧 예상 vs 실차감 표)
- cross-refs: motion-graphic 스킬의 "장면 최소 3.5초" 원칙과 같은 결론("각 단계에 여유") → 도구 무관 원칙으로 승격 메모
- contradictions: 없음
- 비고: 연동 앱에 미공유 페이지라 노션 API 404 → 공개 페이지용 loadPageChunk 경로로 읽음
## [2026-11-08] ingest | AI TREND 「바로 해보는 리버스 엔지니어링 프롬프트와 자료집」
- source: https://aitrend-library.pages.dev/g/reverse-engineering/ (공개 페이지, 원문 사본 00-inbox/2026-11-08_AI트렌드-리버스엔지니어링-프롬프트-REA-replica_원문.md)
- created: [[리버스-엔지니어링-프롬프트-REA-replica]] (entity — 프롬프트 공식 4칸, 예시 3개, REA·replica 설치·순서, 체크리스트, 10월 말 클로드 제한)
- cross-refs: [[힉스필드-콘텐츠-팩토리]] (한 문장 프롬프트 계열) · review-analyzer 스킬(= replica entrepreneur 발상) · detail-page-opus 끝판왕 템플릿(변형 생성 통로)
- contradictions: 없음
- 비고: 페이지 본문 60만 자 중 글자는 6천 자, 나머지는 이미지 데이터 → 이미지 걷어내고 저장. 적용 판단: REA·replica 본체보다 공식·리뷰불만 발상·체크리스트 3가지가 사업에 유효

## [2026-11-08] ingest | sebia.ai 노션 「클로드 코드가 나한테 전화 걸게 만드는 법」 (call-me)
- source: https://app.notion.com/p/3fd06e6723208148a80fdf50f9db23f4 (유튜브 쇼츠 고정 댓글, 공개 페이지, 원문 사본 00-inbox/2026-11-08_세비아-클로드코드-전화걸기-call-me_원문.md)
- created: [[클로드코드-전화-call-me]] (entity — Bland.ai 전화 세팅, 한국 번호 크레딧 $5 함정, 키체인 보안, 귀찮지 않게 하는 5규칙, API 파라미터)
- cross-refs: auto-watch 카톡 알림(일방향) 대비, "사람 큐를 만들지 마라" 원칙과의 긴장 메모
- contradictions: 없음
- 비고: loadPageChunk 경로로 읽음. 한 통 요금 칸은 원문이 비어 있음
