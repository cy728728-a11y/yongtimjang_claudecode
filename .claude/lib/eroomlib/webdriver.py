#!/usr/bin/env python3
"""봇 감지 우회 Chrome 드라이버 1벌.

두 계열을 통합한다(둘 다 selenium 을 함수 안에서 지연 import):
  create_driver(headless)                       — 봇 우회 기본 드라이버(WSL/Mac/Linux 자동 감지).
                                                   구 review-analyzer/cookie_extractor._create_driver.
  make_driver(headless, profile_dir, download_dir) — 전용 프로필 + 다운로드 경로 지정형.
                                                   구 sellerlife-keyword/common.make_driver.
  close_driver(driver)                          — 안전 종료(구 _close_driver).

봇 우회 공통: navigator.webdriver=undefined, AutomationControlled 비활성.
"""
import os
import platform
import time


def create_driver(headless=False):
    """Chrome WebDriver 생성 (WSL/Mac/Linux 자동 감지). 실패 시 None.

    (구 review-analyzer/cookie_extractor._create_driver 와 동일 동작.)
    """
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


def close_driver(driver):
    """WebDriver 안전 종료 (구 _close_driver)."""
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


def make_driver(headless=False, profile_dir=None, download_dir=None):
    """전용 프로필을 쓰는 Chrome 생성 (구 sellerlife-keyword/common.make_driver).

    profile_dir 를 고정하면 최초 1회 사람이 구글 로그인한 세션이 계속 남아
    이후 실행에서 비밀번호 입력 없이 통과한다 (구글 자동화 차단 회피).
    profile_dir 미지정 시 CWD 하위 임시 프로필을 쓴다(구 기본값은 스킬 폴더였음 —
    호출부가 항상 profile_dir 를 넘기므로 이 폴백은 사용되지 않음).
    """
    from selenium import webdriver

    profile_dir = profile_dir or os.path.join(os.getcwd(), "_chrome_profile")
    os.makedirs(profile_dir, exist_ok=True)

    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(f"--user-data-dir={profile_dir}")
    if headless:
        options.add_argument("--headless=new")

    if download_dir:
        os.makedirs(download_dir, exist_ok=True)
        options.add_experimental_option("prefs", {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        })

    try:
        driver = webdriver.Chrome(options=options)
    except Exception as e:
        msg = str(e)
        if "user data directory is already in use" in msg.lower():
            print("[오류] 이 프로필을 쓰는 Chrome 이 이미 떠 있습니다. 해당 창을 닫고 다시 실행하세요.")
        else:
            print(f"[오류] Chrome 실행 실패: {msg[:200]}")
        return None

    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
        )
    except Exception:
        pass

    if download_dir:
        try:
            driver.execute_cdp_cmd("Page.setDownloadBehavior",
                                   {"behavior": "allow", "downloadPath": download_dir})
        except Exception as e:
            print(f"[경고] 다운로드 경로 CDP 설정 실패: {e}")

    return driver
