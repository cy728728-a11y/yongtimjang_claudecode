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

# OpenAI 키는 기존 썸네일 스킬의 .env 재사용
ENV_DIR = Path(r"C:\Users\workspace\.claude\skills\thumbnail-bg-replace\scripts")
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
            "4) Wide horizontal banner composition (about 3:1). Keep ALL text and key icons centered "
            "within the MIDDLE horizontal band of the image, leaving generous empty margin at the very "
            "top and very bottom so the center strip can be safely cropped to a 3:1 banner. "
        )
    else:  # pc
        layout = (
            "4) VERY WIDE and THIN horizontal banner (about 6.4:1). Lay out the store name, the message "
            "and the icons together in ONE single horizontal row, all on the same eye level, spread "
            "across the width. Keep everything within a THIN central horizontal strip, leaving large "
            "empty margin at the very top and very bottom so the center strip can be safely cropped to a "
            "very wide thin banner. "
        )
    return head + layout + tail


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
            # 배너: 가로폭 기준 중앙 밴드 크롭 후 목표 크기로 리사이즈
            w, h = img.size
            target_ratio = out_w / out_h
            band_h = int(round(w / target_ratio))
            top = max(0, (h - band_h) // 2)
            cropped = img.crop((0, top, w, min(h, top + band_h)))
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
