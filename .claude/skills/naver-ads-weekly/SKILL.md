---
name: naver-ads-weekly
description: 네이버 검색광고 여러 계정을 주 1회 훑어 ⑦ 체계로 분류한다 — 노출0(입찰+10), 전 계정 노출 50+ 소재의 CTR 하위 10%(썸네일 변형)·상위 10% 중 상세 미가공(상세 꾸미기), 30일 클릭 20+ 상품의 상세·옵션명 정비 점검, 구매0·효자·꺼진 소재. ⑦c/⑦d 는 판매자상품코드로 불사자와 잇는다. 매주 월요일 07:00 무인 실행(입찰 인상·꺼진 소재 삭제 포함). "광고 주간보고", "광고 성과 정리", "노출 안 되는 상품", "입찰가 올려줘", "꺼진 광고 정리", "광고 리포트", "썸네일 바꿀 상품 뽑아줘" 등을 언급하면 자동 실행.
allowed-tools:
  - Bash
  - Read
---

# 네이버 광고 주간 관리

> 규칙 전문·가드레일·전환 함정의 실측 근거는 전부
> [`references/규칙-판정기준.md`](references/규칙-판정기준.md) 한 곳에 있다. 여기는 요약+링크다.

## 왜 필요한가

여러 광고계정을 눈으로 훑으면 **구매완료가 아니라 장바구니를 매출로 착각한다.**
`/stats` 의 전환값(`convAmt`·`ccnt`)은 장바구니 담기가 섞여 있어 4계정 합산 실측에서
14배 넘게 부풀어 보였다(총전환 기준 ROAS 3,844% vs 구매완료 기준 275%).

## 흐름

```bash
P=.venv/bin/python3
S=.claude/skills/naver-ads-weekly/scripts/run_ads.py

$P $S prep                      # 전 계정 수집 (쓰기 0)
$P $S run                       # 판정 → result.json (①③⑤⑥ + ⑦b/⑦c 전 계정 1풀 + ⑦d)
$P $S enrich                    # ⑦c/⑦d 후보만 커머스API·불사자 조회 → 판매자상품코드·상세/옵션 상태 (읽기 전용)
$P $S apply --sheet <시트ID>     # 시트 원장 append + report.md (--sheet 생략하면 마크다운만)

# 여기서 용팀장이 ①번 리스트를 확인한 뒤
$P $S bids                      # dry-run — 뭘 올릴지만 보여준다
$P $S bids --commit             # 실제 인상
$P $S prune --commit            # 꺼진 소재 삭제 (백업 선행)

# 되돌려야 하면(잘못 인상했을 때) — before_bids_<계정>.json 백업으로 원본을 복원한다
$P $S bids --revert             # dry-run — 무엇을 되돌릴지만 보여준다
$P $S bids --revert --commit    # 실제로 되돌린다
```

**`prep`·`run`·`enrich`·`apply` 는 광고 API·불사자에 아무것도 쓰지 않는다.** `bids`·`prune` 만 쓰고, 둘 다
`--commit` 없이는 dry-run 이다. 모든 서브커맨드는 `--run-dir <이름>`(기본: 오늘 날짜) ·
`--account <alias...>`(기본: 전 계정)를 받는다.

## 규칙 (⑦ 체계 — 2026-10-16 용팀장 확정)

| 규칙 | 조건 | 결과 |
|---|---|---|
| ⑦a (=①) | 7일 노출 0 (게재중 · 검수대기 제외) | 입찰 +10원 — `bids`. result.json 키 `①노출0` 이름 유지 |
| ⑦b (② 대체) | 7일. 모집단 = 7일 노출 ≥ 50 인 게재중 소재(**전 계정 합산 1풀**). CTR 오름차순·동률은 노출 많은 순, 개수 = ceil(모집단×0.10) | 썸네일 변형 리스트 |
| ⑦c (④ 대체) | 같은 모집단 CTR 상위 10%(내림차순·동률 노출 많은 순) → 그중 상세 미가공(중국어원본/단순번역)만 | 상세 꾸미기 리스트 |
| ⑦d (신규) | 30일 클릭 ≥ 20 전체(구매 무관) | 상세+옵션명 정비 점검 — 상세 미가공·옵션명 미정리 표시, 둘 다 OK 면 `정비완료` |
| ③ | 30일 클릭 20+ & 구매완료 0 | 원인분석 리스트 (그대로) |
| ⑤ | 30일 구매완료 발생 | 효자 확정 (그대로) |
| ⑥ | `enable=false`(꺼진 소재 전체를 보고) | 그중 `AD_ABNORMAL_INTERLOCK` 만 삭제 (`prune`, 백업 선행) (그대로) |

