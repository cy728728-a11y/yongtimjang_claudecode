#!/usr/bin/env python3
"""
네이버 Selenium 로그인 + XHR 인터셉터 기반 API 세션 관리

Selenium으로 네이버에 직접 로그인하여:
  1. 쿠키 추출 (naver-cookies.txt) - naver_login() 레거시 함수
  2. NaverSession: 브라우저 세션 유지 + XHR 인터셉터로 리뷰 API 캡처
     - nfront WAF가 curl/requests (TLS 핑거프린팅)과
       Selenium execute_script에서 만든 XHR/fetch (실행 컨텍스트 감지)를 모두 차단
     - 해결: 페이지 자체의 XHR 호출을 XMLHttpRequest 몽키패치로 인터셉트

pyperclip + Ctrl+V 방식으로 네이버 봇 감지를 우회.

사용법:
  # 단독 실행 (쿠키 추출만)
  python cookie_extractor.py

  # naver-brand-reviews.py에서 사용 (NaverSession)
  python naver-brand-reviews.py <merchant> <product> --selenium --referer <url>
"""

import argparse
import json
import os
import platform
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
COOKIE_OUTPUT = os.path.join(SCRIPT_DIR, "naver-cookies.txt")

REQUIRED_COOKIES = ["NID_AUT", "NID_SES"]


def load_env():
    """SKILL_DIR/.env 에서 NAVER_ID, NAVER_PW 로드"""
    env_path = os.path.join(SKILL_DIR, ".env")
    if not os.path.exists(env_path):
        return None, None

    naver_id = None
    naver_pw = None
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key == "NAVER_ID":
                    naver_id = value
                elif key == "NAVER_PW":
                    naver_pw = value
    return naver_id, naver_pw


def _create_driver(headless=False):
    """Chrome WebDriver 생성 (WSL/Mac/Linux 자동 감지)"""
    from selenium import webdriver

    is_wsl = "microsoft" in platform.uname().release.lower()

    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    if headless:
        options.add_argument("--headless=new")

    if is_wsl:
        win_chrome_wsl = "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"
        win_chrome_win = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
        if os.path.exists(win_chrome_wsl):
            options.binary_location = win_chrome_win
            print("WSL 감지: Windows Chrome 사용")
        else:
            print(f"Error: Windows Chrome을 찾을 수 없습니다: {win_chrome_wsl}")
            return None

    print("Chrome 실행 중...")

    if is_wsl:
        import subprocess as sp
        import socket

        win_driver_path = os.path.expanduser("~/.cache/selenium/chromedriver/win64/chromedriver.exe")
        if not os.path.exists(win_driver_path):
            print(f"Error: Windows ChromeDriver가 없습니다: {win_driver_path}")
            return None

        host_ip = None
        try:
            result = sp.run(
                ["powershell.exe", "-Command",
                 "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -like '*WSL*' }).IPAddress"],
                capture_output=True, text=True, timeout=10,
            )
            host_ip = result.stdout.strip()
        except Exception:
            pass
        if not host_ip:
            host_ip = "172.17.128.1"
        print(f"Windows 호스트 IP: {host_ip}")

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            port = s.getsockname()[1]

        driver_proc = sp.Popen(
            [win_driver_path, f"--port={port}", "--allowed-ips="],
            stdout=sp.DEVNULL, stderr=sp.DEVNULL,
        )
        for _ in range(30):
            try:
                with socket.create_connection((host_ip, port), timeout=1):
                    break
            except (ConnectionRefusedError, OSError):
                time.sleep(0.5)
        else:
            print("Error: ChromeDriver 서비스 시작 실패")
            driver_proc.kill()
            return None

        driver = webdriver.Remote(
            command_executor=f"http://{host_ip}:{port}",
            options=options,
        )
        driver._chromedriver_proc = driver_proc
    else:
        driver = webdriver.Chrome(options=options)

    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def _close_driver(driver):
    """WebDriver 안전 종료"""
    try:
        driver.quit()
    except Exception:
        pass
    if hasattr(driver, "_chromedriver_proc"):
        try:
            driver._chromedriver_proc.kill()
        except Exception:
            pass
    print("Chrome 종료")


