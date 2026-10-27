---
name: detail-page-opus
description: 판매자상품코드를 받아 Aside 에서 Claude Opus 5.5 로 고퀄 스마트스토어 상세페이지(860px 낱장 PNG, 아이보리+진갈색 C 세일즈형, 원본 컷 70% 이상 활용, 상표등록번호·무단복제 경고·마켓명 펜체 워터마크 포함)를 만들고, 검수를 통과하면 불사자 상세페이지까지 교체 반영한다(교체 전 백업). 불사자 크레딧은 쓰지 않는다. "오퍼스 상세페이지", "오퍼스로 상세 만들어줘", "고퀄 상세페이지", "직접 상세페이지 만들어줘", "아사이드 상세페이지", "워터마크 넣은 상세페이지" 등을 언급하며 상품코드를 주면 자동 실행. "반영 없이"라고 하면 파일만 만든다. ※ 불사자 내부 AI 상세페이지 배치(크레딧 소모)는 bulsaja-detail-page.
---

# detail-page-opus — Aside + Opus 5.5 상세페이지

제작 규칙 정본은 Aside 계정 스킬 `~/.aside/u/0/skills/user/smartstore-detail-page/SKILL.md`(기준 `2026-10-23-opus-v1`)에 있다.
이 스킬은 **디스패처**다. 규칙을 여기 복제하지 말고, 바꿀 일이 있으면 Aside 스킬을 고친다.

## 입력
- 판매자상품코드(필수, 여러 개면 한 개씩 순서대로)
- 선택: 스타일(A/B/C, 기본 C) · "보호 표시 없이"(촬영용 — 이때는 반영하지 않는다) · "반영 없이"(파일만) · 모델 변경(기본 `claude-code/claude-opus-5-5`)

## 흐름

1. **상품 확인** — `mcp__bulsaja__bulsaja_product_find_by_code` 로 내부 ID·마켓그룹·상품명을 찾는다. 0건·다건이면 멈추고 보고한다.
   마켓번호는 그룹명(예 `용쌤4-1` → `4-1`)에서 뽑는다. 판매 후 `구매_가공완료` 같은 그룹으로 옮겨져 번호가 없으면 `~/.aside/u/0/detail-pages/*/<내부ID>/` 기존 폴더의 마켓번호를 쓰고, 그것도 없으면 `bulsaja_product_workdata(full)` 의 업로드 마켓그룹 ID(`uploadSelectedMarketGroupId`) → `bulsaja_market_groups(groupId)` 그룹명(예 `5번_용쌤25-2`)에서 뽑는다. 그래도 없으면 사용자에게 묻는다. 마켓명 매핑은 Aside 가 `smartstore-market-number-map.md` 에서 직접 찾는다.