50·10%·20 은 `ads_rules.py` 상수 `POP_IMP_MIN`·`CTR_TAIL_PCT`·`MAINT_CLICK_MIN` 한 곳에만 있다(2~3주 뒤 조정 예정).
②④ 는 result.json 에 계속 남지만(웹앱이 읽는다) 시트·보고서에는 안 쓴다.

**⑦c/⑦d 불사자 조인** — 스토어상품ID(채널상품번호)+광고그룹 `NN-N` → 그 마켓 커머스API 로 판매자상품코드 →
불사자 `find_by_code` 정확히 1건 → 스스번호 일치면 히트. **상품명 매칭은 하지 않는다.** 못 이은 행은
`미매칭: <사유>`(번호추출실패/키없음/커머스조회실패/판매자코드없음/불사자미매칭/다건/번호불일치/조회실패)로 남는다.
상세 판정은 `webapp/state.상세상태`, 옵션은 그룹 현황판 `옵션` 열(기록 없으면 `판정 불가`). 캐시는 `run-dir/bulsaja_cache/`.
불사자 계정이 `부킹` 이 아니면 조회 0건·종료코드 3.

전문·기간/하한 근거·가드레일 7종: [`references/규칙-판정기준.md`](references/규칙-판정기준.md)

## 반드시 지킬 것 3가지

1. **`/stats` 의 `convAmt`·`ccnt` 를 매출로 쓰지 않는다** — 장바구니 포함이다. 구매완료는 `AD_CONVERSION` 리포트의 `purchase` 유형만.
2. **`salesAmt` 는 광고비다** — 매출이 아니다.
3. **그룹입찰 상품의 인상 출발점은 그룹 기본입찰가다** — 잠자던 `bidAmt` 를 쓰면 올리려다 내린다.

보고서(`report.md`·시트)에는 **구매완료 기준 숫자만** 싣는다(2026-08-28 용팀장 지시).
`장바구니`·`총전환`·`add_to_cart` 는 보고서에 나오면 안 된다.

## 자격증명

`~/.eroom/naver-ads.json` (권한 600, git 밖). 현재 8계정:
`cy728`(4158478) · `cy7728`(3415467) · `ownway1`(3406540) · `pogeunae`(3307029) ·
`dldmswl1986`(3399878) · `milky-way1992`(4377264) · `level_up_ad`(4141540) ·
`minimoving`(4514484, 스토어 '소형이동식오피스' 전용 — 2026-10-12 추가).

> 쇼핑 소재 등록은 API 로 못 한다 — `referenceKey` 에 네이버쇼핑 상품번호(nvMid)가 필요한데
> 스마트스토어 상품번호→nvMid 변환 경로가 광고 API·커머스API 어디에도 없다(2026-10-12 실측).
> 사람이 광고 UI 에서 넣고(1000개 한 번에는 에러, 500개씩), 넣은 뒤 중복·누락 검사만 API 로 한다.

```json
{"accounts":[{"alias":"cy728","customer_id":"...","api_key":"...","secret_key":"..."}]}
```

계정마다 광고플랫폼 → 도구 → **API 사용 관리** 에서 3종(고객ID·액세스라이선스·비밀키)을
발급받아 배열에 블록을 추가한다. 새 계정을 붙일 때마다 검수대기·연동끊김 비중이 계정마다
크게 달랐다(예: ownway1 검수대기 988건) — 붙인 직후엔 `prep && run` 결과를 한 번 훑어라.

