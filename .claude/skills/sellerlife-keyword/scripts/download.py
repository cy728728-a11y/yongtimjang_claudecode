#!/usr/bin/env python3
"""셀러라이프(sellochomes.co.kr) 카테고리 소싱 엑셀 다운로더.

구글 로그인은 '전용 크롬 프로필 + 최초 1회 사람이 직접 로그인' 방식이다.
구글은 Selenium 의 자동 비밀번호 입력을 차단하므로, 비밀번호 단계는 딱 한 번
사람이 통과하고 그 세션을 프로필에 남긴다. 이후 실행은 계정 선택/무음 리다이렉트로 통과.

모드:
  --setup   보이는 브라우저를 띄우고, 사람이 구글 로그인을 끝낼 때까지 기다린다 (최초 1회)
  --probe   메뉴/버튼 후보를 덤프하고 실제로 한 번 받아본 뒤 산출물 형태(zip/xlsx)를 보고
  (기본)    로그인 확인 -> 카테고리 소싱 이동 -> '전체 카테고리 엑셀 다운로드'

출력 마커:
  ###ARTIFACT###  다음 줄에 받은 파일 절대경로
  ###SHAPE###     다음 줄에 zip | single
"""
import argparse
import glob
import os
import shutil
import sys
import time
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import DL_TMP_DIR, PROFILE_DIR, close_driver, load_env, make_driver, run_dir  # noqa: E402

BASE_URL = "https://sellochomes.co.kr/"
LOGIN_URL = "https://sellochomes.co.kr/auth/login"
# 카테고리 소싱 페이지 (셀러라이프 앱 SPA). 메뉴 클릭보다 직접 진입이 안정적.
CATEGORY_URL = "https://sellochomes.co.kr/sellerlife/sourcing/category/"
GOOGLE_BTN_CSS = "a.btn-google"          # <a class="btn-google login-btn" href="/auth/google">구글로 시작하기</a>
GOOGLE_BTN_TEXTS = ["구글로 시작하기", "구글로 로그인", "Sign in with Google"]
# '전체 카테고리 엑셀 다운로드' = 아이콘 버튼(텍스트 없음). CSS 클래스로 타겟.
ALL_EXCEL_CSS = "button.all-excel"
DOWNLOAD_BTN_HINTS = ["전체 카테고리 엑셀 다운로드", "전체 카테고리 엑셀", "엑셀 다운로드"]

DOWNLOAD_TIMEOUT = 180  # ZIP 이 클 수 있다


def js(driver, script, *args):
    return driver.execute_script(script, *args)


def click_text(driver, texts, tags="a, button, span, div, li, p"):
    """보이는 요소 중 텍스트가 일치/포함하는 것을 클릭. 클릭한 텍스트 반환, 실패 시 None."""
    if isinstance(texts, str):
        texts = [texts]
    return js(driver, """
        var wanted = arguments[0], sel = arguments[1];
        var els = [...document.querySelectorAll(sel)]
            .filter(e => e.offsetParent !== null);
        // 정확 일치 우선
        for (var w of wanted) {
            for (var e of els) {
                if ((e.textContent || '').trim() === w) { e.click(); return w; }
            }
        }
        // 포함 일치 (짧은 leaf 우선)
        for (var w of wanted) {
            for (var e of els) {
                var t = (e.textContent || '').trim();
                if (t && t.length < 40 && t.indexOf(w) !== -1 && e.childElementCount === 0) {
                    e.click(); return t;
                }
            }
        }
        for (var w of wanted) {
            for (var e of els) {
                var t = (e.textContent || '').trim();
                if (t && t.length < 60 && t.indexOf(w) !== -1) { e.click(); return t; }
            }
        }
        return null;
    """, texts, tags)


def visible_texts(driver, limit=400):
    return js(driver, """
        return [...document.querySelectorAll('a, button, span, div, li')]
            .filter(e => e.childElementCount === 0 && e.offsetParent !== null)
            .map(e => (e.textContent || '').trim())
            .filter(t => t && t.length > 0 && t.length < 40)
            .slice(0, arguments[0]);
    """, limit)


def click_google_account(driver, email):
    """구글 계정 선택 화면에서 email 타일을 클릭. 성공 시 방식 문자열, 실패 시 None.

    앱이 prompt=select_account 로 매번 계정 선택을 강제하지만, 구글 세션이 유효하면
    이 타일 한 번 클릭으로 비밀번호 없이 통과한다.
    """
    return js(driver, """
        var email = arguments[0];
        var el = document.querySelector('div[data-identifier="'+email+'"], li[data-identifier="'+email+'"]');
        if (el) { el.click(); return 'data-identifier'; }
        var cands = [...document.querySelectorAll('div[role=link], li, div[data-authuser], [jsname]')]
            .filter(e => e.offsetParent !== null && (e.textContent||'').indexOf(email) !== -1);
        if (cands.length) { cands[0].click(); return 'text-match'; }
        return null;
    """, email)


