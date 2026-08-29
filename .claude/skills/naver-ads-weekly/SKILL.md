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

`apply --sheet <시트ID>` 는 `①노출0`~`⑤효자확정` 5개 탭에 회차·계정을 앞에 붙여 append 한다
(⑥ 삭제대상과 총괄은 시트 탭이 아니라 `report.md` 에만 실린다). **시트 실제 쓰기는 아직
검증되지 않았다.** 실패해도 `prep`·`run`·`apply` 의 판정·보고서 산출 자체는 죽지 않는다
(시트 실패는 계정·규칙별로 로그만 남기고 나머지를 계속 시도한다).

**2026-08-30 확인 — 현재는 gws 인증이 아니라 요청 형식 문제로 100% 실패한다.**
`gws auth status` 로 보면 인증은 살아 있고(`spreadsheets` 스코프 포함) 정상 호출도 되는데,
`sheets_out._gws()` 가 `values.append` 의 본문(`values`)을 `--json` 이 아니라 `--params` 안에
`"body"` 키로 넣고 있다 — 실제 `gws sheets spreadsheets values append --help` 는 쿼리/경로
값은 `--params`, 요청 본문은 `--json` 으로 분리해서 받는다. 그 결과 매번
`Invalid JSON payload ... Unknown name "body"` 로 죽는다(재현: `sheets_out.write_sheet` 를
아무 시트ID로나 호출해봐도 동일). **코드 수정이 필요하다** — 이 태스크(문서화)에서는 고치지
않았다. gws 인증이 실제로 끊긴 것처럼 보이면(403·invalid_grant 류) 아래로 재인증한다:

```bash
gws auth login
# 재로그인해도 안 풀리면 캐시가 낡은 것 — 이것부터 지운다
rm -f ~/.config/gws/token_cache.json
```
`--sheet` 를 생략하면 시트를 아예 건드리지 않고 `report.md` 만 만든다.

## 테스트

```bash
for t in nvad reports ads_rules ledger bids; do
  .venv/bin/python3 .claude/skills/naver-ads-weekly/scripts/test_$t.py
done
```

전부 네트워크 없이 돈다.

## 알려진 미해결

**`AD_ABNORMAL_INTERLOCK`(연동 비정상)으로 소재가 계속 자동 정지된다.** 2026-08-29~30 에
4계정 합산 **7,340건**(cy728 38 · cy7728 5,024 · ownway1 494 · pogeunae 1,784)을 이미
삭제했지만 원인은 규명되지 않았고 지금도 발생 중이다 — 새 계정을 붙일 때마다 수백~수천
건이 나왔다. `prune` 이 매주 신규 발생 건수를 보고한다 — **급증하면 삭제보다 원인 규명이
먼저다.** 원인 규명 자체는 이 스킬의 범위 밖이다.

**`bids --commit`·`prune --commit` 은 이 스킬의 정식 진입점으로는 아직 한 번도 실행되지
않았다** (위 7,340건은 스킬 완성 전 검증 과정에서 별도로 실행됐다). 첫 정식 실행은 용팀장
승인 후다.