## 구글시트 기록

`apply --sheet <시트ID>` 는 `sheets_out.write_sheet` 가 `eroomlib.gsheets.append_rows`/
`ensure_tab`(429 백오프 재시도 포함, 다른 스킬 두 개도 쓰는 검증된 헬퍼)을 불러
`①노출0`·`③원인분석`·`⑤효자확정`·`⑦b썸네일변형`·`⑦c상세꾸미기`·`⑦d정비점검` 6개 탭에 회차·계정을
앞에 붙여 append 한다(⑥ 삭제대상과 총괄은 시트 탭이 아니라 `report.md` 에만 실린다).
**`②썸네일교체`·`④효자후보` 탭은 2026-10-16 부로 쓰기를 멈췄다 — 과거 행은 보존한다.**
⑦c·⑦d 탭의 사람이 볼 표기는 판매자상품코드다(⑦b 는 불사자를 조회하지 않아 광고그룹·스토어상품ID).

**2026-08-30 확인 — 실제 시트 쓰기가 검증됐다.** 시트ID
`1-oSQepeUGbdmRfSizJHUIjgHu-UYxMtyS504mzDeJKI` 에 5개 탭 합계
2,242/198/78/138/38행이 기록됐다. (과거 이 문서가 언급하던 `_gws()` 헬퍼는 제거되고
`eroomlib.gsheets` 로 교체됐다 — subprocess 로 `gws` 를 직접 부르지 않는다.)

한 탭(규칙)이 실패해도 **판정(`result.json`)과 마크다운 보고서는 죽지 않는다** — `write_sheet`
가 규칙마다 try/except 로 감싸기 때문이다. 다만 실패 단위는 **규칙**이지 계정이 아니다:
`write_sheet` 는 규칙마다 전 계정의 행을 한 번에 합쳐 append 하므로, 한 규칙이 실패하면
그 규칙의 **모든 계정 행**이 함께 빠진다 — "한 탭이 실패해도 나머지 계정은 계속 기록한다"는
서술은 틀렸다.

gws 인증이 끊긴 것처럼 보이면(403·invalid_grant 류) 아래로 재인증한다:

```bash
gws auth login
# 재로그인해도 안 풀리면 캐시가 낡은 것 — 이것부터 지운다
rm -f ~/.config/gws/token_cache.json
```
`--sheet` 를 생략하면 시트를 아예 건드리지 않고 `report.md` 만 만든다.

## 테스트

```bash
for t in nvad reports ads_rules ledger bids prune bulsaja_join weekly_monday; do
  .venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_$t.py
done
```

전부 네트워크 없이 돈다.

## 월요일 자동 실행 (launchd, 매주 월 07:00 · `caffeinate -i`)

`scripts/weekly_monday.py` 가 같은 `--run-dir`(기본: 오늘 날짜)로 아래를 순서대로 돌린다. 첫 실행 **2026-10-19(월)**.

```
prep → run → enrich → apply --sheet <원장> → bids --commit → prune --commit → 업무판 1행
```

- **실패 정책**: prep/run 실패 → 이후 전부 생략. **bids/prune 은 prep·run 성공에만 의존한다** —
  enrich·apply·업무판 실패는 기록만 하고 계속 간다(불사자·시트 장애가 입찰 인상을 막지 않는다). bids 실패도 prune 은 돈다.
- **원장 시트**: `--sheet` > `workspace.toml sheets.naver_ads` > 상수 `1-oSQepeUGbdmRfSizJHUIjgHu-UYxMtyS504mzDeJKI`.
- **산출물**: run-dir 에 `weekly.log`(단계별 출력) · `bids_commit.json` · `prune_commit.json`(백업 태그 `weekly-YYYYMMDD`) ·
  `weekly_result.json`(steps = {단계: 종료코드|"skipped"}, memo, board.status).
