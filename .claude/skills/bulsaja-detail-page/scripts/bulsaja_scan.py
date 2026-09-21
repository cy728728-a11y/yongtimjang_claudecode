# -*- coding: utf-8 -*-
"""불사자 계정 확인 + 회차 조인 스캔 — **관측만 적는다. 판정은 한 줄도 없다.**

무엇을 하나
  광고 판정 행 `(계정alias, mallProductId)` 목록을 받아, 그 번호가 지금 불사자의 어떤
  상품인지를 **다시 읽어** 회차 산출물(`join_<job>.json`)에 적는다. 인덱스에 적힌 값을
  그대로 믿지 않는 이유는 20일 물갈이로 채널상품번호가 재발급되기 때문이다(D-04/JOIN-04) —
  적힌 값만 보고 작업 대상을 정하면 **조용히 틀린 상품에 크레딧을 태운다.**

왜 여기서 아무것도 판정하지 않나
  이 파일이 적는 것은 전부 관측값이다: 인덱스에 적혀 있던 번호 · 지금 읽은 번호 ·
  상세 필드 원본 · 사본 목록. 그 값들을 맞대어 조인 결과를 내는 것은
  `webapp/join.py` 의 `재검증판정` **한 곳**이다. 판정이 두 곳에 있으면 화면과 산출물이
  다른 말을 하고, 그때 어느 쪽이 맞는지 아무도 모른다.
  상세 상태(⚪🟡🔴) 도 마찬가지다 — `uploadDetailContents` 를 **키 부재까지 그대로** 싣고,
  읽는 쪽(`webapp/state.py`)이 판정한다. 여기서 미리 접으면 그 규약이 두 벌이 된다.

모드 둘
  · `--profile-only` : `bulsaja_my_profile` 한 번(실측 0.14초, 크레딧 0)만 부르고 끝.
                       기대 계정이 아니어도 **파일은 쓰고** exit 3 — 화면이
                       "지금 붙어 있는 계정이 다르다" 를 말할 수 있어야 한다
  · 스캔             : 아래 흐름

스캔 흐름
  1. 계정 확인. 기대 계정이 아니면 exit 3 — 스캔은 시작도 하지 않는다 (ENG-08 2층 방어)
  2. `--targets` 읽기. 비면 exit 2. **빈 목록은 전량이 아니다**
  3. `bulsaja_market_groups` 한 번(실측 0.11초, 86개). `groupId`·`그룹명` 만 싣는다.
     **번호 추출·매칭을 여기서 하지 않는다** — 그건 웹앱(`join.market_number` /
     `join.group_index`)의 일이고, 여기서 또 하면 규칙이 두 벌이 된다
  4. `--db` 를 **읽기 전용**(`mode=ro`)으로 열어 인덱스를 조회한다. 스캔은 인덱스를
     고치지 않는다. 파일·테이블이 없으면 전 행을 `미조회` 로 두고 **계속 간다** —
     인덱스 구축 전에도 번호층 해상률과 광고 청소 목록은 나와야 한다
  5. 인덱스에 productId 가 있는 행만 `bulsaja_product_workdata(mode=summary)` 로 다시 읽는다
  6. 팬아웃(JOIN-03): 모인 판매자상품코드를 **배치로** `bulsaja_product_find_by_code` 에
     넣어 사본 묶음 키를 얻고, 다시 배치로 넣어 사본 전체를 얻는다.
     **행마다 한 번씩 부르지 않는다** — 194행이면 194호출이라 레이트리밋 예산의 40%를 먹는다
     (실측: 50코드 배치가 0.53초)
  7. 산출물 전체에서 `표시규칙` 을 재귀 제거하고 원자적으로 쓴다

코드 두 가지를 구분한다 (D-05/D-06, 2026-09-21 실측으로 정정됨)
  · `판매자상품코드` — 사본 **1개**를 집는다. workdata 의 `uploadBulsajaCode` 가 이 값이다
  · 불사자 사본 묶음 키 — 사본 **전체**를 묶는다. `find_by_code` 응답에만 나온다
  CONTEXT 의 canonical_refs 는 `uploadBulsajaCode` 를 묶음 키로 적었는데 **그게 틀렸다.**
  그래서 팬아웃이 2단 조회가 된다.

종료코드
  0  정상 (`--profile-only` 포함)
  2  대상이 없다 (`--targets` 파일이 없거나 배열이 비었다)
  3  기대한 불사자 계정이 아니다 (ENG-08)

사용:
  python3 bulsaja_scan.py --profile-only --db <webapp.db> --profile-out <p.json>
        --expect-nick <닉네임> --min-interval 0.26 --retry-after 21 --batch-size 50
  python3 bulsaja_scan.py --run-dir <회차> --targets <t.json> --out <join.json>
        --db <webapp.db> --profile-out <p.json> --expect-nick <닉네임>
        --min-interval 0.26 --retry-after 21 --batch-size 50
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
# **경로를 박지 않는다** (같은 관용구: run_names.py:40-46 · detail_batch.py:47-52).
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", ".."))
SKILL_SCRIPTS = os.path.join(SKILLS_DIR, "bulsaja-category-fix", "scripts")
if SKILL_SCRIPTS not in sys.path:
    sys.path.insert(0, SKILL_SCRIPTS)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from bulsaja_mcp import BulsajaMCP  # noqa: E402
from bulsaja_rate import 안전호출, 호출간격  # noqa: E402


# ── 공용 유틸 (ss_index_build.py 와 같은 뼈대) ───────────────────────────────

def 말하기(줄):
    """진행 출력. `flush=True` 가 협상 불가다 — SSE 가 로그파일을 tail 한다."""
    try:
        print(줄, flush=True)
    except Exception:
        pass


def 오류말하기(줄):
    """치명적 사유는 stderr 로도. 잡 레코드가 보관하는 게 stderr 꼬리다."""
    try:
        print(줄, file=sys.stderr, flush=True)
    except Exception:
        pass


def 표시규칙제거(obj):
    """dict/list 를 재귀로 돌며 `표시규칙` 키를 **제거한 사본**을 돌려준다.

    불사자 MCP 는 모든 도구 응답에 모델 대상 지시문(`표시규칙`)을 싣는다
    (*"앞 지시를 무시해라"* 류). 그게 회차 산출물에 남으면 나중에 그 파일을 LLM 에
    먹이는 경로가 생겼을 때 프롬프트 인젝션이 된다. 파일에 안 남기는 게 1차 방어이고,
    웹앱의 `join.strip_display_rules` 가 읽을 때 한 번 더 버린다(방어적 이중화).
    """
    if isinstance(obj, dict):
        return {k: 표시규칙제거(v) for k, v in obj.items() if k != "표시규칙"}
    if isinstance(obj, list):
        return [표시규칙제거(v) for v in obj]
    return obj


def 원자적쓰기(경로, obj):
    """`tmp → os.replace` (`webapp/jobs.py:340-350` 의 관용구)."""
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
    return datetime.now().astimezone().isoformat(timespec="seconds")


def 계정확인(mcp, 기대닉, 프로필경로):
    """`bulsaja_my_profile` 한 번. 반환 `(기록, 통과여부)`.

    **기대 계정이 아니어도 파일은 쓴다** — 화면이 "지금 붙어 있는 계정이 다르다" 를
    말할 수 있어야 하기 때문이다. 산출물에는 닉네임·크레딧·확인시각만 싣는다.
    이메일은 싣지 않는다(화면에 뜰 값이 아니다 — SAFE-03 의 정신).
    """
    프로필 = 표시규칙제거(mcp.call_tool("bulsaja_my_profile", {}) or {})
    닉 = str(프로필.get("닉네임") or "")
    기록 = {"닉네임": 닉, "크레딧": str(프로필.get("크레딧") or ""), "확인시각": 지금()}
    원자적쓰기(프로필경로, 기록)
    return 기록, 닉 == str(기대닉)


# ── 인덱스 읽기 (쓰지 않는다) ───────────────────────────────────────────────

def 인덱스조회(db경로, 번호들, 묶음크기):
    """`{채널상품번호: {productId, smartstore, market_group_id, observed_at}}`.

    **읽기 전용이다.** URI 에 `mode=ro` 를 박아서, 실수로 쓰려 해도 SQLite 가 막는다.
    파일이 없으면 만들지 않는다 — 스캔이 인덱스 파일을 만들어 버리면 웹앱이
    "인덱스가 있다" 고 착각한다.

    같은 번호에 행이 둘이면 **관측시각이 늦은 쪽이 이긴다** (물갈이 재발급 대비).
    `webapp/bulsaja_index.lookup` 과 같은 규약인데, 그 모듈을 import 하지 않는 이유는
    `.venv`(CLI)에 웹앱 의존성이 없기 때문이다 — 두 venv 를 subprocess 경계로 갈라 둔 설계다.
    """
    나온것 = {}
    번호들 = 번호정리(번호들)
    if not 번호들 or not os.path.isfile(db경로):
        return 나온것, os.path.isfile(db경로)

    try:
        cx = sqlite3.connect(f"file:{db경로}?mode=ro", uri=True)
    except sqlite3.Error as e:
        말하기(f"[경고] 인덱스를 열지 못했다: {e}")
        return 나온것, False
    try:
        있음 = cx.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ss_index'"
        ).fetchone()
        if not 있음:
            return 나온것, False

        for i in range(0, len(번호들), 묶음크기):
            조각 = 번호들[i:i + 묶음크기]
            자리 = ",".join("?" * len(조각))
            for r in cx.execute(
                    "SELECT smartstore, product_id, market_group_id, observed_at "
                    f"FROM ss_index WHERE smartstore IN ({자리}) "
                    "ORDER BY observed_at ASC", tuple(조각)):
                # ASC 정렬이라 나중 행이 앞 행을 덮는다 = 최신 관측이 이긴다
                나온것[str(r[0])] = {"productId": r[1], "smartstore": str(r[0]),
                                    "market_group_id": r[2], "observed_at": r[3]}
    except sqlite3.Error as e:
        말하기(f"[경고] 인덱스 조회 실패: {e}")
        return 나온것, False
    finally:
        cx.close()
    return 나온것, True


def 번호정리(번호들):
    """`None`·빈칸을 걸러 문자열 목록으로. 빈 목록이 '전량' 이 되지 않게 한다."""
    return [str(n).strip() for n in (번호들 or []) if n and str(n).strip()]


# ── 팬아웃 (JOIN-03) ────────────────────────────────────────────────────────

def 배치조회(mcp, 간격, 코드들, 재시도대기, 묶음크기):
    """`bulsaja_product_find_by_code` 를 **배치로** 돌려 항목 목록을 모은다.

    ⚠️ 행마다 한 번씩 부르지 마라. 실측상 50코드 배치가 0.53초인데, 194행을 낱개로
       부르면 194호출이 되어 레이트리밋 예산(초당 4회)의 40%를 먹는다.
    """
    항목들 = []
    코드들 = [c for c in 코드들 if c]
    for i in range(0, len(코드들), 묶음크기):
        조각 = 코드들[i:i + 묶음크기]
        간격.대기()
        r, 미조회 = 안전호출(
            lambda: mcp.call_tool("bulsaja_product_find_by_code", {"codes": 조각}),
            재시도대기=재시도대기, sleep_fn=time.sleep, 로그=말하기)
        if 미조회 or not isinstance(r, dict):
            말하기(f"[경고] 코드 조회 {len(조각)}건을 못 받았다 — 사본 정보가 빈다")
            continue
        항목들.extend(표시규칙제거(r).get("항목") or [])
    return 항목들


# ── 진입점 ──────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="불사자 계정 확인 + 회차 조인 스캔 (읽기 전용 조회 · 크레딧 0)")
    ap.add_argument("--profile-only", action="store_true",
                    help="계정 확인만 하고 --profile-out 에 쓰고 끝낸다")
    ap.add_argument("--db", required=True, help="webapp.db (ss_index 를 읽기만 한다)")
    ap.add_argument("--profile-out", required=True, help="계정 확인 결과 JSON")
    ap.add_argument("--expect-nick", required=True, help="기대 계정 닉네임 (ENG-08)")
    ap.add_argument("--min-interval", type=float, required=True,
                    help="호출 최소 간격(초). 서버 정책이 초당 4회다")
    ap.add_argument("--retry-after", type=int, required=True, help="429 재시도 대기(초)")
    ap.add_argument("--batch-size", type=int, required=True,
                    help="코드 배치·인덱스 질의 묶음 크기")
    # 아래 셋은 스캔에서만 필수다. argparse 의 `required` 로 걸지 않는 이유는
    # `--profile-only` 모드가 이것들 없이 도는 **같은 스크립트**이기 때문이다
    # (`detail_batch.py` 의 `--submit-only`/`--poll-only` 와 같은 관용구).
    ap.add_argument("--run-dir", help="회차명 (스캔 필수, 기록용)")
    ap.add_argument("--targets", help='"<계정alias>|<mallProductId>" JSON 배열 (스캔 필수)')
    ap.add_argument("--out", help="산출물 join_<job>.json (스캔 필수)")
    인자 = ap.parse_args()

    시작 = time.time()
    간격 = 호출간격(인자.min_interval)

    mcp = BulsajaMCP()
    mcp.open()
    try:
        # ① 계정 확인 — 두 모드 공통. 파일은 어느 쪽이든 쓴다.
        계정, 통과 = 계정확인(mcp, 인자.expect_nick, 인자.profile_out)
        if not 통과:
            사유 = ("⛔ 붙어 있는 불사자 계정이 기대한 계정이 아니다 (ENG-08). "
                   "스캔을 시작하지 않는다. 프로필 파일에서 현재 계정을 확인해라.")
            말하기(사유)
            오류말하기(사유)
            return 3

        if 인자.profile_only:
            말하기(f"계정 확인 완료 ({계정['확인시각']}) — 크레딧 {계정['크레딧']}")
            return 0

        # ② 대상 확인. **빈 목록은 전량이 아니다.**
        for 필수, 이름 in ((인자.run_dir, "--run-dir"), (인자.targets, "--targets"),
                          (인자.out, "--out")):
            if not 필수:
                사유 = f"⛔ 스캔에는 {이름} 이 반드시 있어야 한다"
                말하기(사유)
                오류말하기(사유)
                return 2
        try:
            with open(인자.targets, encoding="utf-8") as f:
                원본대상 = json.load(f)
        except FileNotFoundError:
            말하기(f"⛔ 대상 파일이 없다: {인자.targets} — 빈 목록은 전량이 아니다")
            return 2
        except Exception as e:
            말하기(f"⛔ 대상 파일을 읽지 못했다({인자.targets}): {e}")
            return 2

        대상 = []
        for 항 in 원본대상 or []:
            문자 = str(항 or "")
            if "|" not in 문자:
                말하기(f"[경고] 형식이 아닌 대상을 건너뛴다: {문자[:60]}")
                continue
            # `|` 로 **한 번만** 나눈다 — alias 에는 `|` 가 못 들어간다
            # (`webapp/argv.py:46` 의 `Alias` 패턴이 보장한다).
            acct, mall = 문자.split("|", 1)
            if acct and mall:
                대상.append((acct, mall))

        if not 대상:
            사유 = "⛔ 스캔할 대상이 없다 — **빈 목록은 전량이 아니다.**"
            말하기(사유)
            오류말하기(사유)
            return 2

        말하기(f"회차 {인자.run_dir} · 대상 {len(대상)}행 · 최소간격 {인자.min_interval}초 "
              f"(읽기 전용 조회 · 크레딧 0)")

        # ③ 마켓그룹 목록 한 번. 번호 추출·매칭은 **웹앱의 일이다.**
        간격.대기()
        그룹응답 = 표시규칙제거(mcp.call_tool("bulsaja_market_groups", {}) or {})
        마켓그룹 = [{"groupId": str(g.get("groupId") or ""),
                    "그룹명": str(g.get("그룹명") or "")}
                   for g in (그룹응답.get("그룹") or 그룹응답.get("항목") or [])
                   if isinstance(g, dict)]
        말하기(f"마켓그룹 {len(마켓그룹)}개")

        # ④ 인덱스 읽기 (mode=ro). 없으면 전 행을 미조회로 두고 **계속 간다.**
        색인, 인덱스있음 = 인덱스조회(인자.db, [m for _, m in 대상], 인자.batch_size)
        if not 인덱스있음:
            말하기("※ 불사자 인덱스가 아직 없다 — 전 행을 '미조회'로 적고 계속 간다. "
                  "번호층 해상률과 광고 청소 목록은 인덱스 없이도 나온다.")
        말하기(f"인덱스에 적혀 있던 행 {len(색인)}/{len(대상)}")

        # ⑤ 행별 재검증 관측. **판정하지 않는다 — 읽은 값을 그대로 적는다.**
        행들, 관측수, 미조회수 = [], 0, 0
        for i, (acct, mall) in enumerate(대상, 1):
            적힌것 = 색인.get(str(mall))
            행 = {"acct": acct, "mallProductId": str(mall),
                  "productId": (적힌것 or {}).get("productId"),
                  "인덱스_smartstore": (적힌것 or {}).get("smartstore"),
                  "관측_smartstore": None,
                  "미조회": (not 인덱스있음),
                  "uploadDetailContents": None,
                  "그룹태그": None,
                  "판매자상품코드": None,
                  "불사자코드": None,
                  "사본": []}
            행들.append(행)

            pid = 행["productId"]
            if not pid:
                continue

            간격.대기()
            # `mode=summary` 로 충분하다 — 실측상 `uploadedSuccessUrl` 도
            # `uploadDetailContents` 도 여기 다 나오고 응답이 16% 작다.
            r, 미조회 = 안전호출(
                lambda: mcp.call_tool("bulsaja_product_workdata",
                                      {"productId": pid, "mode": "summary"}),
                재시도대기=인자.retry_after, sleep_fn=time.sleep, 로그=말하기)
            if 미조회:
                행["미조회"] = True
                미조회수 += 1
                continue

            d = 표시규칙제거((r or {}).get("data") or {})
            값 = (d.get("uploadedSuccessUrl") or {}).get("smartstore")
            행["관측_smartstore"] = str(값) if 값 else None
            # **키 부재까지 그대로 싣는다.** `aiImageGenerated` 는 값이 거짓이 되는 게
            # 아니라 키가 통째로 없다(실측 34건) — 여기서 기본값을 채우면 읽는 쪽의
            # 상태 판정이 뒤집힌다.
            dc = d.get("uploadDetailContents")
            행["uploadDetailContents"] = dc if isinstance(dc, dict) else None
            # `uploadBulsajaCode` 는 **판매자상품코드**다 (2026-09-21 실측 정정).
            코드 = d.get("uploadBulsajaCode")
            행["판매자상품코드"] = str(코드) if 코드 else None
            관측수 += 1

            if i % 50 == 0:
                말하기(f"  {i}/{len(대상)} (관측 {관측수} · 미조회 {미조회수})")

        # ⑥ 팬아웃 — 2단 배치 조회 (JOIN-03)
        코드행 = {}
        for 행 in 행들:
            if 행["판매자상품코드"]:
                코드행.setdefault(행["판매자상품코드"], []).append(행)

        묶음키수 = 0
        if 코드행:
            말하기(f"사본 조회 1단 — 판매자상품코드 {len(코드행)}건 "
                  f"(배치 {인자.batch_size})")
            for it in 배치조회(mcp, 간격, list(코드행), 인자.retry_after, 인자.batch_size):
                코드 = str((it or {}).get("판매자상품코드") or "")
                for 행 in 코드행.get(코드, []):
                    묶음 = (it or {}).get("불사자코드")
                    행["불사자코드"] = str(묶음) if 묶음 else None
                    # `그룹` 태그는 용팀장의 손자국이다(`구매_가공완료` 등). 상태 판정과
                    # 섞지 않고 **별개 값**으로 싣는다 (RESEARCH §Pitfall 8).
                    행["그룹태그"] = (it or {}).get("그룹")

            묶음별행 = {}
            for 행 in 행들:
                if 행["불사자코드"]:
                    묶음별행.setdefault(행["불사자코드"], []).append(행)
            묶음키수 = len(묶음별행)

            if 묶음별행:
                말하기(f"사본 조회 2단 — 묶음 키 {묶음키수}건")
                사본별 = {}
                for it in 배치조회(mcp, 간격, list(묶음별행),
                                  인자.retry_after, 인자.batch_size):
                    if not isinstance(it, dict):
                        continue
                    사본별.setdefault(str(it.get("불사자코드") or ""), []).append({
                        "판매자상품코드": str(it.get("판매자상품코드") or ""),
                        "그룹": it.get("그룹"),
                        "잠금": it.get("잠금"),
                    })
                for 묶음, 행들묶음 in 묶음별행.items():
                    for 행 in 행들묶음:
                        행["사본"] = 사본별.get(묶음, [])
    finally:
        try:
            mcp.close()
        except Exception:
            pass

    # ⑦ 산출물 — 쓰기 직전 한 번 더 `표시규칙` 을 훑는다.
    산출물 = 표시규칙제거({
        "run_dir": 인자.run_dir,
        "생성시각": 지금(),
        "계정": 계정,
        "마켓그룹": 마켓그룹,
        # D-18 제외 설정은 **웹앱이 읽어 `join.attach(excluded=...)` 로 넘긴다.**
        # 자식에게는 그 값을 주는 플래그가 없으므로 여기에 빈 배열을 적으면
        # "제외 없음" 이라는 거짓말이 된다. `null` = 모른다 (설정의 정본은 한 곳이다).
        "제외그룹": None,
        "행": 행들,
    })
    원자적쓰기(인자.out, 산출물)

    소요 = round(time.time() - 시작, 1)
    # 미조회 총계는 **행에서 다시 센다.** 위 `미조회수` 는 레이트리밋으로 못 읽은 것만이고,
    # 인덱스가 아예 없어서 미조회가 된 행은 거기 안 들어간다 — 그 둘을 합쳐 보여주지 않으면
    # "미조회 0" 이라는 거짓 안심 신호가 나간다.
    미조회합 = sum(1 for 행 in 행들 if 행.get("미조회"))
    말하기(f"끝 — 행 {len(행들)} · 관측 {관측수} · 미조회 {미조회합}"
          + (f"(그중 레이트리밋 {미조회수})" if 미조회수 else "")
          + f" · 사본묶음 {묶음키수}건 · {소요}초")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        말하기("\n중단됨 — 산출물을 쓰지 않았다. 다시 돌려라 (크레딧 0).")
        sys.exit(130)
