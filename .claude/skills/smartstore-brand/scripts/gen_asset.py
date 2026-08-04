# -*- coding: utf-8 -*-
"""
스마트스토어 브랜드 에셋 생성 (로고 / 모바일 배너 / PC 배너).
모델: OpenAI gpt-image-2 (고정, 용팀장님 지시). 엔드포인트: /v1/images/generations.
결과물 한 장만 저장 (크롭 전 원본은 저장하지 않음).

사용법:
    python gen_asset.py <mode> "<마켓명>" ["<출력경로>"]
    mode: logo | mobile | pc
      logo   -> 1300x1300 정사각 로고
      mobile -> 750x240 모바일 배너 (3.125:1)
      pc     -> 1280x200 PC 배너 (6.4:1)
    출력경로 생략 시 50-resources/attachments/ 아래 자동 명명.

Windows 콘솔: PYTHONIOENCODING=utf-8 PYTHONUTF8=1 로 실행.
"""
import os
import sys
import base64
from pathlib import Path

import requests
from dotenv import load_dotenv
from PIL import Image

# OpenAI 키: 이 스킬의 scripts/.env 를 우선 사용
# (구 thumbnail-bg-replace 스킬은 삭제됨 — 있으면 폴백으로 읽음)
ENV_DIR = Path(__file__).resolve().parent
LEGACY_ENV_DIR = Path(r"C:\Users\workspace\.claude\skills\thumbnail-bg-replace\scripts")
ATTACH_DIR = Path(r"C:\Users\workspace\50-resources\attachments")
MODEL = "gpt-image-2"  # 고정 — 다른 모델 사용 금지 (용팀장님 지시)

MESSAGE = "안심하고 맡기는 쇼핑"   # 배너 서브 메시지
SLOGAN = "안심하고 맡기세요"        # 로고 슬로건


def build_prompt(mode, store_name):
    """모드별 gpt-image-2 프롬프트 생성."""
    if mode == "logo":
        return (
            "Design a clean, premium logo for a Korean online shopping mall (Naver Smart Store). "
            f"Store name (Korean): \"{store_name}\". Secondary slogan (Korean): \"{SLOGAN}\". "
            "REQUIREMENTS: "
            f"1) The store name \"{store_name}\" is the DOMINANT visual element - bold, modern Korean "
            "lettering (wordmark), perfectly spelled and crisp. "
            f"2) Add the small phrase \"{SLOGAN}\" beneath it as a secondary line, only if it fits "
            "naturally. "
            "3) Include ONE simple, minimal icon or symbol that pairs with the wordmark - subtle, not "
            "too literal, not cluttered. "
            "4) Style: flat vector illustration, sharp clean lines. No photo-realistic elements, no 3D, "
            "no mockups or frames. "
            "5) Layout: centered, square 1:1 composition, plenty of white space. "
            "6) Background: white or a very light neutral tone. "
            "7) Color palette: 2-3 colors that feel warm, kind and trustworthy (soft blues / greens / "
            "warm neutrals). "
            "8) Minimal enough to work small as a store profile icon - avoid tiny detail or clutter. "
            "All Korean text spelling must be exactly correct."
        )

    # 배너 공통 헤더
    head = (
        "Design a clean, premium main banner for a Korean online shopping mall (Naver Smart Store). "
        f"Store name (Korean): \"{store_name}\". Main supporting message (Korean): \"{MESSAGE}\". "
        "It is a general online store covering many categories. The tone is warm, kind and trustworthy. "
        "REQUIREMENTS: "
        f"1) The store name \"{store_name}\" must be the most prominent, largest, boldest Korean text, "
        "perfectly spelled, crisp and highly legible. "
        f"2) Include the message \"{MESSAGE}\" as clear secondary Korean text, large and easy to read. "
        "3) Add simple, relevant flat vector icons matching an online shopping / delivery theme "
        "(e.g. box, delivery truck, shield) - subtle, clean, NOT busy. "
    )
    tail = (
        "5) Background: white or soft light color in a warm trustworthy tone (soft blue or soft green). "
        "6) Text large and crisp for display; avoid tiny cluttered elements. "
        "7) Style: flat, modern, vector-like, no photorealistic mockups, no 3D. No border or frame. "
        "All Korean text spelling must be exactly correct."
    )

    if mode == "mobile":
        layout = (
            "4) Wide horizontal banner composition (about 3:1). CRITICAL VERTICAL PLACEMENT: place ALL "
            "text and ALL icons inside the middle third of the image height, VERTICALLY CENTERED on the "
            "exact middle line of the canvas. The top third and the bottom third of the canvas must be "
            "COMPLETELY EMPTY background - no text, no icons, no decorative leaves, nothing. The empty "
            "margin above and below must be EQUAL in height. Do not push the composition upward or "
            "downward; the visual center of everything must sit exactly at the vertical midpoint. "
        )
    else:  # pc
        layout = (
            "4) VERY WIDE and THIN horizontal banner (about 6.4:1). Lay out the store name, the message "
            "and the icons together in ONE single horizontal row, all on the same eye level, spread "
            "across the width. CRITICAL VERTICAL PLACEMENT: that single row must be VERTICALLY CENTERED "
            "on the exact middle line of the canvas, confined to a thin central strip about one sixth of "
            "the canvas height. Everything above and below that thin strip must be COMPLETELY EMPTY "
            "background - no text, no icons, no decorative elements, nothing. The empty margin above and "
            "below must be EQUAL in height. Do not push the composition upward or downward; the visual "
            "center of the row must sit exactly at the vertical midpoint. "
        )
    return head + layout + tail


