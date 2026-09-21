# -*- coding: utf-8 -*-
"""불사자 마켓그룹 단위 인덱스 구축 — `스마트스토어 채널상품번호 → productId`.

이 인덱스가 없으면 광고 판정 행을 불사자 상품에 **이을 수가 없다**. 채널상품번호는
상품 목록 조회에 안 나오고(`uploadedSuccessUrl` 은 상세 응답에만 있다), 상품명 매칭은
실측 67% 라 조용히 틀린 상품을 집는다(D-03). 그래서 그룹을 통째로 한 번 훑어 적어 둔다.

비용 실측 (2026-09-21, 단일 세션 3.7건/초)
  · 대상 36그룹 / 47,105 상품 ≈ **3시간 32분**
  · 크레딧 **0** — 읽기 전용 조회만 한다. 상품을 고치지도, 만들지도 않는다
  · 중단해도 안전하다 (아래 체크포인트 규약)

체크포인트 규약 — 재개 단위는 **이미 처리한 productId 집합**이다
  페이지 번호로 재개하지 않는다. 목록 조회의 정렬 기준이 문서화돼 있지 않고, 실측상
  `mallProductId` 의 단조성이 61.9%였다. 호출 사이에 물갈이 삭제·신규 수집이 끼면 페이지
  경계가 밀려서 **안 훑은 상품이 훑은 것으로 넘어간다**(RESEARCH §Pitfall 6).
  그래서 매 그룹 시작 시 `ss_index` 에서 그 그룹의 `product_id` 를 읽어 집합으로 만들고,
  거기 없는 것만 조회한다. 한 건 조회할 때마다 곧바로 커밋한다 — 28,000건짜리 그룹이 있어서
  메모리에 쌓으면 중단 시 통째로 날아간다.

동시 실행 — 이 스크립트는 자기 몫의 간격만 지킨다
  같은 인덱스 잡이 둘 동시에 돌면 각자 초당 4회를 지켜도 합산 8회/초라 서버 정책
  (`RateLimit-Policy: 240;w=60`)을 넘고 429 가 쏟아진다. 그걸 막는 것은 웹앱 쪽
  `jobs.SINGLETON_KINDS` 가드다. 여기서 또 막지 않는다 — 같은 규칙이 두 곳이면
  어느 쪽이 진짜 가드인지 모르게 된다.

스키마를 여기서 만들지 않는다
  `ss_index` 의 DDL 정본은 `webapp/jobs.py` **하나**다. 여기에 테이블 생성문을 두면
  스키마가 두 벌이 되고, 컬럼이 조용히 갈라진다. 테이블이 없으면 만들지 말고 죽는다(exit 4).

향후 — 커머스API 로 가면 같은 일이 **30초**다
  `channelProductNo → sellerManagementCode` → `find_by_code` 배치면 500배 빠르다.
  막는 것은 오직 자격증명이고(스토어당 앱 1개 상한 × 몰 50개), v1 범위 밖이다.
  숫자 비교표는 `webapp/bulsaja_index.py` 의 docstring 에 있다 — 인덱스 비용이 다시
  아플 때 그걸 보면 같은 조사를 처음부터 하지 않아도 된다.

종료코드
  0  정상
  2  훑을 대상이 없다 (`--groups` 파일이 없거나 배열이 비었다). **빈 목록은 전량이 아니다**
  3  계정 불일치 (ENG-08). SQLite 에 한 글자도 쓰기 전에 죽는다
  4  `ss_index` 테이블이 없다. 웹앱을 한 번 띄워 스키마를 만들어라

사용:
  python3 ss_index_build.py --db <webapp.db> --groups <groups.json> --out <summary.json>
        --profile-out <profile.json> --expect-nick <닉네임>
        --min-interval 0.26 --retry-after 21 --batch-size 50 [--limit N]
"""
import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 불사자 MCP 클라이언트는 카테고리 교정 스킬의 것을 재사용한다.
# **경로를 박지 않는다** — 이 파일 위치에서 스킬 루트를 거슬러 올라가 찾는다.
# (같은 관용구: product-name/scripts/run_names.py:40-46 · detail_batch.py:47-52)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", ".."))
SKILL_SCRIPTS = os.path.join(SKILLS_DIR, "bulsaja-category-fix", "scripts")
if SKILL_SCRIPTS not in sys.path:
    sys.path.insert(0, SKILL_SCRIPTS)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from bulsaja_mcp import BulsajaMCP  # noqa: E402
from bulsaja_rate import 안전호출, 호출간격  # noqa: E402


# ── 공용 유틸 ───────────────────────────────────────────────────────────────

