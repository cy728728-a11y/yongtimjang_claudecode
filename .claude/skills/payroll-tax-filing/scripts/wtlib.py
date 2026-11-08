# -*- coding: utf-8 -*-
"""위택스(엣지 9222) 부착 헬퍼."""
import time
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By


def attach():
    o = Options()
    o.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    d = webdriver.Edge(options=o)
    for h in d.window_handles:
        d.switch_to.window(h)
        if "wetax.go.kr" in d.current_url:
            return d
    return d