def _do_login(driver, naver_id, naver_pw):
    """네이버 로그인 수행. 성공 시 True 반환."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    import pyperclip

    paste_key = Keys.COMMAND if platform.system() == "Darwin" else Keys.CONTROL

    def _paste(el, text):
        """클립보드 복사 후 Cmd/Ctrl+V. element.send_keys(paste_key,'v')는
        Mac ChromeDriver에서 붙여넣기를 트리거하지 못하므로 ActionChains 조합키 사용."""
        el.click()
        time.sleep(0.3)
        pyperclip.copy(text)
        ActionChains(driver).key_down(paste_key).send_keys("v").key_up(paste_key).perform()
        time.sleep(0.3)

    print("네이버 로그인 페이지 접속...")
    driver.get("https://nid.naver.com/nidlogin.login")

    wait = WebDriverWait(driver, 10)

    id_input = wait.until(EC.presence_of_element_located((By.ID, "id")))
    _paste(id_input, naver_id)

    pw_input = driver.find_element(By.ID, "pw")
    _paste(pw_input, naver_pw)

    print("로그인 시도 중...")
    login_btn = driver.find_element(By.ID, "log.login")
    login_btn.click()

    print("로그인 완료 대기 중... (2FA/캡차 발생 시 브라우저에서 직접 완료해주세요)")
    for i in range(120):
        time.sleep(1)
        current_url = driver.current_url or ""
        if "nidlogin.login" not in current_url and "nid.naver.com" not in current_url:
            print(f"로그인 성공! (URL: {current_url[:60]}...)")
            return True
        if "nid.naver.com" in current_url and "nidlogin.login" not in current_url:
            if i % 10 == 0 and i > 0:
                print(f"  인증 진행 중... ({i}초 경과, 브라우저에서 완료해주세요)")

    print("Error: 로그인 타임아웃 (120초)")
    return False


def naver_login(naver_id, naver_pw, headless=False):
    """Selenium으로 네이버 로그인 후 쿠키 문자열 반환 (레거시 호환)"""
    try:
        from selenium import webdriver  # noqa: F401
    except ImportError:
        print("Error: selenium 패키지가 필요합니다. 설치: pip3 install selenium")
        sys.exit(1)
    try:
        import pyperclip  # noqa: F401
    except ImportError:
        print("Error: pyperclip 패키지가 필요합니다. 설치: pip3 install pyperclip")
        sys.exit(1)

    driver = _create_driver(headless=headless)
    if not driver:
        return None

    try:
        if not _do_login(driver, naver_id, naver_pw):
            return None

        # 여러 도메인 방문하여 쿠키 축적
        all_cookies = {}
        for url in ["https://www.naver.com", "https://shopping.naver.com", "https://brand.naver.com"]:
            print(f"  쿠키 수집: {url}")
            driver.get(url)
            time.sleep(3)
            for c in driver.get_cookies():
                all_cookies[c["name"]] = c["value"]

        cookie_str = "; ".join(f"{k}={v}" for k, v in all_cookies.items())

        missing = [name for name in REQUIRED_COOKIES if name not in all_cookies]
        if missing:
            print(f"Warning: 필수 쿠키 누락: {', '.join(missing)}")
            return None

        print(f"쿠키 추출 완료: {len(all_cookies)}개 항목")
        return cookie_str

    except Exception as e:
        print(f"Error: {e}")
        return None
    finally:
        _close_driver(driver)


class NaverSession:
    """네이버 로그인 브라우저 세션.

    TLS 핑거프린팅 우회를 위해 curl 대신 Chrome 내부에서
    JavaScript fetch()로 API를 직접 호출.
    """

    SORT_LABELS = {
        'REVIEW_RANKING': ['랭킹순'],
        'REVIEW_CREATE_DATE_DESC': ['최신순'],
        'REVIEW_SCORE_DESC': ['평점 높은순', '평점높은순', '별점 높은순', '별점높은순'],
        'REVIEW_SCORE_ASC': ['평점 낮은순', '평점낮은순', '별점 낮은순', '별점낮은순'],
    }

    def __init__(self):
        self.driver = None
        self._modal_opened = False

    def login(self, naver_id, naver_pw, headless=False, product_url=None):
        """로그인 후 세션 유지. 성공 시 True.

        product_url: 브랜드스토어 제품 페이지 URL (same-origin 설정용)
        """
        try:
            from selenium import webdriver  # noqa: F401
            import pyperclip  # noqa: F401
        except ImportError:
            print("Error: selenium, pyperclip 패키지가 필요합니다.")
            return False

        self.driver = _create_driver(headless=headless)
        if not self.driver:
            return False

        if not _do_login(self.driver, naver_id, naver_pw):
            self.close()
            return False

        # brand.naver.com으로 이동 (리뷰 API의 same-origin)
        target = product_url or "https://brand.naver.com"
        print(f"브랜드스토어 접속 중: {target[:60]}...")
        self.driver.get(target)
        time.sleep(3)
        print(f"세션 준비 완료 (현재 URL: {self.driver.current_url[:60]})")
        return True

    def install_interceptor(self):
        """페이지의 XHR+fetch 응답을 가로채는 인터셉터 설치.

        nfront WAF가 Selenium execute_script에서 만든 XHR을 차단하므로,
        페이지 자체의 API 호출을 가로채서 응답 데이터를 캡처.
        정렬 후 페이지네이션은 fetch를 사용할 수 있으므로 둘 다 패치.

        네이티브 메서드를 한 번만 저장하고 매번 그 위에 패치하여
        중첩 체인 문제를 방지.
        """
        self.driver.execute_script("""
            // 네이티브 메서드를 최초 1회만 저장
            if (!window.__nativeXhrOpen) {
                window.__nativeXhrOpen = XMLHttpRequest.prototype.open;
                window.__nativeXhrSend = XMLHttpRequest.prototype.send;
            }
            if (!window.__nativeFetch) {
                window.__nativeFetch = window.fetch;
            }
            window.__reviewResponses = [];
            window.__reviewRequestCount = 0;

            // XHR 인터셉터
            XMLHttpRequest.prototype.open = function(method, url) {
                this._interceptUrl = url;
                return window.__nativeXhrOpen.apply(this, arguments);
            };
            XMLHttpRequest.prototype.send = function(body) {
                var self = this;
                if (this._interceptUrl && this._interceptUrl.indexOf('reviews') !== -1
                    && this._interceptUrl.indexOf('query-pages') !== -1) {
                    window.__reviewRequestCount++;
                    this.addEventListener('load', function() {
                        if (self.status === 200 && self.responseText) {
                            try {
                                var data = JSON.parse(self.responseText);
                                window.__reviewResponses.push({
                                    url: self._interceptUrl,
                                    body: body,
                                    status: self.status,
                                    data: data
                                });
                            } catch(e) {}
                        }
                    });
                }
                return window.__nativeXhrSend.apply(this, arguments);
            };

            // fetch 인터셉터
            window.fetch = function(url, opts) {
                var urlStr = typeof url === 'string' ? url : (url && url.url ? url.url : '');
                if (urlStr.indexOf('reviews') !== -1 && urlStr.indexOf('query-pages') !== -1) {
                    window.__reviewRequestCount++;
                    return window.__nativeFetch.apply(this, arguments).then(function(response) {
                        var cloned = response.clone();
                        cloned.json().then(function(data) {
                            window.__reviewResponses.push({
                                url: urlStr,
                                body: opts && opts.body ? opts.body : null,
                                status: response.status,
                                data: data
                            });
                        }).catch(function() {});
                        return response;
                    });
                }
                return window.__nativeFetch.apply(this, arguments);
            };
        """)
        print("  인터셉터 설치 완료")

    def trigger_review_load(self, page=1):
        """페이지의 리뷰 로딩을 트리거.

        page=1: 맨 아래까지 스크롤 후 리뷰 탭 클릭
        page>=2: #REVIEW 내 페이지네이션 버튼 클릭
        """
        if page == 1:
            # 1) 맨 아래까지 스크롤 (리뷰 영역은 하단에 위치)
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)

            # 2) 리뷰 탭 클릭 (상단 중간의 리뷰가 아닌, 하단 본문 리뷰 탭)
            clicked = self.driver.execute_script("""
                // #REVIEW 영역 안이나 근처에서 리뷰 탭 찾기
                var review = document.getElementById('REVIEW');
                if (review) {
                    review.scrollIntoView();
                }

                // role=tab 요소 중 '리뷰'가 포함된 것 클릭
                var tabs = document.querySelectorAll('[role="tab"]');
                for (var i = 0; i < tabs.length; i++) {
                    var text = tabs[i].textContent || '';
                    if (text.indexOf('리뷰') !== -1 && text.indexOf('스토어픽') === -1) {
                        tabs[i].click();
                        return 'tab clicked: ' + text.trim().substring(0, 30);
                    }
                }

                // role=tab이 없으면 링크/버튼 중에서 찾기
                var elems = document.querySelectorAll('a, button');
                for (var i = 0; i < elems.length; i++) {
                    var text = elems[i].textContent || '';
                    if (/\\d+.*리뷰/.test(text) && text.indexOf('스토어픽') === -1) {
                        elems[i].click();
                        return 'link clicked: ' + text.trim().substring(0, 30);
                    }
                }

                return 'review tab not found';
            """)
            print(f"  리뷰 트리거: {clicked}")
        else:
            # 신 UI: 인라인에는 숫자 페이지네이션이 없고, "리뷰 전체보기" 모달 진입 후
            # 모달 내부 무한 스크롤로 페이지가 추가 로드됨 (스크롤 1회 = 다음 페이지 query-pages API 호출).
            if not self._modal_opened:
                opened = self.driver.execute_script("""
                    var btns = document.querySelectorAll('button, a');
                    for (var i = 0; i < btns.length; i++) {
                        var t = (btns[i].textContent || '').trim();
                        if (t === '리뷰 전체보기' || t === '리뷰 더보기') {
                            btns[i].scrollIntoView();
                            btns[i].click();
                            return 'modal opened: ' + t;
                        }
                    }
                    return 'modal trigger not found';
                """)
                print(f"  모달: {opened}")
                self._modal_opened = 'opened' in str(opened)
                # 모달 진입 시 자동으로 1페이지가 다시 로드됨 → 응답 큐를 비워야 스크롤로 받는 page=2를 잡음
                time.sleep(3)
                self.driver.execute_script("if (window.__reviewResponses) { window.__reviewResponses = []; }")

            scrolled = self.driver.execute_script("""
                // 모달 내 가장 큰 스크롤 가능 영역을 찾아 끝까지 내림
                var dialogs = document.querySelectorAll('[role="dialog"]');
                var dialog = null;
                for (var i = 0; i < dialogs.length; i++) {
                    if (dialogs[i].offsetWidth > 0) { dialog = dialogs[i]; break; }
                }
                if (!dialog) return 'modal not found';
                var all = dialog.querySelectorAll('*');
                var best = null;
                var bestClient = 0;
                for (var i = 0; i < all.length; i++) {
                    var el = all[i];
                    if (el.scrollHeight > el.clientHeight + 10 && el.clientHeight > bestClient) {
                        best = el;
                        bestClient = el.clientHeight;
                    }
                }
                if (!best) {
                    // fallback: 모달 자체 스크롤
                    dialog.scrollTop = dialog.scrollHeight;
                    return 'scrolled dialog';
                }
                best.scrollTop = best.scrollHeight;
                return 'scrolled: ' + best.tagName + ' clientH=' + bestClient;
            """)
            print(f"  페이지네이션 스크롤: {scrolled}")

    def get_captured_reviews(self, wait_seconds=5):
        """캡처된 리뷰 API 응답 반환. 응답이 올 때까지 대기."""
        for _ in range(wait_seconds * 2):
            time.sleep(0.5)
            count = self.driver.execute_script("return window.__reviewResponses ? window.__reviewResponses.length : 0;")
            if count > 0:
                # 가장 최근 응답 꺼내기
                result = self.driver.execute_script("""
                    if (window.__reviewResponses && window.__reviewResponses.length > 0) {
                        var resp = window.__reviewResponses.shift();
                        return JSON.stringify(resp.data);
                    }
                    return null;
                """)
                if result:
                    data = json.loads(result)
                    total = data.get("totalElements", "?")
                    contents = data.get("contents", [])
                    print(f"  인터셉트 성공: totalElements={total}, contents={len(contents)}개")
                    return data

        print(f"  인터셉트 대기 타임아웃 ({wait_seconds}초)")
        return None

    def change_sort(self, sort_type):
        """리뷰 정렬을 페이지 UI 클릭으로 변경.

        정렬 컨트롤은 <button> 이며 텍스트가 '라벨 + 정렬하기' 형태
        (예: '최신순정렬하기'). 접근성 접미사를 떼고 매칭한다.
        동명의 카테고리 탭('랭킹순')과 구분하기 위해 '정렬하기' 접미사가
        붙은 실제 정렬 버튼을 먼저 찾고, 없을 때만 정확 매칭으로 폴백.
        scrollIntoView 없이 직접 click()으로 트리거해야 XHR이 발생.
        """
        labels = self.SORT_LABELS.get(sort_type, [])
        if not labels:
            print(f"  알 수 없는 정렬: {sort_type}")
            return False

        result = self.driver.execute_script("""
            var labels = arguments[0];
            var els = document.querySelectorAll('button, a');
            // 1차: '정렬하기' 접미사가 붙은 실제 정렬 버튼 우선
            for (var j = 0; j < labels.length; j++) {
                for (var i = 0; i < els.length; i++) {
                    var raw = els[i].textContent.trim();
                    if (raw.indexOf('정렬하기') === -1) continue;
                    var norm = raw.replace(/정렬하기$/, '').trim();
                    if (norm === labels[j]) {
                        els[i].click();
                        return 'clicked: ' + raw;
                    }
                }
            }
            // 2차 폴백: 라벨 정확 매칭 (구버전 <a> 링크 대비)
            for (var j = 0; j < labels.length; j++) {
                for (var i = 0; i < els.length; i++) {
                    if (els[i].textContent.trim() === labels[j]) {
                        els[i].click();
                        return 'clicked: ' + labels[j];
                    }
                }
            }
            return 'not found';
        """, labels)

        print(f"  정렬 변경: {result}")
        return 'clicked' in str(result)

    def fetch_json(self, url, payload):
        """리뷰 API 데이터 가져오기.

        nfront WAF가 Selenium에서 생성한 XHR/fetch를 차단(HTTP 204)하므로,
        페이지 자체의 API 호출을 인터셉트하여 응답을 캡처하는 방식 사용.

        플로우:
          page=1: 인터셉터 설치 → 리뷰 탭 클릭 → 캡처
                  정렬 필요시: 인터셉터 재설치 → 정렬 링크 클릭 → 캡처
          page>=2: 인터셉터 설치 → 페이지네이션 클릭 → 캡처
        """
        if not self.driver:
            print("Error: 세션이 없습니다. login()을 먼저 호출하세요.")
            return None

        page = payload.get("page", 1)
        sort_type = payload.get("reviewSearchSortType", "REVIEW_RANKING")

        if page == 1:
            # 첫 페이지: 리뷰 탭 클릭으로 초기 로드
            self.install_interceptor()
            self.trigger_review_load(page=1)
            result = self.get_captured_reviews(wait_seconds=8)

            # 기본 정렬이 아닌 경우: UI에서 정렬 변경
            if sort_type != 'REVIEW_RANKING':
                print(f"  정렬 변경 중: {sort_type}")
                self.install_interceptor()
                if self.change_sort(sort_type):
                    result = self.get_captured_reviews(wait_seconds=10)
                else:
                    print("  Warning: 정렬 변경 실패, 기본 정렬로 진행")

            return result
        else:
            # 2페이지 이후: 페이지네이션 클릭
            self.install_interceptor()
            self.trigger_review_load(page=page)
            return self.get_captured_reviews(wait_seconds=8)

    def close(self):
        """브라우저 종료"""
        if self.driver:
            _close_driver(self.driver)
            self.driver = None


def main():
    parser = argparse.ArgumentParser(description="네이버 Selenium 로그인 쿠키 추출기")
    parser.add_argument("--id", help="네이버 아이디 (.env 대신 직접 지정)")
    parser.add_argument("--pw", help="네이버 비밀번호 (.env 대신 직접 지정)")
    parser.add_argument("--output", "-o", default=COOKIE_OUTPUT, help=f"출력 파일 (기본: {COOKIE_OUTPUT})")
    args = parser.parse_args()

    # 자격증명 로드: 인자 > .env
    naver_id = args.id
    naver_pw = args.pw

    if not naver_id or not naver_pw:
        env_id, env_pw = load_env()
        naver_id = naver_id or env_id
        naver_pw = naver_pw or env_pw

    if not naver_id or not naver_pw:
        print("Error: 네이버 ID/PW가 필요합니다.")
        print(f"  방법 1: {os.path.join(SKILL_DIR, '.env')} 파일에 NAVER_ID, NAVER_PW 설정")
        print("  방법 2: --id, --pw 인자로 직접 지정")
        sys.exit(1)

    print(f"네이버 로그인: {naver_id[:2]}{'*' * (len(naver_id) - 2)}")

    cookie_str = naver_login(naver_id, naver_pw)
    if not cookie_str:
        print("쿠키 추출 실패")
        sys.exit(1)

    # 파일 저장
    with open(args.output, "w") as f:
        f.write(cookie_str)
    print(f"쿠키 저장: {args.output}")


if __name__ == "__main__":
    main()
