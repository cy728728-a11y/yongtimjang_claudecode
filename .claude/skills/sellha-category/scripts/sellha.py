#!/usr/bin/env python3
"""
sellha.kr 카테고리 조회 — 상품명/키워드 → 네이버 카테고리 경로 추출

셀하(sellha.kr) 아이템 분석(research) 페이지에서 키워드가 속한 네이버 카테고리 경로
(예: '생활/건강 > 공구 > 원예공구 > 농기계')를 추출한다.

★ 2026-07-31 전면 개편 — 셀하 확장 프로그램이 **필수**가 됐다.
   네이버 API 종료(셀하 공지 2026-07-29) 이후 셀하는 카테고리·상품수를 서버가 아니라
   **크롬 확장이 브라우저에서 직접** 가져온다. 확장 없이 돌리면 로그인·검색이 다 되는데도
   응답이 빈 채로 와서 **전건 `파싱실패`** 가 된다. 실측 조건 3가지:
     ① 셀하 확장이 설치된 **크롬 프로필**로 띄운다 (`--profile`).
        `--load-extension` 은 Chrome 137+ 에서 막혔고 150 에서 우회 플래그 전부 실패.
     ② 그 프로필이 **셀하 로그인 + 네이버 로그인/보안확인**을 통과해 있어야 한다.
     ③ **`--headless` 는 쓰지 않는다** — 확장이 안 돌아 전건 실패(실측). 창 모드 고정.
   프로필 만드는 법 → SKILL.md §확장 프로필 준비

드라이버 엔진은 eroomlib.webdriver(봇 감지 우회 Chrome)를 쓴다.

자격증명: 같은 스킬 폴더의 .env (SELLHA_EMAIL, SELLHA_PW). git 제외됨.

사용법:
  # 상품명/키워드 하나 이상 조회 (--profile 필수)
  python sellha.py --profile D:/python_work/data/sellha/profile --query "낚시텐트"

  # 상품ID+상품명 매핑 파일(JSON: [{"productId":"..","name":".."}]) 배치 조회
  python sellha.py --profile <프로필> --input products.json --output result.json

  # 이미 떠 있는 크롬에 붙기(수동 점검용)
  python sellha.py --debugger 127.0.0.1:9222 --query "낚시텐트"

반환(항목별):
  검색어 · productId(입력시) · 카테고리경로 · 최종차수 · 확신도 · 마켓 · url · 상태 · error
  상태: 성공 | 조회실패(검색결과없음) | 파싱실패 | 로그인실패
"""
import argparse
import json
import os
import random
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


def _type(el, text):
    """입력칸을 확실히 비우고 친다.

    `.clear()` 는 React 제어 컴포넌트에서 값이 되살아나고, 크롬 자동완성이 채워둔
    값 위에 그냥 치면 두 벌로 겹친다(실측: 아이디 중복 → 로그인 실패,
    검색창 '사과' + '지게차 커버' → '사과지게차 커버').
    """
    from selenium.webdriver.common.keys import Keys
    try:
        el.click()
    except Exception:
        # 공지 모달 등이 덮고 있으면 click 이 가로막힌다 → 스크롤 + JS 포커스로 우회
        drv = el.parent
        drv.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        drv.execute_script("arguments[0].focus();", el)
    el.send_keys(Keys.CONTROL, "a")
    el.send_keys(Keys.DELETE)
    time.sleep(0.15)
    el.send_keys(text)


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

    # ★ 반드시 비우고 입력한다 (2026-07-31).
    # 크롬 프로필에 자격증명이 저장돼 있으면 필드가 **자동완성된 상태**로 뜬다.
    # 그냥 send_keys 하면 아이디가 두 벌로 겹쳐 로그인이 실패한다.
    # `.clear()` 는 React 제어 입력에 안 먹으므로 Ctrl+A → Delete 로 지운다.
    _type(email_el, email)
    time.sleep(0.2)
    _type(pw_el, pw)
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


