---
name: sourcing-inspect
description: 불사자 "엔잡곰소싱기" 캠페인 상품을 자동 검수한다 — 1차(매칭 전 네이버 원본)·2차(타오바오 매칭 상품) pass/drop 판정을 기계 규칙 + AI 팬아웃으로 하고, 사람이 훑어볼 결과표(review.html)를 만든다. "소싱 검수", "상품검수", "검수 돌려줘", "엔잡곰 검수", "소싱기 검수", "캠페인 검수", "sourcing inspect" 등을 언급하면 자동 실행. ※ 현재는 판정 단계만 — 휴지통 이동·이미지 매칭·상품수집 반영은 2단계(쓰기 API 실측 후)에 붙는다.
---

# sourcing-inspect — 소싱기 상품검수 (판정 단계)

설계: `docs/superpowers/specs/2026-10-18-sourcing-inspection-design.md`
계획: `docs/superpowers/plans/2026-10-18-sourcing-inspect.md`

## 원칙
- **애매하면 drop.** 금지품 1건 놓치는 게 멀쩡한 상품 1건 버리는 것보다 비싸다.
- 1차는 **네이버 상품명의 브랜드만으로 떨어뜨리지 않는다** — 실제로 팔 건 이미지매칭으로 찾은 브랜드 없는 타오바오 물건이고 브랜드 검사는 2차 몫(2026-10-18). 호환·전용 부품, 캐릭터·레고, 디자인 복제품, 골프·구기, 캠핑 버너류는 1차에서도 drop.
- 2차는 **타오바오 상품만** 본다. 네이버 썸네일·상품명은 판정에 영향 0(2026-10-19). 왼쪽(네이버)과 같은 상품인지는 안 따진다(오매칭이어도 팔 만하면 pass).
- **이 단계는 불사자에 쓰지 않는다.** 읽기(`bulsa-sourcing-products`)만.
- 기준 수정은 `rules/` 파일에서만: `banned_cats.txt`(금지 카테고리), `banned_keywords.json`(확실한 금지어 — 상품명만 봄), `worker-prompt.md`(AI 판정 기준표).

## 캠페인
| 이름 | campaignId |
|---|---|
| 엔잡곰마켓 | `YWfs4MpPnVWHzYW` |
| 마켓 28765개 판매1이상 | `kwy9jllI5NICgPo` |

## 흐름
```bash
PY=.venv/bin/python3; S=.claude/skills/sourcing-inspect/scripts
$PY $S/web_token.py                                   # 크롬 프로필 → ~/.eroom/bulsaja-web.json (토큰 값 비출력)
$PY $S/run_inspect.py fetch  --run-dir <R> --campaign <ID>
$PY $S/run_inspect.py prep   --run-dir <R> --stage 1|2 [--limit N --sample random]
$PY $S/run_inspect.py batch  --run-dir <R> --size 40
$PY $S/run_inspect.py pending --run-dir <R>           # 출력 JSON 을 그대로 Workflow 'inspect-fanout' args 로
#   → Workflow({name: "inspect-fanout", args: <pending 출력>})   (judged/judged_NNN.json 생성)
$PY $S/run_inspect.py merge  --run-dir <R>            # 누락 있으면 pending → Workflow 재호출
$PY $S/run_inspect.py report --run-dir <R>            # <R>/review.html
```

### 기준 수정 후 부분 재판정 (전량 재실행 금지)
```bash
$PY $S/run_inspect.py remachine --run-dir <R>                      # 기계 규칙(WATT 등) 바뀌면 전 대상 재적용
$PY $S/run_inspect.py recheck --run-dir <R> --pattern '정규식'       # 통과 중 일치만 재검 → batch_9001~ (drop 우선)
$PY $S/run_inspect.py recheck --run-dir <R> --source drop --reason IP,CATEGORY [--note] --pattern '정규식'
#   탈락 재심 → batch_9501~ (원판정을 양방향으로 덮음, 재심끼리는 나중 배치가 이김). --note = AI 메모도 검색
#   출력 batches 를 Workflow inspect-fanout args 의 range {from,to,count,imgs,lastCount,lastImgs} 로
$PY $S/run_inspect.py report --run-dir <R> [--only drop]            # review.html / review_drop.html
```
- **사용자가 직접 정한 판정은 `rules/feedback_*.json`(pass/drop → id 목록)에 넣는다 — merge 가 최우선으로 덮는다.**
- 워크플로 워커는 effort 를 낮추지 마라(2차가 썸네일을 안 연다). 2차는 thumbs_read 80% 미만이면 재팬아웃.
- `<R>` 은 이름만 주면 `<data_root>/sourcing-inspect/runs/<R>`.
- 같은 run-dir 재실행 시 judged 파일이 있는 배치는 건너뛴다(디스크가 정본).
- 1차 대상 = 매칭 결과 없음, 2차 대상 = 매칭 결과 있음 또는 match_failed(→ 기계 NO_MATCH).

## 토큰
- 웹 API 는 MCP 토큰이 아니라 웹 로그인 토큰(헤더 `accesstoken` 7일 + `refreshtoken` 30일)이다.
- 401 → 크롬(Claude 확장이 붙은 "Default" 프로필)에서 불사자에 **cy17281728** 구글 계정으로 재로그인(이 프로필 기본 자동로그인은 cy728728 이라 '다른 계정 사용' 필요) → `web_token.py` 재실행. 비밀번호는 다루지 않는다.

## 결과 보고
- merge 출력(통과/탈락·사유 분포·누락)과 review.html 경로를 보고한다.
- 결과표는 **통과 쪽부터** 훑게 한다 — 금지품이 섞였는지가 핵심.