2. **지시서 작성** — `~/.aside/u/0/detail-pages/_brief/작업지시서-<판매자상품코드>-<YYYY-MM-DD>.md` 에 짧게 쓴다.
   ```
   계정 스킬 smartstore-detail-page(2026-10-23-opus-v1)를 그대로 따른다.
   - 판매자상품코드 <코드>, 불사자 내부 ID <ID>, 마켓 <번호>, 상품명 <이름>
   - 저장: ~/.aside/u/0/detail-pages/<마켓>/<ID>/<YYYY-MM-DD>_opus/
   - 원본: 같은 상품 폴더에 originals/ 가 있으면 재사용, 없으면 불사자에서 내려받아 originals/ 에 저장
   - 스타일 <C>, 보호 표시 <넣음/없음>
   - verification.json 에 모델명 <모델> 기록
   - 불사자 저장·교체·업로드 금지(반영은 Claude Code 가 6단계에서 한다)
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
5. **불사자 반영** — 4단계 검수를 모두 통과했을 때만. "반영 없이"·"보호 표시 없이"면 건너뛴다.
   반영 스크립트는 `bulsaja-detail-remix/scripts/run.py` 를 재사용한다(860px 세로 이어붙이기, 2300px 조각, 8MB 클램프, 업로드→교체).
   ```bash
   cd .claude/skills/bulsaja-detail-remix/scripts
   D=<저장폴더>; A=$D/_apply; mkdir -p $A
   rm -f $A/final.zip && (cd $D && zip -q $A/final.zip [0-9][0-9].png)   # 최종본만(clean/ 제외), 반영 직전에 새로 묶는다
   PY=../../../../.venv/bin/python3
   PYTHONIOENCODING=utf-8 $PY run.py --code <코드> --zip $A/final.zip --out $A --dry-run   # ① 미리보기
   PYTHONIOENCODING=utf-8 $PY run.py --code <코드> --zip $A/final.zip --out $A             # ② 실제 반영
   ```
   - ① dry-run 에서 조각 수·폭 860·높이 2300 이하를 확인하고, 이상 없으면 묻지 않고 ② 를 돌린다(사용자가 스킬 호출로 반영까지 위임, 2026-10-27).
   - ② 는 교체 전 현재 상세를 `$A/before_apply.html` 에 백업(workdata full 의 상세 HTML, img 0개면 실패 처리)하고, 백업이 실패하면 반영하지 않고 멈춘다.
   - 반영 후 `bulsaja_product_workdata(full)` 로 상세 HTML 의 `<img>` 개수가 조각 수와 같은지 다시 확인한다.
   - 이미 상세가 반영된 상품을 다시 돌리면 그대로 덮어쓴다. 되돌릴 때는 `before_apply.html` 을 `bulsaja_detail_apply` 로 다시 넣는다.
   - 마켓(스마트스토어) 업데이트 전송은 하지 않는다. 불사자 상품 상세만 바꾼다.
6. **보고** — 판매자상품코드로 보고한다.
   - 장수, 컷 활용률, 걸린 시간, 결과 폴더 경로, 원본에서 뺀 정보 요약, 아쉬운 점
   - 불사자 반영 여부(조각 수, 백업 경로). 반영 안 했으면 이유.
   - 마켓 전송은 안 했다는 것 — 스마트스토어에 내보내려면 불사자에서 마켓 업데이트를 따로 해야 한다.

## 배치 모드 (밤 배치 · 2026-10-27~)
"고퀄 상세 배치", "상세 배치 돌려줘", "효자상품 상세 몰아서" 등이면 이 흐름. 첫 회는 5건으로 시간·토큰을 실측하고 늘린다.
```bash
cd .claude/skills/detail-page-opus/scripts; PY=../../../../.venv/bin/python3
PYTHONIOENCODING=utf-8 $PY -u targets.py --limit 5            # 대상 뽑기(읽기 전용) → batches/<오늘>/targets.json
caffeinate -i env PYTHONIOENCODING=utf-8 $PY -u batch.py --batch <오늘> > <배치폴더>/batch.log 2>&1   # 백그라운드 + 감시 필수
```
- **대상**: 최신 광고 주간보고 ⑦c·⑦d 중 상세 미가공 + 불사자 히트. 순서 = 판매(잠금) → 구매수 → 클릭수. 실시간 재조회로 이미 가공된 것(AI 생성 표시 · `mcp-assets` 업로드 흔적 · 로컬 `_opus` 결과)과 마켓번호 불일치는 뺀다.
- **상품마다**: 지시서 → Aside 제작(로그 5분 무응답이면 1회 재시작, 60분 상한) → 자동 검수(장수·860px·verification) → 보고서에 "확인 필요" 절이 있으면 **보류**(반영 안 함) → 반영(dry-run→실제→재조회) → 스마트스토어 수정 전송.
- 결과: 배치 폴더(`~/python_work/data/detail-opus/batches/<날짜>/`)의 `state.json`(재실행 시 이어서) · `summary.md`(아침 요약: 완료/보류/실패·시간·토큰). 보류 건은 사람이 보고 판단한 뒤 단건 흐름으로 처리한다.
- 아침 보고 때 Claude 가 완료 건 `preview.jpg` 를 눈으로 훑는다(배치는 자동 검수만 한다).
- 토큰은 Aside `state.db` 의 회차 시간대 합(API 환산). 다른 Aside 작업이 겹치면 과대 계상된다.
- 불사자 429: 호출마다 2초 간격, 429 면 60/120/240초 쉬고 재시도.

## 하지 않을 것
- 검수 미통과 상태로 불사자 반영
- 백업 없이 상세 교체
- 단건 흐름에서 지시 없는 마켓 전송(배치 모드는 위임받아 전송한다)
- Aside 를 거치지 않고 Claude Code 가 직접 PNG 를 만드는 것(규칙·폰트·검수가 Aside 스킬에 묶여 있다)
- 레퍼런스 보드 이미지를 결과물·배포물에 넣는 것(저작권)
- 네이버 로그인