# ── 확장 프로필 기동 + UI 조회 (2026-07-31 전면 교체) ────────────────────────
#
# 네이버 API 종료(셀하 공지 2026-07-29) 이후 셀하는 카테고리 데이터를 **서버가 아니라
# 크롬 확장 프로그램이 브라우저에서 직접** 가져온다. 그래서 예전 방식(확장 없는 새 프로필
# + URL 진입)은 전건 `파싱실패` 가 된다. 실측으로 확인된 필수 조건 3가지:
#
#   ① 셀하 확장이 설치된 **프로필**로 크롬을 띄운다 (`--load-extension` 은 Chrome 137+ 에서
#      막혔고 150 에서도 우회 플래그 전부 실패 — 프로필 외 방법이 없다)
#   ② 그 브라우저가 **셀하 로그인** + **네이버 로그인/보안확인**을 통과해 있어야 한다
#   ③ URL 로 keyword 를 갈아끼워도 **화면이 안 바뀐다**(SPA) → 검색창에 입력해야 한다
#
# 프로필 만드는 법 → SKILL.md §확장 프로필 준비.

CARD_JS = r"""
  const out=[];
  document.querySelectorAll('*').forEach(el=>{
    if(el.children.length) return;
    if(!/^\d+(\.\d+)?%$/.test((el.textContent||'').trim())) return;
    const gp = el.parentElement && el.parentElement.parentElement;
    if(!gp) return;
    const t = gp.innerText.replace(/\n/g,' ').trim();
    if(t.indexOf('>') < 0) return;
    let card = gp;
    for(let i=0;i<4 && card.parentElement;i++) card = card.parentElement;
    out.push({node:t, card:card.innerText.replace(/\n/g,' ').trim()});
  });
  return out;
"""

_NOWS = lambda s: re.sub(r"\s+", "", s or "")


def human_pause(base, hi, label=""):
    """조회 간 **난수** 대기. 고정 간격은 그 자체가 봇 신호라 오히려 위험하다.

    네이버가 차단 사유로 명시한 것이 "짧은 시간 내에 너무 많은 요청이 이루어진 IP" 다.
    간격을 고르게 두면 사람처럼 안 보이므로 폭을 준다.
    """
    d = random.uniform(base, max(base, hi))
    if label:
        print(f"    (대기 {d:.1f}초{label})", flush=True)
    time.sleep(d)
    return d


def create_profile_driver(profile_dir, headless=False, debugger=None):
    """셀하 확장이 설치된 프로필로 크롬 기동. `debugger`가 있으면 기존 창에 붙는다."""
    from selenium import webdriver
    o = webdriver.ChromeOptions()
    if debugger:
        o.add_experimental_option("debuggerAddress", debugger)
        return webdriver.Chrome(options=o)
    o.add_argument("--disable-blink-features=AutomationControlled")
    o.add_experimental_option("excludeSwitches", ["enable-automation"])
    o.add_argument(f"--user-data-dir={profile_dir}")
    o.add_argument("--profile-directory=Default")
    if headless:
        # 확장은 headless=new 에서만 동작한다(구 headless 는 확장 미지원)
        o.add_argument("--headless=new")
    return webdriver.Chrome(options=o)


def dismiss_popups(driver):
    driver.execute_script("""
      document.querySelectorAll('button,a,span,div').forEach(e=>{
        const t=(e.textContent||'').trim();
        if(t==='3일 동안 보지 않기'||t==='취소'||t==='닫기'){ try{e.click();}catch(_){} }
      });
    """)


def _search_box(driver):
    for b in driver.find_elements(By.CSS_SELECTOR, "input"):
        try:
            if b.is_displayed() and (b.get_attribute("placeholder") or "").startswith("키워드를"):
                return b
        except Exception:
            continue
    return None