def click_google_consent(driver):
    """구글 동의/계속 화면 버튼 클릭 (있을 때만)."""
    return js(driver, """
        var words = ['계속', '허용', 'Continue', 'Allow', '확인', '동의'];
        var btns = [...document.querySelectorAll('button, [role=button], span')]
            .filter(e => e.offsetParent !== null);
        for (var w of words) {
            for (var b of btns) {
                if ((b.textContent||'').trim() === w) { b.click(); return w; }
            }
        }
        return null;
    """)


def is_logged_in(driver):
    """로그인 상태를 '양성 신호'로 판정한다.

    '로그인 텍스트가 없다' 만으로 판단하면 아직 로딩 안 된 빈 페이지를 로그인으로 오판한다.
    그래서 (1) 로그아웃/마이페이지 같은 계정 마커가 있거나,
            (2) 헤더 네비(셀러라이프·소싱라이프)가 실제로 렌더된 상태에서 '로그인/회원가입' 진입점이 사라졌을 때
    만 로그인으로 본다. 페이지가 덜 로딩됐으면(네비 없음) 무조건 False.
    """
    try:
        url = driver.current_url or ""
    except Exception:
        return False
    if "sellochomes" not in url and "sellerlife" not in url:
        return False
    return js(driver, """
        var els = [...document.querySelectorAll('a, button, span, div, li')]
            .filter(e => e.offsetParent !== null)
            .map(e => (e.textContent || '').trim())
            .filter(t => t && t.length < 40);
        var hasAccount = els.some(t => t.indexOf('로그아웃') !== -1
                                    || t.indexOf('마이페이지') !== -1
                                    || t.indexOf('내 정보') !== -1
                                    || t.indexOf('내정보') !== -1);
        if (hasAccount) return true;
        var navLoaded = els.some(t => t === '셀러라이프') && els.some(t => t === '소싱라이프');
        if (!navLoaded) return false;                       // 덜 로딩됨 -> 판단 보류(=미로그인)
        var hasLoginEntry = els.some(t => t.indexOf('로그인') !== -1 || t === 'Login');
        return !hasLoginEntry;                              // 네비는 떴는데 로그인 진입점이 없다 -> 로그인됨
    """)


def _click_google_button(driver):
    """로그인 페이지에서 '구글로 시작하기' 를 최대 15초 폴링하며 클릭."""
    driver.get(LOGIN_URL)
    for _ in range(15):
        time.sleep(1)
        if is_logged_in(driver):     # 이미 셀록홈즈 세션이 살아있으면 클릭 불필요
            return "already"
        clicked = js(driver, """
            var el = document.querySelector(arguments[0]);
            if (el && el.offsetParent !== null) { el.click(); return (el.textContent || '').trim(); }
            return null;
        """, GOOGLE_BTN_CSS)
        if clicked:
            return clicked
    return click_text(driver, GOOGLE_BTN_TEXTS)