def 말하기(줄):
    """진행 출력. **`flush=True` 가 협상 불가다.**

    3시간짜리 잡의 로그가 0바이트로 머물면 사람이 "멈췄나" 를 판단할 수 없다.
    잡으로 띄울 때는 `PYTHONUNBUFFERED` 가 주입되지만(`webapp/jobs.py`), 터미널에서
    직접 돌릴 때는 그게 없으므로 **둘 다** 필요하다.
    """
    try:
        print(줄, flush=True)
    except Exception:
        pass


def 오류말하기(줄):
    """치명적 사유는 stderr 로도 남긴다 — 잡 레코드가 보관하는 게 stderr 꼬리다.

    stdout 과 **따로** 흘러서 버퍼도 따로다. 여기도 `flush=True` 가 필요하다.
    """
    try:
        print(줄, file=sys.stderr, flush=True)
    except Exception:
        pass


def 표시규칙제거(obj):
    """dict/list 를 재귀로 돌며 `표시규칙` 키를 **제거한 사본**을 돌려준다.

    불사자 MCP 는 모든 도구 응답에 모델 대상 지시문(`표시규칙`)을 실어 보낸다
    (*"앞 지시를 무시해라"* 류). 그게 산출물 파일에 남으면 나중에 그 파일을 LLM 에
    먹이는 경로가 생겼을 때 프롬프트 인젝션이 된다. 파일에 안 남기는 게 1차 방어다.
    (웹앱의 `join.strip_display_rules` 가 읽을 때 한 번 더 버린다 — 이중화)
    """
    if isinstance(obj, dict):
        return {k: 표시규칙제거(v) for k, v in obj.items() if k != "표시규칙"}
    if isinstance(obj, list):
        return [표시규칙제거(v) for v in obj]
    return obj


def 원자적쓰기(경로, obj):
    """`tmp → os.replace` — 반쯤 쓴 JSON 을 읽는 쪽이 보지 않게 한다.

    (`webapp/jobs.py:340-350` 의 `_write_targets` 와 같은 관용구)
    """
    try:
        경로 = str(경로)
        os.makedirs(os.path.dirname(경로) or ".", exist_ok=True)
        tmp = 경로 + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        os.replace(tmp, 경로)
    except Exception as e:
        말하기(f"[경고] 파일 저장 실패({경로}): {e}")