def lookup_category_ui(driver, keyword, timeout=30):
    """검색창에 입력해 조회. **결과 카드가 그 키워드의 것인지 확인한 뒤** 읽는다.

    확인이 필수인 이유: SPA 라 이전 키워드 결과가 화면에 남아 있고, 로그인 전에는
    예시 카드(`isExample=true`, 늘 '사과')가 떠 있다. 검증 없이 읽으면 남의 답을 가져온다.
    """
    from selenium.webdriver.common.keys import Keys
    result = {"검색어": keyword, "카테고리경로": None, "최종차수": None, "확신도": None,
              "마켓": "네이버", "url": None, "상태": None, "error": None}
    box = _search_box(driver)
    if box is None:
        result["상태"] = "파싱실패"; result["error"] = "검색창을 찾지 못함"
        return result
    try:
        _type(box, keyword)
        box.send_keys(Keys.ENTER)
    except Exception as e:
        result["상태"] = "파싱실패"; result["error"] = f"입력 실패: {type(e).__name__}"
        return result

    want = _NOWS(keyword)
    for _ in range(timeout):
        time.sleep(1)
        try:
            cards = driver.execute_script(CARD_JS) or []
            text = driver.execute_script("return document.body.innerText") or ""
        except Exception as e:
            result["상태"] = "파싱실패"; result["error"] = f"페이지 로드 실패: {e}"
            return result
        for c in cards:
            if want not in _NOWS(c.get("card", "")):
                continue                      # 다른 키워드의 카드(잔상·예시) → 무시
            m = CAT_PAT.search(c.get("node", ""))
            if not m:
                continue
            pct, path = m.group(1), re.sub(r"\s*>\s*", " > ", m.group(2)).strip()
            path = re.split(r"\s{2,}", path)[0].strip()
            tiers = [t.strip() for t in path.split(">") if t.strip()]
            result.update({"카테고리경로": path, "최종차수": tiers[-1] if tiers else None,
                           "확신도": pct, "상태": "성공"})
            result["url"] = driver.current_url
            return result
        if any(k in text for k in ("일시적으로 제한", "접속이 제한", "비정상적인 접근")):
            # 네이버가 확장 기반 접근을 차단했다. 계속 두드리면 더 오래 막힌다 → 즉시 반환
            result["상태"] = "차단감지"
            result["error"] = "네이버 쇼핑 접속 제한 — 대기 후 재시도 필요"
            return result
        if "확장프로그램 설치" in text or "네이버 보안 확인" in text:
            result["상태"] = "파싱실패"
            result["error"] = "확장 미동작/네이버 보안확인 필요 — 프로필 상태 점검 필요"
            return result
        if any(k in text for k in ("검색 결과가 없", "검색결과가 없", "데이터가 없")):
            result["상태"] = "조회실패"; result["error"] = "검색 결과 없음"
            return result
    result["상태"] = "파싱실패"; result["error"] = "카테고리 경로를 찾지 못함(타임아웃)"
    result["url"] = driver.current_url
    return result


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
    ap.add_argument("--profile", default=os.environ.get("SELLHA_PROFILE"),
                    help="셀하 확장이 설치된 크롬 프로필 경로(필수. 없으면 카테고리가 안 나온다). "
                         "환경변수 SELLHA_PROFILE 로도 지정 가능")
    ap.add_argument("--debugger", default=None,
                    help="이미 떠 있는 크롬에 붙는다(예 127.0.0.1:9222). --profile 대신 사용")
    ap.add_argument("--sleep", type=float, default=5.0,
                    help="조회 간 최소 대기(초). 실제 대기는 이 값~--sleep-max 사이 난수 "
                         "(2026-08-01 2.0→5.0 상향 — 실제 IP 차단 발생 이후)")
    ap.add_argument("--sleep-max", type=float, default=15.0,
                    help="조회 간 최대 대기(초). (2026-08-01 sleep x 3→고정 15.0 상향)")
    ap.add_argument("--rest-every", type=int, default=10,
                    help="평균 N건마다 긴 휴식(실제 주기도 난수). 0=안 함 "
                         "(2026-08-01 30→10 상향 — 더 잦은 휴식)")
    ap.add_argument("--block-wait", type=float, default=300,
                    help="차단 감지 시 대기(초). 그 뒤 1회 재시도")
    args = ap.parse_args()
    if not args.profile and not args.debugger:
        ap.error("--profile 또는 --debugger 가 필요합니다 "
                 "(셀하는 확장 없이는 카테고리를 주지 않습니다 — SKILL.md §확장 프로필 준비)")

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
        """확장 프로필로 드라이버 생성 → 필요할 때만 로그인 → research 페이지 준비."""
        try:
            d = create_profile_driver(args.profile, headless=args.headless,
                                      debugger=args.debugger)
        except Exception as e:
            print(f"드라이버 기동 실패: {type(e).__name__}: {e}")
            return None
        d.get("https://sellha.kr/")
        time.sleep(4)
        body = d.execute_script("return document.body.innerText") or ""
        if "님" not in body:
            # 프로필에 세션이 살아 있으면 재로그인하지 않는다 — 불필요한 로그인은 차단 위험만 키운다
            print(f"로그인: {email[:3]}***", flush=True)
            if not login(d, email, pw):
                _close_driver(d)
                return None
            print("로그인 성공", flush=True)
        else:
            print("기존 세션 재사용", flush=True)
        d.get("https://sellha.kr/research")
        time.sleep(6)
        dismiss_popups(d)
        time.sleep(1)
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

    sleep_hi = args.sleep_max if args.sleep_max else args.sleep * 3
    next_rest = (max(5, int(random.uniform(args.rest_every * 0.6, args.rest_every * 1.4)))
                 if args.rest_every else 10 ** 9)
    print(f"대기 정책: 조회당 {args.sleep:.1f}~{sleep_hi:.1f}초 난수"
          + (f" · 약 {args.rest_every}건마다 긴 휴식" if args.rest_every else "")
          + f" · 차단 시 {args.block_wait:.0f}초 대기", flush=True)

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

            r = lookup_category_ui(driver, name)
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
                r = lookup_category_ui(driver, name)

            if pid is not None:
                r = {"productId": pid, **r}
            results.append(r)
            since_restart += 1
            print(f"[{i}/{len(todo)}] [{name[:22]}] {r['상태']}  →  {r.get('카테고리경로') or r.get('error')}"
                  + (f"  ({r['확신도']}%)" if r["상태"] == "성공" else ""), flush=True)
            if i % 5 == 0:
                _flush()  # 5건마다 증분 저장

            # ── 차단 감지 → 길게 쉬고 1회만 재시도 ──────────────────────────
            if r.get("상태") == "차단감지":
                print(f"  !! 네이버 접속 제한 감지 — {args.block_wait:.0f}초 대기 후 1회 재시도",
                      flush=True)
                _flush()
                time.sleep(args.block_wait)
                r2 = lookup_category_ui(driver, name)
                if pid is not None:
                    r2 = {"productId": pid, **r2}
                results[-1] = r2
                if r2.get("상태") == "차단감지":
                    print("  !! 재시도도 차단 — 중단한다. 시간을 두고 `--resume` 으로 이어서.",
                          flush=True)
                    _flush()
                    sys.exit(2)
                print(f"  -- 재개: {r2.get('카테고리경로') or r2.get('error')}", flush=True)

            # ── 조회 간 난수 대기 + 주기적 긴 휴식 ─────────────────────────
            if i < len(todo):
                human_pause(args.sleep, sleep_hi)
                if args.rest_every and i >= next_rest:
                    human_pause(args.rest_every * 0.6, args.rest_every * 2.0,
                                label=" · 긴 휴식")
                    next_rest = i + max(5, int(random.uniform(args.rest_every * 0.6,
                                                              args.rest_every * 1.4)))

        _flush()
        if args.output:
            print(f"\n저장: {args.output} ({len(results)}건)")
        else:
            print("\n" + json.dumps(results, ensure_ascii=False, indent=2))
    finally:
        # --debugger 로 붙은 창은 우리 것이 아니다 — 닫지 않는다
        if not args.debugger:
            _close_driver(driver)


if __name__ == "__main__":
    main()
