# 00-wiki 운영 가이드

> Karpathy "LLM Wiki" 아이디어 기반. 지식을 복리로 축적.
> 규칙은 `SCHEMA.md`, 토픽 카탈로그는 `index.md`, 활동 기록은 `log.md`.

## 핵심 아이디어

- **단순 축적이 아닌 통합**. 같은 소스에서 여러 토픽이 동시에 enriched 되어야 복리.
- **기존 페이지 확장 우선**. 비슷한 토픽 있으면 새 파일 만들지 말 것.
- **출처 인용 필수**. 모든 추가에 [source: 출처, 날짜].
- **모순은 삭제 금지**. `[!contradiction]` 플래그만. 판단은 사용자.

## 사용 흐름

1. **Query** — 주제에 대해 물으면 Claude가 `index.md` → `Grep` → `Read` 순으로 확인
2. **Ingest** — 소스가 쌓이면 "wiki-ingest" 호출하여 토픽 페이지에 통합
3. **Lint** — 주기적으로 "wiki-lint" 호출하여 헬스체크

## 참고

- [[SCHEMA]] — 상세 규칙 (페이지 형식, Infobox, 3오퍼레이션)
- [[index]] — 토픽 카탈로그
- [[log]] — 활동 로그