def do_google_oauth(driver, email, wait_sec=300, allow_human=True):
    """구글 OAuth 로그인.

    구글 세션이 유효하면 계정 선택/동의를 자동 클릭해 사람 개입 없이 통과한다.
    비밀번호·2단계 인증 화면이 나오면(세션 없음):
      - allow_human=True (--setup): 사람이 끝낼 때까지 대기
      - allow_human=False (자동 실행): 실패 반환하며 --setup 안내
    """
    clicked = _click_google_button(driver)
    if clicked == "already":
        print("셀록홈즈 세션 유효 — 재로그인 불필요")
        return True
    if not clicked:
        print(f"[오류] '구글로 시작하기' 버튼을 찾지 못했습니다. (현재 URL: {driver.current_url})")
        return False
    print(f"로그인 버튼 클릭: {clicked!r}")
    time.sleep(2)

    prompted_human = False
    for i in range(wait_sec):
        time.sleep(1)
        try:
            url = driver.current_url
        except Exception as e:
            print(f"[오류] 브라우저 연결 끊김: {str(e)[:80]}")
            return False

        if is_logged_in(driver):
            print(f"로그인 확인됨 ({i}초 경과)")
            return True

        if "accounts.google.com" in url:
            # 1) 계정 선택 화면 -> 타일 자동 클릭
            if "accountchooser" in url or "select_account" in url:
                if click_google_account(driver, email):
                    print(f"  계정 자동 선택: {email}")
                    time.sleep(2)
                    continue
            # 2) 동의/계속 화면 -> 자동 클릭
            if click_google_consent(driver):
                print("  동의 화면 자동 진행")
                time.sleep(2)
                continue
            # 3) 비밀번호/2FA 화면 -> 세션 없음. 사람이 필요.
            needs_human = js(driver, """
                var u = location.href, t = document.body ? document.body.innerText : '';
                var challenge = /\\/challenge\\/|\\/pwd|signin\\/v2\\/challenge|비밀번호|2단계|passkey|본인 확인/;
                return challenge.test(u) || challenge.test(t);
            """)
            if needs_human:
                if not allow_human:
                    print("[오류] 구글 세션이 만료됐습니다(비밀번호/2FA 필요).")
                    print("  → `download.py --setup --wait 600` 을 실행해 다시 로그인하세요.")
                    return False
                if not prompted_human:
                    print(f"\n>>> 구글 로그인(비밀번호·2단계 인증)을 완료해 주세요 ({email})")
                    print(">>> Chrome 창이 다른 창 뒤에 숨어 있을 수 있습니다. 작업표시줄 확인.\n")
                    prompted_human = True

        if i and i % 20 == 0:
            print(f"  [{i:3d}s] 진행 중… {url[:80]}")

    print("[오류] 시간 내 로그인이 확인되지 않았습니다.")
    return False


def ensure_logged_in(driver, email, allow_human=False):
    """로그인 보장. 자동 실행 경로는 allow_human=False (계정선택 자동, 비번화면이면 --setup 안내)."""
    driver.get(BASE_URL)
    for _ in range(8):        # 홈 네비 로딩을 최대 8초 기다림
        time.sleep(1)
        if is_logged_in(driver):
            print("기존 세션으로 로그인 상태 확인")
            return True
    print("셀록홈즈 세션 없음 — 구글 재로그인 시도")
    return do_google_oauth(driver, email, wait_sec=120 if not allow_human else 600,
                           allow_human=allow_human)


def dismiss_modal(driver):
    """페이지 로드시 뜨는 홍보 모달을 닫는다 (있을 때만). 다운로드를 막지는 않지만 안전차원."""
    js(driver, """
        var closers = [...document.querySelectorAll(
            '[class*=modal] [class*=close], [class*=popup] [class*=close], '
          + '[class*=modal] button, [aria-label=닫기], [aria-label=Close], .close, .btn-close')]
            .filter(e => e.offsetParent !== null);
        for (var c of closers) {
            var t = (c.textContent || '').trim();
            if (t === '' || t === '×' || t === '닫기' || t.length < 4) { c.click(); }
        }
    """)


def navigate_to_sourcing(driver):
    """카테고리 소싱 페이지로 직접 진입 (셀러라이프 앱 SPA)."""
    driver.get(CATEGORY_URL)
    time.sleep(6)  # SPA 렌더 + 데이터 로드
    dismiss_modal(driver)
    time.sleep(1)
    if "sourcing/category" not in driver.current_url:
        print(f"  [경고] 카테고리 소싱 페이지가 아닙니다: {driver.current_url}")


def wait_for_download(dl_dir, before, timeout=DOWNLOAD_TIMEOUT):
    """새 파일이 완성될 때까지 대기 (.crdownload 제외 + 크기 안정)."""
    for _ in range(timeout):
        time.sleep(1)
        now = set(glob.glob(os.path.join(dl_dir, "*")))
        new = [f for f in (now - before) if not f.endswith(".crdownload")]
        if new:
            got = new[0]
            s1 = os.path.getsize(got)
            time.sleep(1.5)
            if os.path.getsize(got) == s1 and s1 > 0:
                return got
    return None


def click_download(driver, dl_dir, out_dir, base_name):
    os.makedirs(dl_dir, exist_ok=True)
    before = set(glob.glob(os.path.join(dl_dir, "*")))

    # CSS(button.all-excel) 우선 -> 텍스트 폴백
    got_btn = js(driver, """
        var b = document.querySelector(arguments[0]);
        if (b && b.offsetParent !== null) { b.click(); return arguments[0]; }
        return null;
    """, ALL_EXCEL_CSS)
    if not got_btn:
        got_btn = click_text(driver, DOWNLOAD_BTN_HINTS)
    if not got_btn:
        raise RuntimeError("'전체 카테고리 엑셀 다운로드' 버튼을 찾지 못했습니다. --probe 로 확인하세요.")
    print(f"다운로드 버튼 클릭: {got_btn!r} — 최대 {DOWNLOAD_TIMEOUT}초 대기")

    got = wait_for_download(dl_dir, before)
    if not got:
        raise RuntimeError("다운로드 파일을 확인하지 못했습니다 (타임아웃).")

    os.makedirs(out_dir, exist_ok=True)
    ext = os.path.splitext(got)[1] or ".zip"
    dest = os.path.join(out_dir, base_name + ext)
    n = 1
    while os.path.exists(dest):
        dest = os.path.join(out_dir, f"{base_name}_{n}{ext}")
        n += 1
    shutil.move(got, dest)
    return dest


