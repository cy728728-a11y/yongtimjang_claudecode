# -*- coding: utf-8 -*-
"""홈택스 조작 공용 헬퍼 (디버그 크롬 9222 부착)."""
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By


def attach():
    o = Options()
    o.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    d = webdriver.Chrome(options=o)
    for h in d.window_handles:
        d.switch_to.window(h)
        if "hometax.go.kr" in d.current_url:
            return d
    return d


def popup_text(d):
    """떠 있는 팝업의 안내문만 뽑는다."""
    out = []
    for lay in d.find_elements(By.XPATH, "//*[contains(@class,'w2window')]"):
        try:
            if lay.is_displayed() and lay.text.strip():
                t = " | ".join(x for x in lay.text.strip().split("\n")
                               if x.strip() not in ("레이어 팝업", "레이어팝업시작", "알림", ""))
                if t and t not in out:
                    out.append(t)
        except Exception:
            continue
    return out


def accept(d, rounds=3, wait=2.0):
    """확인/예 계열 버튼(btn_confirm)을 눌러 팝업을 넘긴다. 누른 내용을 반환."""
    seen = []
    for _ in range(rounds):
        btns = [b for b in d.find_elements(By.XPATH, "//input[contains(@id,'btn_confirm')]")
                if b.is_displayed()]
        if not btns:
            break
        msg = popup_text(d)
        seen.extend(msg)
        d.execute_script("arguments[0].click();", btns[0])
        time.sleep(wait)
    return seen


def screen(d, n=1200):
    txt = d.find_element(By.TAG_NAME, "body").text
    i = txt.find("즐겨찾기")
    return txt[i:i + n] if i > 0 else txt[:n]
