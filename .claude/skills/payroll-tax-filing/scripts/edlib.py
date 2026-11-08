# -*- coding: utf-8 -*-
"""엣지(9222 디버그) 부착 헬퍼 — htlib 의 엣지판."""
import time
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from htlib import popup_text, accept, screen  # noqa: F401


def attach():
    o = Options()
    o.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    d = webdriver.Edge(options=o)
    for h in d.window_handles:
        d.switch_to.window(h)
        if "hometax.go.kr" in d.current_url:
            return d
    return d