def content_center_y(img, threshold=18):
    """
    이미지에서 배경이 아닌 '내용'(글자·아이콘)이 차지하는 세로 범위의 중심을 반환.

    배경색은 네 모서리 픽셀의 중앙값으로 추정하고, 각 행마다 배경과
    threshold 이상 차이나는 픽셀 수를 세어 내용 유무를 판단한다.
    내용을 못 찾으면 이미지 정중앙으로 폴백.
    """
    try:
        gray = img.convert("L")
        w, h = gray.size
        px = gray.load()

        # 네 모서리로 배경 밝기 추정
        corners = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
        bg = sorted(corners)[len(corners) // 2]

        # 가로로 듬성듬성 샘플링 (속도)
        step = max(1, w // 400)
        min_pixels = max(3, (w // step) // 100)  # 노이즈 무시 임계

        rows = [
            y for y in range(h)
            if sum(1 for x in range(0, w, step) if abs(px[x, y] - bg) > threshold) >= min_pixels
        ]
        if not rows:
            return h / 2
        return (rows[0] + rows[-1]) / 2
    except Exception:
        # 어떤 이유로든 실패하면 안전하게 정중앙 사용
        return img.size[1] / 2


# 모드별 설정: (생성 사이즈, 출력 W, 출력 H, 파일명 접미사)
SPECS = {
    "logo":   {"gen": "1024x1024", "out": (1300, 1300), "suffix": "_logo"},
    "mobile": {"gen": "1536x1024", "out": (750, 240),   "suffix": "_모바일배너_750x240"},
    "pc":     {"gen": "1536x1024", "out": (1280, 200),  "suffix": "_PC배너_1280x200"},
}


def main():
    if len(sys.argv) < 3:
        print("사용법: python gen_asset.py <logo|mobile|pc> \"<마켓명>\" [\"<출력경로>\"]")
        sys.exit(1)

    mode = sys.argv[1].strip().lower()
    store_name = sys.argv[2].strip()
    if mode not in SPECS:
        print(f"알 수 없는 mode: {mode} (logo|mobile|pc 중 하나)")
        sys.exit(1)

    spec = SPECS[mode]
    if len(sys.argv) >= 4:
        output_path = sys.argv[3]
    else:
        ATTACH_DIR.mkdir(parents=True, exist_ok=True)
        output_path = str(ATTACH_DIR / f"{store_name}{spec['suffix']}.png")

    # --- 키 로드 ---
    load_dotenv(ENV_DIR / ".env")
    if not os.getenv("OPENAI_API_KEY"):
        load_dotenv(LEGACY_ENV_DIR / ".env")  # 구 경로 폴백
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print(f"OPENAI_API_KEY 없음. {ENV_DIR / '.env'} 에 OPENAI_API_KEY=sk-... 저장 필요.")
        sys.exit(1)

    prompt = build_prompt(mode, store_name)

    try:
        print(f"{MODEL} {mode} 생성 중... (30~90초)")
        resp = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": MODEL, "prompt": prompt, "size": spec["gen"], "n": 1},
            timeout=300,
        )
        if resp.status_code != 200:
            print(f"API 오류: {resp.status_code}\n{resp.text[:1000]}")
            sys.exit(1)

        payload = resp.json()
        b64 = payload["data"][0].get("b64_json")
        if not b64:
            print(f"응답에 이미지 없음(안전필터 등): {str(payload)[:500]}")
            sys.exit(1)

        raw_path = Path(output_path).with_suffix(".raw.png")
        with open(raw_path, "wb") as out:
            out.write(base64.b64decode(b64))

        img = Image.open(raw_path).convert("RGB")
        out_w, out_h = spec["out"]

        if mode == "logo":
            # 정사각: 그대로 리사이즈
            final = img.resize((out_w, out_h), Image.LANCZOS)
        else:
            # 배너: 콘텐츠(글자·아이콘)의 세로 중심을 기준으로 밴드 크롭 후 리사이즈.
            # 생성물이 위/아래로 치우쳐도 내용이 잘리지 않도록 중심을 잡아준다.
            w, h = img.size
            target_ratio = out_w / out_h
            band_h = min(h, int(round(w / target_ratio)))
            center = content_center_y(img)
            top = int(round(center - band_h / 2))
            top = max(0, min(top, h - band_h))  # 이미지 밖으로 나가지 않게 보정
            cropped = img.crop((0, top, w, top + band_h))
            final = cropped.resize((out_w, out_h), Image.LANCZOS)

        final.save(output_path, "PNG")

        try:
            raw_path.unlink()  # 임시파일 정리 (원본은 남기지 않음)
        except OSError:
            pass

        print(f"완료: {output_path}  ({out_w}x{out_h})")

    except requests.exceptions.Timeout:
        print("타임아웃: API 응답이 너무 오래 걸립니다. 다시 시도해주세요.")
        sys.exit(1)
    except Exception as e:
        print(f"예외 발생: {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