- **업무판**: `sheets.work_board` 의 `오늘` 탭 1행 — `[번호, 날짜, ✓(전 단계 성공일 때만), "⑦ 광고 주간 <회차>", ⑦, Claude, 자동, 메모, ""]`.
  메모: `입찰+10 N · 썸네일변형 b · 상세꾸미기 c · 정비점검 d(미정비 x) · 꺼진소재 삭제 p`, 실패가 있으면 앞에 `실패: <단계>`.
  업무판 기록이 실패해도 본 작업은 유지된다(`board.status=failed`).
- **되돌리기**: 입찰 인상은 `run_ads.py bids --revert --commit --run-dir <회차>`. 꺼진 소재 삭제는 prune 백업 참조.
- **점검용**: `weekly_monday.py --dry-run` — bids/prune 을 `--commit` 없이 돌리고 업무판 할 일 앞에 `[dry-run] `.

설치 (사람이 한 번 — 템플릿은 load 되어 있지 않다):
```bash
WS="$(pwd)"   # 워크스페이스 루트에서 실행
mkdir -p "$HOME/python_work/data/naver-ads/logs"
sed -e "s#__WORKSPACE__#$WS#g" -e "s#__HOME__#$HOME#g" \
  .claude/skills/naver-ads-weekly/launchd/com.eroom.ads-weekly.plist > "$HOME/Library/LaunchAgents/com.eroom.ads-weekly.plist"
plutil -lint "$HOME/Library/LaunchAgents/com.eroom.ads-weekly.plist"
launchctl bootstrap gui/$(id -u) "$HOME/Library/LaunchAgents/com.eroom.ads-weekly.plist"
```
해제: `launchctl bootout gui/$(id -u)/com.eroom.ads-weekly`
로그: `~/python_work/data/naver-ads/logs/launchd.{out,err}.log` · 상태: `launchctl print gui/$(id -u)/com.eroom.ads-weekly`

## 연동끊김(AD_ABNORMAL_INTERLOCK)의 정체 — 물갈이 부산물 (2026-08-30 용팀장 확인)

**미해결 미스터리가 아니라 운영 사이클의 정상 부산물이다.**

용팀장은 전시 최신성을 위해 마켓그룹마다 **20일 주기로 물갈이**(삭제 → 재업로드)를 한다
(`bulsaja-mulgari-delete` · `bulsaja-mulgari-upload` 스킬이 그 일정을 관리한다).

```
물갈이 삭제   → 스마트스토어 상품이 사라짐 → 광고 소재가 연동을 잃고 AD_ABNORMAL_INTERLOCK 으로 자동 정지
물갈이 업로드 → 새 상품ID로 재등록        → 기존 광고 소재는 죽은 채 남고, 광고에 **새로 소재를 추가**해야 한다
```

그래서 계정을 새로 붙일 때마다 수백~수천 건이 나온다(누적 7,340건 삭제).
**급증해도 이상 신호가 아니다** — 물갈이를 크게 돌린 직후일 뿐이다.
`prune` 은 그 사이클의 뒤처리를 자동화한 것이고, 앞으로도 계속 나오는 게 정상이다.

> 남은 수작업: 물갈이 재업로드 뒤 **광고에 소재를 새로 넣는 일**은 아직 사람이 한다
> (네이버 광고 UI 에서 미투입 상품을 전체 선택). 광고 API 에 "광고 미투입 상품 목록" 을
> 주는 엔드포인트가 없어 자동화가 막혀 있다 — 2026-08-30 실측으로 확인.

## 예약 실행 (2026-10-17 변경)

> **예약 실행은 `.claude/lib/eroom_scheduler.py`(launchd `com.eroom.scheduler`, 1분 틱) 한 곳에서 한다.** 이 맥북에선 새로 등록한 StartCalendarInterval 이 안 터져서(2026-10-17 실측) 개별 plist 를 없앴다. 시각을 바꾸려면 그 파일의 `JOBS` 표를 고친다. 로그: `~/python_work/data/scheduler/logs/<작업>.log`
