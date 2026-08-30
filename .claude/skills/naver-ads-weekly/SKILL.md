---
name: naver-ads-weekly
description: 네이버 검색광고 여러 계정을 주 1회 훑어 노출0·저CTR·구매0·효자상품을 분류하고 총괄 보고서를 만든다. 입찰가 인상과 꺼진 소재 삭제는 승인 후 별도 명령으로 실행한다. "광고 주간보고", "광고 성과 정리", "노출 안 되는 상품", "입찰가 올려줘", "꺼진 광고 정리", "광고 리포트", "썸네일 바꿀 상품 뽑아줘" 등을 언급하면 자동 실행.
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
$P $S run                       # 6개 규칙 판정 → result.json
$P $S apply --sheet <시트ID>     # 시트 원장 append + report.md (--sheet 생략하면 마크다운만)

# 여기서 용팀장이 ①번 리스트를 확인한 뒤
$P $S bids                      # dry-run — 뭘 올릴지만 보여준다
$P $S bids --commit             # 실제 인상
$P $S prune --commit            # 꺼진 소재 삭제 (백업 선행)

# 되돌려야 하면(잘못 인상했을 때) — before_bids_<계정>.json 백업으로 원본을 복원한다
$P $S bids --revert             # dry-run — 무엇을 되돌릴지만 보여준다
$P $S bids --revert --commit    # 실제로 되돌린다
```

**`prep`·`run`·`apply` 는 광고 API 에 아무것도 쓰지 않는다.** `bids`·`prune` 만 쓰고, 둘 다
`--commit` 없이는 dry-run 이다. 모든 서브커맨드는 `--run-dir <이름>`(기본: 오늘 날짜) ·
`--account <alias...>`(기본: 전 계정)를 받는다.

## 6개 규칙

| # | 조건 | 기간 | 결과 |
|---|---|---|---|
| ① | 노출 0 (게재중 · 검수대기 제외) | 7일 | 입찰 +10원 (`bids`) |
| ② | 노출 100+ & CTR<1% | 30일 | 썸네일 교체 리스트 (노출 많은 순 상위 20건) |
| ③ | 클릭 20+ & 구매완료 0 | 30일 | 원인분석 리스트 |
| ④ | 노출 100+ & CTR≥2% | 30일 | 효자 후보 |
| ⑤ | 구매완료 발생 | 30일 | 효자 확정 |
| ⑥ | `enable=false`(꺼진 소재 전체를 보고) | — | 그중 `AD_ABNORMAL_INTERLOCK` 만 삭제 (`prune`, 백업 선행) |

전문·기간/하한 근거·가드레일 7종: [`references/규칙-판정기준.md`](references/규칙-판정기준.md)

## 반드시 지킬 것 3가지

1. **`/stats` 의 `convAmt`·`ccnt` 를 매출로 쓰지 않는다** — 장바구니 포함이다. 구매완료는 `AD_CONVERSION` 리포트의 `purchase` 유형만.
2. **`salesAmt` 는 광고비다** — 매출이 아니다.
3. **그룹입찰 상품의 인상 출발점은 그룹 기본입찰가다** — 잠자던 `bidAmt` 를 쓰면 올리려다 내린다.

보고서(`report.md`·시트)에는 **구매완료 기준 숫자만** 싣는다(2026-08-28 용팀장 지시).
`장바구니`·`총전환`·`add_to_cart` 는 보고서에 나오면 안 된다.

## 자격증명

`~/.eroom/naver-ads.json` (권한 600, git 밖). 현재 4계정:
`cy728`(4158478) · `cy7728`(3415467) · `ownway1`(3406540) · `pogeunae`(3307029).

```json
{"accounts":[{"alias":"cy728","customer_id":"...","api_key":"...","secret_key":"..."}]}
```

계정마다 광고플랫폼 → 도구 → **API 사용 관리** 에서 3종(고객ID·액세스라이선스·비밀키)을
발급받아 배열에 블록을 추가한다. 새 계정을 붙일 때마다 검수대기·연동끊김 비중이 계정마다
크게 달랐다(예: ownway1 검수대기 988건) — 붙인 직후엔 `prep && run` 결과를 한 번 훑어라.

## 구글시트 기록

`apply --sheet <시트ID>` 는 `sheets_out.write_sheet` 가 `eroomlib.gsheets.append_rows`/
`ensure_tab`(429 백오프 재시도 포함, 다른 스킬 두 개도 쓰는 검증된 헬퍼)을 불러
`①노출0`~`⑤효자확정` 5개 탭에 회차·계정을 앞에 붙여 append 한다(⑥ 삭제대상과 총괄은
시트 탭이 아니라 `report.md` 에만 실린다).

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
for t in nvad reports ads_rules ledger bids prune; do
  .venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_$t.py
done
```

전부 네트워크 없이 돈다.

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
