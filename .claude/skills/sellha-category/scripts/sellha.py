#!/usr/bin/env python3
"""
sellha.kr 카테고리 조회 — 상품명/키워드 → 네이버 카테고리 경로 추출

셀하(sellha.kr)에 이메일 로그인 후, 아이템 분석(research) 페이지에서
키워드가 속한 네이버 카테고리 경로(예: '생활/건강 > 공구 > 원예공구 > 농기계')를
추출한다. 아이템스카우트와 달리 확장 프로그램 없이 렌더되므로 크롤 가능.

드라이버 엔진은 eroomlib.webdriver(봇 감지 우회 Chrome)를 쓴다.

자격증명: 같은 스킬 폴더의 .env (SELLHA_EMAIL, SELLHA_PW). git 제외됨.

사용법:
  # 상품명/키워드 하나 이상 조회
  python sellha.py --query "아세아관리기엔진" "낚시텐트"

  # 상품ID+상품명 매핑 파일(JSON: [{"productId":"..","name":".."}]) 배치 조회
  python sellha.py --input products.json --output result.json

  # 결과 JSON 저장 / 창 숨김
  python sellha.py --query "낚시텐트" --output out.json --headless

반환(항목별):
  검색어 · productId(입력시) · 카테고리경로 · 최종차수 · 확신도 · 마켓 · url · 상태 · error
  상태: 성공 | 조회실패(검색결과없음) | 파싱실패 | 로그인실패
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)

# 봇 감지 우회 Chrome 드라이버는 eroomlib.webdriver 를 쓴다.
# `.claude` 앵커(= lib/eroomlib)를 찾아 lib 를 1회 insert.
_d = SCRIPT_DIR
while _d and _d != os.path.dirname(_d):
    _lib = os.path.join(_d, "lib")
    if os.path.isdir(os.path.join(_lib, "eroomlib")):
        if _lib not in sys.path:
            sys.path.insert(0, _lib)
        break
    _d = os.path.dirname(_d)
from eroomlib.webdriver import create_driver as _create_driver  # noqa: E402
from eroomlib.webdriver import close_driver as _close_driver  # noqa: E402
from eroomlib.envload import load_env as _envload  # noqa: E402

from selenium.webdriver.common.by import By  # noqa: E402

# 'NN.N% 대분류 > ... > 최종' 형태의 카테고리 라인
CAT_PAT = re.compile(
    r"(\d+(?:\.\d+)?)\s*%\s*"
    r"([가-힣A-Za-z0-9/()][^\n%]*?(?:\s*>\s*[^\n>%]+)+)"
)


def load_env():
    """SKILL_DIR/.env 에서 자격증명 로드(환경변수 우선). eroomlib.envload 사용."""
    cfg = _envload(os.path.join(SKILL_DIR, ".env"), ["SELLHA_EMAIL", "SELLHA_PW"])
    return cfg.get("SELLHA_EMAIL"), cfg.get("SELLHA_PW")


def login(driver, email, pw, timeout=30):
    """셀하 이메일 로그인. 성공 시 True."""
    driver.get("https://sellha.kr/member/login")
    time.sleep(3)
    try:
        email_el = driver.find_element(By.CSS_SELECTOR, "input[name='email']")
        pw_el = driver.find_element(By.CSS_SELECTOR, "input[name='password']")
    except Exception:
        print("로그인 폼을 찾지 못했습니다 (페이지 구조 변경 가능성).")
        return False

    email_el.click(); email_el.send_keys(email)
    time.sleep(0.2)
    pw_el.click(); pw_el.send_keys(pw)
    time.sleep(0.2)

    driver.execute_script("""
        var els=document.querySelectorAll('button, a, input[type=submit]');
        for (var i=0;i<els.length;i++){
            var t=(els[i].textContent||els[i].value||'').trim();
            if (t.indexOf('로그인')!==-1){ els[i].click(); return; }
        }
    """)

    # 로그인 완료 = /member/login 을 벗어남
    for _ in range(timeout):
        time.sleep(1)
        if "/member/login" not in (driver.current_url or ""):
            time.sleep(1)
            return True
    return False


def lookup_category(driver, keyword, timeout=22):
    """키워드의 네이버 카테고리 경로 조회. dict 반환."""
    result = {
        "검색어": keyword,
        "카테고리경로": None,
        "최종차수": None,
        "확신도": None,
        "마켓": "네이버",
        "url": None,
        "상태": None,
        "error": None,
    }
    enc = urllib.parse.quote(keyword)
    url = f"https://sellha.kr/research?keyword={enc}&tab=research-result"
    try:
        driver.get(url)
    except Exception as e:
        result["상태"] = "파싱실패"; result["error"] = f"페이지 로드 실패: {e}"
        return result
    result["url"] = driver.current_url

    best = None  # (확신도float, 경로str)
    saw_noresult = False
    for _ in range(timeout):
        time.sleep(1)
        text = driver.execute_script("return document.body.innerText") or ""
        if any(k in text for k in ("검색 결과가 없", "검색결과가 없", "데이터가 없")):
            saw_noresult = True
        matches = CAT_PAT.findall(text)
        if matches:
            for pct_s, path in matches:
                path = re.sub(r"\s*>\s*", " > ", path).strip()
                # 경로 꼬리 잡음 제거(다음 지표 라벨이 붙는 경우 대비)
                path = re.split(r"\s{2,}", path)[0].strip()
                try:
                    pct = float(pct_s)
                except ValueError:
                    pct = 0.0
                if best is None or pct > best[0]:
                    best = (pct, path)
            if best:
                break

    if best:
        pct, path = best
        tiers = [t.strip() for t in path.split(">") if t.strip()]
        result["카테고리경로"] = path
        result["최종차수"] = tiers[-1] if tiers else None
        result["확신도"] = f"{pct}"
        result["상태"] = "성공"
    elif saw_noresult:
        result["상태"] = "조회실패"; result["error"] = "검색 결과 없음"
    else:
        result["상태"] = "파싱실패"; result["error"] = "카테고리 경로를 찾지 못함(구조 변경/렌더 지연 가능)"
    return result


def main():
    ap = argparse.ArgumentParser(description="셀하 카테고리 조회")
    ap.add_argument("--query", "-q", nargs="+", help="조회할 상품명/키워드(들)")
    ap.add_argument("--input", "-i", help='배치 입력 JSON: [{"productId":"..","name":".."}]')
    ap.add_argument("--output", "-o", help="결과 JSON 저장 경로")
    ap.add_argument("--headless", action="store_true", help="Chrome 창 숨김")
    ap.add_argument("--resume", action="store_true",
                    help="output 에 이미 있는 productId(성공/조회실패)는 건너뜀")
    ap.add_argument("--restart-every", type=int, default=150,
                    help="N건마다 브라우저 재시작(장시간 드라이버 행 방지). 0=안 함")
    args = ap.parse_args()

    # 조회 대상 구성: [(productId or None, name)]
    targets = []
    if args.input:
        with open(args.input, encoding="utf-8") as f:
            for item in json.load(f):
                targets.append((item.get("productId"), item.get("name") or item.get("상품명")))
    for q in (args.query or []):
        targets.append((None, q))
    if not targets:
        ap.error("--query 또는 --input 중 하나가 필요합니다.")

    email, pw = load_env()
    if not email or not pw:
        print("Error: 자격증명이 없습니다. .env 에 SELLHA_EMAIL, SELLHA_PW 를 설정하세요.")
        sys.exit(1)

    # --resume: 기존 output 로드 → 이미 처리된 productId 스킵
    results = []
    done = set()
    if args.resume and args.output and os.path.exists(args.output):
        try:
            with open(args.output, encoding="utf-8") as f:
                results = json.load(f)
            # '성공'만 완료로 간주 → 실패건(세션만료 등)은 재실행 시 새 로그인으로 재시도.
            # 재시도 대상은 결과에서 제거해 중복 방지.
            done = {r.get("productId") for r in results
                    if r.get("productId") and r.get("상태") == "성공"}
            results = [r for r in results
                       if r.get("productId") in done or r.get("productId") is None]
            print(f"[resume] 성공 {len(done)}건 스킵, 실패건 재시도")
        except (json.JSONDecodeError, OSError):
            results, done = [], set()

    def _flush():
        if args.output:
            tmp = args.output + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            os.replace(tmp, args.output)  # 원자적 교체(크래시 시 손상 방지)

    todo = [(pid, name) for pid, name in targets if pid not in done]
    print(f"조회 대상 {len(todo)}건 (전체 {len(targets)})")

    def _new_session():
        """드라이버 생성 + 로그인. 실패 시 None."""
        d = _create_driver(headless=args.headless)
        if not d:
            return None
        print(f"로그인: {email[:3]}***", flush=True)
        if not login(d, email, pw):
            _close_driver(d)
            return None
        print("로그인 성공\n", flush=True)
        return d

    def _dead(r):
        """드라이버가 죽어서 난 실패인지(사이트 문제 아님)."""
        e = (r.get("error") or "")
        return "Read timed out" in e or "페이지 로드 실패" in e or "invalid session" in e \
            or "chrome not reachable" in e or "no such window" in e

    driver = _new_session()
    if not driver:
        print("Error: 드라이버/로그인 실패")
        _flush(); sys.exit(1)

    since_restart = 0
    try:
        for i, (pid, name) in enumerate(todo, 1):
            if not name:
                results.append({"검색어": None, "productId": pid, "상태": "파싱실패", "error": "상품명 없음"})
                continue

            # 주기적 브라우저 재시작(장시간 드라이버 행 방지)
            if args.restart_every and since_restart >= args.restart_every:
                print(f"  -- 브라우저 재시작 ({i}/{len(todo)}) --", flush=True)
                _close_driver(driver)
                driver = _new_session()
                since_restart = 0
                if not driver:
                    print("재시작 후 로그인 실패 — 중단(나머지는 --resume 으로 이어서)")
                    _flush(); sys.exit(1)

            r = lookup_category(driver, name)
            # 드라이버 사망 감지 → 즉시 재시작 후 1회 재시도
            if r.get("상태") != "성공" and _dead(r):
                print(f"  -- 드라이버 사망 감지, 재시작 후 재시도 --", flush=True)
                _close_driver(driver)
                driver = _new_session()
                since_restart = 0
                if not driver:
                    print("재시작 실패 — 중단(--resume 으로 이어서)")
                    if pid is not None:
                        r = {"productId": pid, **r}
                    results.append(r); _flush(); sys.exit(1)
                r = lookup_category(driver, name)

            if pid is not None:
                r = {"productId": pid, **r}
            results.append(r)
            since_restart += 1
            print(f"[{i}/{len(todo)}] [{name[:22]}] {r['상태']}  →  {r.get('카테고리경로') or r.get('error')}"
                  + (f"  ({r['확신도']}%)" if r["상태"] == "성공" else ""), flush=True)
            if i % 5 == 0:
                _flush()  # 5건마다 증분 저장

        _flush()
        if args.output:
            print(f"\n저장: {args.output} ({len(results)}건)")
        else:
            print("\n" + json.dumps(results, ensure_ascii=False, indent=2))
    finally:
        _close_driver(driver)


if __name__ == "__main__":
    main()
