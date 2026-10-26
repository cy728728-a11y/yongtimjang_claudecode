---
name: detail-page-opus
description: 판매자상품코드를 받아 Aside 에서 Claude Opus 5.5 로 고퀄 스마트스토어 상세페이지(860px 낱장 PNG, 아이보리+진갈색 C 세일즈형, 원본 컷 70% 이상 활용, 상표등록번호·무단복제 경고·마켓명 펜체 워터마크 포함)를 만든다. 불사자 크레딧을 쓰지 않고 불사자에 반영하지 않는다. "오퍼스 상세페이지", "오퍼스로 상세 만들어줘", "고퀄 상세페이지", "직접 상세페이지 만들어줘", "아사이드 상세페이지", "워터마크 넣은 상세페이지" 등을 언급하며 상품코드를 주면 자동 실행. ※ 불사자 내부 AI 상세페이지 배치(크레딧 소모)는 bulsaja-detail-page.
---

# detail-page-opus — Aside + Opus 5.5 상세페이지

제작 규칙 정본은 Aside 계정 스킬 `~/.aside/u/0/skills/user/smartstore-detail-page/SKILL.md`(기준 `2026-10-23-opus-v1`)에 있다.
이 스킬은 **디스패처**다. 규칙을 여기 복제하지 말고, 바꿀 일이 있으면 Aside 스킬을 고친다.

## 입력
- 판매자상품코드(필수, 여러 개면 한 개씩 순서대로)
- 선택: 스타일(A/B/C, 기본 C) · "보호 표시 없이"(촬영용) · 모델 변경(기본 `claude-code/claude-opus-5-5`)

## 흐름

1. **상품 확인** — `mcp__bulsaja__bulsaja_product_find_by_code` 로 내부 ID·마켓그룹·상품명을 찾는다. 0건·다건이면 멈추고 보고한다.
   마켓번호는 그룹명(예 `용쌤4-1` → `4-1`)에서 뽑는다. 판매 후 `구매_가공완료` 같은 그룹으로 옮겨져 번호가 없으면 `~/.aside/u/0/detail-pages/*/<내부ID>/` 기존 폴더의 마켓번호를 쓰고, 그것도 없으면 사용자에게 묻는다. 마켓명 매핑은 Aside 가 `smartstore-market-number-map.md` 에서 직접 찾는다.
2. **지시서 작성** — `~/.aside/u/0/detail-pages/_brief/작업지시서-<판매자상품코드>-<YYYY-MM-DD>.md` 에 짧게 쓴다.
   ```
   계정 스킬 smartstore-detail-page(2026-10-23-opus-v1)를 그대로 따른다.
   - 판매자상품코드 <코드>, 불사자 내부 ID <ID>, 마켓 <번호>, 상품명 <이름>
   - 저장: ~/.aside/u/0/detail-pages/<마켓>/<ID>/<YYYY-MM-DD>_opus/
   - 원본: 같은 상품 폴더에 originals/ 가 있으면 재사용, 없으면 불사자에서 내려받아 originals/ 에 저장
   - 스타일 <C>, 보호 표시 <넣음/없음>
   - verification.json 에 모델명 <모델> 기록
   - 불사자 저장·교체·업로드 금지
   ```
3. **실행(백그라운드 + 감시 필수)** — 감시 없이 띄우지 않는다.
   ```bash
   ~/.local/bin/aside exec -m claude-code/claude-opus-5-5 --effort high \
     "~/.aside/u/0/detail-pages/_brief/작업지시서-<코드>-<날짜>.md 를 읽고 그대로 작업해줘" \
     > <scratchpad>/aside-<코드>.log 2>&1
   ```
   `run_in_background: true` 로 띄우고, 동시에 Monitor 로 `<저장폴더>/report.md` 가 생길 때까지 기다린다(보통 25~30분, 상한 60분).
   - CLI 가 "Replay buffer no longer contains requested cursor" 로 먼저 끊겨도 **앱 세션은 계속 돈다.** 재실행하지 말고 report.md 를 계속 기다린다.
   - 세션을 멈출 API 는 없다. 멈춰야 하면 사용자에게 Aside 앱에서 정지 버튼을 눌러 달라고 한다.
4. **결과 확인** — report.md 가 생기면 직접 확인한다.
   - `01.png…` 개수와 `clean/` 개수가 같은지, 폭이 전부 860px 인지(`sips -g pixelWidth`)
   - `verification.json`: 컷 활용률 70% 이상, 배경 교체 오차 0, 펜체 로드 성공, 워터마크 마켓명
   - `preview.jpg` 를 Read 로 열어 톤·워터마크·경고 박스를 눈으로 본다
   - 하나라도 어긋나면 같은 세션에 `aside exec --session <id> "<고칠 점>"` 으로 수정 지시(새 세션을 또 띄우지 않는다)
5. **보고** — 판매자상품코드로 보고한다.
   - 장수, 컷 활용률, 걸린 시간, 결과 폴더 경로, 원본에서 뺀 정보 요약, 아쉬운 점
   - **불사자 미반영**을 분명히 적는다. 반영은 사용자가 따로 승인하면 bulsaja-detail-remix 흐름(860px 세로 이어붙여 교체)으로 한다.

## 하지 않을 것
- 불사자 상품 저장·상세 교체·마켓 업로드(승인 전)
- Aside 를 거치지 않고 Claude Code 가 직접 PNG 를 만드는 것(규칙·폰트·검수가 Aside 스킬에 묶여 있다)
- 레퍼런스 보드 이미지를 결과물·배포물에 넣는 것(저작권)
- 네이버 로그인
