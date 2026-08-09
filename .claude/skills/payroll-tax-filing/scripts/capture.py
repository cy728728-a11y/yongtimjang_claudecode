# -*- coding: utf-8 -*-
"""
홈택스 화면(납부서·접수증 등)을 전체 캡처해 월별 폴더에 PNG 로 저장한다.

  python capture.py "<저장폴더>" "<파일명접두사>"

디버그 크롬(9222)에 붙어, 홈택스 관련 창을 모두 훑어
'납부서/접수증' 성격의 창을 우선 캡처한다. 없으면 현재 창을 캡처.
"""
import sys, os, time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

KEYS = ("납부서", "접수증", "영수증", "고지", "전자납부")


def full_page_png(d, path):
    """CDP 로 페이지 전체 높이를 캡처한다(스크롤 잘림 방지)."""
    m = d.execute_cdp_cmd("Page.getLayoutMetrics", {})
    css = m.get("cssContentSize") or m["contentSize"]
    w, h = int(css["width"]), int(css["height"])
    h = min(h, 20000)
    shot = d.execute_cdp_cmd("Page.captureScreenshot", {
        "format": "png",
        "captureBeyondViewport": True,
        "clip": {"x": 0, "y": 0, "width": w, "height": h, "scale": 1},
    })
    import base64
    with open(path, "wb") as f:
        f.write(base64.b64decode(shot["data"]))
    return w, h


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    prefix = sys.argv[2] if len(sys.argv) > 2 else "캡처"
    os.makedirs(out_dir, exist_ok=True)

    o = Options()
    o.add_experimental_option("debuggerAddress", "127.0.0.1:9222")
    try:
        d = webdriver.Chrome(options=o)
    except Exception as e:
        print("크롬(9222) 부착 실패:", e, file=sys.stderr)
        sys.exit(1)

    targets = []
    for h in d.window_handles:
        try:
            d.switch_to.window(h)
            body = d.find_element(By.TAG_NAME, "body").text
            score = sum(1 for k in KEYS if k in body or k in d.title)
            targets.append((score, h, d.title))
        except Exception:
            continue

    if not targets:
        print("캡처할 창이 없습니다.", file=sys.stderr)
        sys.exit(1)

    targets.sort(reverse=True)
    saved = []
    for score, h, title in targets:
        if score == 0 and saved:
            break                      # 관련 창을 이미 찍었으면 나머지는 생략
        d.switch_to.window(h)
        time.sleep(0.5)
        name = "%s_%d.png" % (prefix, len(saved) + 1) if len(targets) > 1 else "%s.png" % prefix
        path = os.path.join(out_dir, name)
        try:
            w, hh = full_page_png(d, path)
            saved.append((path, w, hh, title))
        except Exception as e:
            print("캡처 실패(%s): %s" % (title, e), file=sys.stderr)

    for p, w, hh, t in saved:
        print("저장: %s  (%dx%d)  ← %s" % (p, w, hh, t))


if __name__ == "__main__":
    main()