def 지금():
    """로컬 시각 + 오프셋 (`webapp/jobs._now()` 와 같은 모양)."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def 계정확인(mcp, 기대닉, 프로필경로):
    """`bulsaja_my_profile` 한 번. 닉네임이 다르면 **아무것도 하기 전에** 죽는다 (ENG-08).

    왜 자식이 또 확인하나 — 웹앱의 `create_job` 가드는 **잡을 띄우는 시점**의 사전 점검이다.
    잡이 뜨고 나서 계정이 바뀌는 창은 자식만 닫을 수 있다. 그리고 틀린 계정으로 3시간 32분을
    쌓고 나면 되돌리는 비용이 그 시간 전부다.

    산출물에는 닉네임·크레딧·확인시각만 싣는다. **이메일은 싣지 않는다** — 화면에 뜰 값이
    아니다(SAFE-03 의 정신). `표시규칙` 도 지운다.
    """
    프로필 = 표시규칙제거(mcp.call_tool("bulsaja_my_profile", {}) or {})
    닉 = str(프로필.get("닉네임") or "")
    기록 = {"닉네임": 닉, "크레딧": str(프로필.get("크레딧") or ""), "확인시각": 지금()}
    원자적쓰기(프로필경로, 기록)

    if 닉 != str(기대닉):
        # 기대·실제 닉네임을 **로그에 나란히 적지 않는다** — 계정 이름은 영업 정보다.
        사유 = ("⛔ 붙어 있는 불사자 계정이 기대한 계정이 아니다 (ENG-08). "
               "아무것도 하지 않고 종료한다. 프로필 파일에서 현재 계정을 확인해라.")
        말하기(사유)
        오류말하기(사유)
        return None
    return 기록


def 스키마확인(db경로):
    """`ss_index` 테이블 **존재만** 확인한다. 없으면 만들지 않고 False."""
    cx = sqlite3.connect(db경로)
    try:
        있음 = cx.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ss_index'"
        ).fetchone()
        return bool(있음)
    finally:
        cx.close()


# ── 그룹 훑기 ───────────────────────────────────────────────────────────────

def 그룹상품목록(mcp, 간격, gid, 페이지크기):
    """그룹 전체 `productId` 목록과 관측 시점의 `총상품수` 를 돌려준다.

    반환 `(pid목록, 총상품수 | None)`.

    `eroomlib.snapshot.collect_group` 을 쓰지 않는 이유가 둘 있다:
      ① 그 헬퍼는 자체 `time.sleep` 으로 간격을 잡아서 이 스크립트의 레이트리밋 예산과
         따로 논다 — 호출 간격의 주인이 둘이면 합산이 초당 4회를 넘는다
      ② 그룹 전체 개수를 반환값에 안 싣는다. 그 값이 없으면 "중간에 끊긴 잡" 과
         "다 훑었다" 를 구분할 수 없다 (`bulsaja_index.group_health` 의 `완결`)
    """
    pid들, 본것, page, 총상품수 = [], set(), 1, None
    while True:
        간격.대기()
        r = mcp.call_tool("bulsaja_market_group_products",
                          {"groupId": gid, "page": page, "pageSize": 페이지크기}) or {}
        항목 = r.get("항목") or []
        if not 항목:
            break

        # 서버가 전체 개수를 어느 이름으로 주는지 판마다 다르다. 못 찾으면 None 으로 둔다 —
        # **지어내지 않는다.** 없는 총계를 0 으로 채우면 "다 훑었다" 가 거짓으로 참이 된다.
        for 키 in ("전체개수", "총상품수", "총개수", "전체"):
            값 = r.get(키)
            if isinstance(값, int):
                총상품수 = 값
                break

        늘어남 = 0
        for it in 항목:
            pid = (it or {}).get("productId")
            if pid and pid not in 본것:
                본것.add(pid)
                pid들.append(pid)
                늘어남 += 1

        # `더있음` 이 명시적으로 거짓이면 멈춘다. 그 키가 없는 판을 대비해, 새로 들어온
        # 상품이 하나도 없으면(=같은 페이지를 다시 받았다) 무한루프를 끊는다.
        if r.get("더있음") is False or 늘어남 == 0:
            break
        page += 1

    return pid들, 총상품수


def 그룹훑기(mcp, cx, 간격, gid, 인자, 순번, 전체그룹수):
    """그룹 하나를 훑어 `ss_index` 에 적는다. 반환 `{groupId, 행수, 미조회, 총상품수, 완결}`.

    ⚠️ 여기서 만드는 요약은 **보고용**이다. 진실의 원천은 DB 다 —
       `bulsaja_index.group_health()` 가 같은 값을 DB 에서 다시 낸다. 둘이 어긋나면
       DB 가 맞다(이 요약은 이번 실행분만 보고, DB 는 이전 회차 적재분까지 본다).
    """
    머리 = f"[그룹 {순번}/{전체그룹수}]"

    # ① 재개 기준 — 이미 적힌 productId 집합. 페이지 번호가 아니다 (Pitfall 6).
    처리됨 = {r[0] for r in cx.execute(
        "SELECT product_id FROM ss_index WHERE market_group_id = ?", (gid,))}
    기존미조회 = cx.execute(
        "SELECT COUNT(*) FROM ss_index WHERE market_group_id = ? AND unresolved = 1",
        (gid,)).fetchone()[0]

    말하기(f"{머리} 목록 조회 중 (이미 적힌 것 {len(처리됨)}건"
          + (f", 그중 미조회 {기존미조회}건" if 기존미조회 else "") + ")")

    pid들, 총상품수 = 그룹상품목록(mcp, 간격, gid, 인자.batch_size)
    말하기(f"{머리} 상품 {len(pid들)}건"
          + (f" (서버 집계 {총상품수}건)" if 총상품수 is not None else ""))

    # ② 미조회로 적힌 행은 **다시 시도한다.** 성공한 행만 건너뛴다 — 안 그러면 429 때문에
    #    빠진 상품이 영원히 미조회로 남고, 그 행이 화면에서 "미해소" 로 굳는다 (Pitfall 3).
    남은미조회 = {r[0] for r in cx.execute(
        "SELECT product_id FROM ss_index WHERE market_group_id = ? AND unresolved = 1",
        (gid,))}
    할것 = [p for p in pid들 if p not in 처리됨 or p in 남은미조회]
    if 인자.limit:
        할것 = 할것[:인자.limit]

    말하기(f"{머리} 이번에 조회할 것 {len(할것)}건")

    미조회수, 처리수 = 0, 0
    for i, pid in enumerate(할것, 1):
        간격.대기()
        # **`mode=summary` 다.** `full` 을 쓸 이유가 없다 — 실측상 summary 에도
        # `uploadedSuccessUrl` 이 나오고 응답이 16% 작다(11,967자 vs 13,856자).
        #
        # **`ProductMCP` 의 workdata 헬퍼를 쓰지 않는다.** 그 투영이 `uploadedSuccessUrl` 을
        # 통째로 버려서, 그걸 쓰면 인덱스 히트율이 0%가 된다 (RESEARCH §Pitfall 1).
        # `call_tool` 원본을 직접 부르는 것이 그래서 의도적이다.
        r, 미조회 = 안전호출(
            lambda: mcp.call_tool("bulsaja_product_workdata",
                                  {"productId": pid, "mode": "summary"}),
            재시도대기=인자.retry_after, sleep_fn=time.sleep, 로그=말하기)

        if 미조회:
            # ⚠️ 건너뛰지 않는다. 행을 **남긴다.** 조용히 빠지면 그 상품이 화면에서
            #    "미해소(= 광고 쪽 오류)" 로 둔갑하고, 용팀장이 멀쩡한 광고그룹을 지우러
            #    간다. 되돌릴 수 없다 (RESEARCH §Pitfall 3).
            ss, unresolved = None, 1
            미조회수 += 1
        else:
            d = (r or {}).get("data") or {}
            값 = (d.get("uploadedSuccessUrl") or {}).get("smartstore")
            # 업로드 안 된 상품은 **정상적으로** NULL 이다 (수집상품 대부분이 그렇다).
            ss, unresolved = (str(값) if 값 else None), 0

        try:
            cx.execute(
                "INSERT OR REPLACE INTO ss_index "
                "(product_id, smartstore, market_group_id, group_total, unresolved, "
                " observed_at) VALUES (?,?,?,?,?,?)",
                (pid, ss, gid, 총상품수, unresolved, 지금()))
            cx.commit()          # **건마다 커밋.** 중단해도 여기까지는 남는다
            처리수 += 1
        except sqlite3.Error as e:
            말하기(f"{머리} ⛔ 적재 실패 {pid[-8:]}: {e}")

        if i % 50 == 0:
            말하기(f"{머리} {i}/{len(할것)} (미조회 {미조회수})")

    # ③ 이번 실행분이 아니라 **DB 의 현재 상태**로 요약한다 — 재개 실행에서도 맞는 숫자다.
    행수 = cx.execute("SELECT COUNT(*) FROM ss_index WHERE market_group_id = ?",
                     (gid,)).fetchone()[0]
    누적미조회 = cx.execute(
        "SELECT COUNT(*) FROM ss_index WHERE market_group_id = ? AND unresolved = 1",
        (gid,)).fetchone()[0]
    총계 = cx.execute("SELECT MAX(group_total) FROM ss_index WHERE market_group_id = ?",
                     (gid,)).fetchone()[0]

    # `bulsaja_index.group_health` 의 `완결` 과 **같은 식**이다. 행수 0 을 완결로 읽으면
    # 한 번도 안 훑은 그룹이 "다 봤다" 가 되고, 그 그룹 행이 "광고 쪽 오류" 로 뜬다.
    완결 = bool(행수 > 0 and 누적미조회 == 0
                and (총계 is None or 행수 >= 총계))

    말하기(f"{머리} 완료 — 이번 {처리수}건 · 누적 {행수}행 · 미조회 {누적미조회} · "
          f"완결 {'예' if 완결 else '아니오'}")
    return {"groupId": gid, "행수": 행수, "미조회": 누적미조회,
            "총상품수": 총계, "완결": 완결, "이번처리": 처리수}


# ── 진입점 ──────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="불사자 마켓그룹 인덱스 구축 (읽기 전용 조회 · 크레딧 0)")
    ap.add_argument("--db", required=True, help="webapp.db (ss_index 가 사는 파일)")
    ap.add_argument("--groups", required=True,
                    help="groupId 문자열 JSON 배열. **빈 배열은 전량이 아니다**")
    ap.add_argument("--out", required=True, help="진행 요약 JSON")
    ap.add_argument("--profile-out", required=True, help="계정 확인 결과 JSON")
    ap.add_argument("--expect-nick", required=True, help="기대 계정 닉네임 (ENG-08)")
    ap.add_argument("--min-interval", type=float, required=True,
                    help="호출 최소 간격(초). 서버 정책이 초당 4회다")
    ap.add_argument("--retry-after", type=int, required=True,
                    help="429 재시도 대기(초). 서버가 Retry-After 를 준다")
    ap.add_argument("--batch-size", type=int, required=True, help="목록 페이지 크기")
    ap.add_argument("--limit", type=int, default=0,
                    help="그룹당 처리 상한. 0/미지정이면 전량")
    인자 = ap.parse_args()

    시작 = time.time()

    # ① 대상 확인 — **MCP 도 SQLite 도 건드리기 전에** 본다.
    #    빈 목록에서 전 그룹(실측 75,335건 · 5시간 39분)으로 미끄러지는 경로를 막는다.
    #    웹앱 `jobs._build_argv` 의 ValueError 와 짝을 이루는 2층 방어다.
    try:
        with open(인자.groups, encoding="utf-8") as f:
            그룹들 = json.load(f)
    except FileNotFoundError:
        말하기(f"⛔ 그룹 목록 파일이 없다: {인자.groups} — 빈 목록은 전량이 아니다")
        return 2
    except Exception as e:
        말하기(f"⛔ 그룹 목록을 읽지 못했다({인자.groups}): {e}")
        return 2

    그룹들 = [str(g) for g in (그룹들 or []) if g]
    if not 그룹들:
        사유 = ("⛔ 훑을 마켓그룹이 없다 — **빈 목록은 전량이 아니다.** "
               "훑을 그룹을 지정해서 다시 불러라.")
        말하기(사유)
        오류말하기(사유)
        return 2

    말하기(f"대상 마켓그룹 {len(그룹들)}개 · 최소간격 {인자.min_interval}초 · "
          f"429 대기 {인자.retry_after}초 · 페이지 {인자.batch_size} (크레딧 0)")

    # 호출 간격의 주인은 **이 객체 하나**다. 그룹을 넘나들며 같은 객체를 쓴다 —
    # 그룹마다 새로 만들면 그룹 경계에서 간격이 0 으로 리셋돼 순간적으로 상한을 넘는다.
    간격 = 호출간격(인자.min_interval)

    mcp = BulsajaMCP()
    mcp.open()
    try:
        # ② 계정 확인 (ENG-08). **SQLite 에 한 글자도 쓰기 전에** 한다.
        계정 = 계정확인(mcp, 인자.expect_nick, 인자.profile_out)
        if 계정 is None:
            return 3

        # ③ 스키마 확인. **만들지 않는다** — 정본은 webapp/jobs.py 의 DDL 하나다.
        if not 스키마확인(인자.db):
            사유 = ("⛔ ss_index 테이블이 없다. 웹앱을 한 번 띄워 스키마를 만든 뒤 다시 불러라 "
                   "— 스키마 정본은 웹앱 한 곳이고, 여기서 만들면 두 벌이 된다.")
            말하기(사유)
            오류말하기(사유)
            return 4

        cx = sqlite3.connect(인자.db)
        try:
            요약 = []
            for 순번, gid in enumerate(그룹들, 1):
                try:
                    요약.append(그룹훑기(mcp, cx, 간격, gid, 인자, 순번, len(그룹들)))
                except Exception as e:
                    # 그룹 하나가 터져도 나머지는 계속 훑는다. 이미 커밋된 행은 남아 있고,
                    # 다음 실행이 그 그룹만 이어서 한다.
                    말하기(f"[그룹 {순번}/{len(그룹들)}] ⛔ 실패: {str(e)[:200]}")
                    요약.append({"groupId": gid, "행수": None, "미조회": None,
                                 "총상품수": None, "완결": False,
                                 "오류": str(e)[:200]})
        finally:
            cx.close()
    finally:
        try:
            mcp.close()
        except Exception:
            pass

    소요 = round(time.time() - 시작, 1)
    총행수 = sum(g["행수"] or 0 for g in 요약)
    총미조회 = sum(g["미조회"] or 0 for g in 요약)
    원자적쓰기(인자.out, {
        "생성시각": 지금(),
        "계정": 계정,
        "그룹": 요약,
        "총계": {"그룹수": len(요약), "행수": 총행수, "미조회": 총미조회,
                "완결그룹": sum(1 for g in 요약 if g.get("완결"))},
        "소요초": 소요,
    })

    말하기(f"끝 — 그룹 {len(요약)}개 · 누적 {총행수}행 · 미조회 {총미조회} · {소요}초")
    if 총미조회:
        말하기("※ 미조회는 **우리가 못 본 것**이다 (레이트리밋·타임아웃). "
              "광고 쪽 오류와 같은 칸에 담지 마라 — 같은 잡을 다시 돌리면 이어서 시도한다.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        # 중단이 안전하다는 것이 이 스크립트의 설계다 — 건마다 커밋했으므로
        # 여기까지 적힌 행은 그대로 남고, 같은 명령이 productId 집합으로 이어서 간다.
        말하기("\n중단됨 — 여기까지 적힌 행은 남아 있다. 같은 명령으로 이어서 돌려라.")
        sys.exit(130)