def shape_of(path):
    if zipfile.is_zipfile(path):
        return "zip"
    return "single"


def main():
    ap = argparse.ArgumentParser(description="셀러라이프 카테고리 소싱 엑셀 다운로더")
    ap.add_argument("--setup", action="store_true", help="최초 1회 구글 로그인 (사람이 직접)")
    ap.add_argument("--probe", action="store_true", help="메뉴/버튼 후보 덤프 + 산출물 형태 확인")
    ap.add_argument("--out-dir", help="저장 폴더 (기본: runs/<YYMMDD>/raw)")
    ap.add_argument("--headless", action="store_true", help="창 숨김 (세션이 살아있을 때만)")
    ap.add_argument("--keep-open", action="store_true", help="작업 후 브라우저 유지")
    ap.add_argument("--wait", type=int, default=300, help="--setup 시 사람 로그인 대기 초 (기본 300)")
    args = ap.parse_args()

    cfg = load_env()
    email = cfg.get("SELLERLIFE_GOOGLE_EMAIL") or "(이메일 미설정)"
    out_dir = args.out_dir or run_dir(cfg["DATA_ROOT"])["raw"]

    if args.setup and args.headless:
        print("[오류] --setup 은 사람이 로그인해야 하므로 --headless 와 함께 쓸 수 없습니다.")
        sys.exit(1)

    driver = make_driver(headless=args.headless, profile_dir=PROFILE_DIR, download_dir=DL_TMP_DIR)
    if not driver:
        sys.exit(1)

    try:
        # ---- setup: 사람이 로그인만 하고 끝
        if args.setup:
            driver.get(BASE_URL)
            time.sleep(3)
            if is_logged_in(driver):
                print("이미 로그인되어 있습니다. 추가 작업 없이 종료합니다.")
                return
            if not do_google_oauth(driver, email, wait_sec=args.wait, allow_human=True):
                sys.exit(1)
            print(f"\n세션이 프로필에 저장되었습니다: {PROFILE_DIR}")
            print("이제부터는 `run_all.py` 한 줄이면 됩니다.")
            return

        # 자동 실행 경로: 계정선택은 자동, 비번/2FA 화면이면 --setup 안내.
        # (headless 가 아니면 사람이 개입할 수도 있게 allow_human 허용)
        if not ensure_logged_in(driver, email, allow_human=not args.headless):
            sys.exit(1)

        # ---- probe: 실제 텍스트를 먼저 보여준다
        if args.probe:
            print("\n[현재 페이지에서 보이는 텍스트 (상위 80개)]")
            for t in visible_texts(driver)[:80]:
                print("  -", t)

        navigate_to_sourcing(driver)

        if args.probe:
            print(f"\n[카테고리 소싱 페이지 URL] {driver.current_url}")
            print("[보이는 텍스트 (상위 120개)]")
            for t in visible_texts(driver)[:120]:
                print("  -", t)
            print("\n[다운로드 버튼 후보]")
            cands = js(driver, """
                return [...document.querySelectorAll('a, button')]
                    .filter(e => e.offsetParent !== null)
                    .map(e => (e.textContent || '').trim())
                    .filter(t => t && t.indexOf('다운') !== -1 || t.indexOf('엑셀') !== -1);
            """)
            for c in cands:
                print("  *", c)

        from datetime import date
        base_name = f"{date.today().strftime('%y%m%d')}_sellerlife_전체카테고리"
        dest = click_download(driver, DL_TMP_DIR, out_dir, base_name)
        shape = shape_of(dest)

        size_mb = os.path.getsize(dest) / 1048576
        print(f"\n다운로드 완료: {dest} ({size_mb:.1f} MB)")
        if shape == "zip":
            with zipfile.ZipFile(dest) as z:
                names = z.namelist()
            print(f"ZIP 내부 {len(names)}개 파일:")
            for n in names:
                print("   -", n)
        print("\n###ARTIFACT###")
        print(dest)
        print("###SHAPE###")
        print(shape)
    finally:
        if not args.keep_open:
            close_driver(driver)


if __name__ == "__main__":
    main()
