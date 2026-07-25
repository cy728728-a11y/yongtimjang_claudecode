# -*- coding: utf-8 -*-
"""
상품 이미지의 배경만 프로급 스튜디오 톤으로 교체한 1:1 이커머스 썸네일 생성.
모델: OpenAI gpt-image-2 (고정). 엔드포인트: /v1/images/edits.

사용법:
    python thumbnail_bg_replace.py "<입력이미지>" ["<출력경로>"]
Windows 콘솔: PYTHONIOENCODING=utf-8 PYTHONUTF8=1 로 실행.
"""
import os
import sys
import base64
from pathlib import Path

import requests
from dotenv import load_dotenv
from PIL import Image

SCRIPT_DIR = Path(__file__).parent
MODEL = "gpt-image-2"  # 고정 — 다른 모델 사용 금지 (용팀장님 지시)

PROMPT = (
    "High-end E-commerce Thumbnail: 1:1 Aspect Ratio, 1000x1000px. Replace background only. "
    "Product placed in a professional photography studio. The backdrop is a seamless, desaturated "
    "color randomly selected from the following palette (Milk Tea #FDF4E1, Powder Yellow #FFF8DC, "
    "Sand Beige #FFEBCD, Sweet Peach #FFE4E1, Apple Mango #FFEFD5, Biscuit #FFE4C4, Lemon Chiffon "
    "#FFFACD, Peach Puff #FFDAB9, Sky Blue #F0FFFF, Mist Green #E0FFFF, Mint White #F5FFFA, Cloud "
    "White #F8F8FF, Lavender Grey #E6E6FA, Green Tea #F0FFF0, Ice White #F8F8FF). Use soft cinematic "
    "lighting from top-left to create a realistic, long soft-edged drop shadow to the bottom-right "
    "for a 3D effect. The product occupies 85% of the frame, presented in a 45-degree quarter view "
    "for maximum visibility. Hyper-realistic studio photography style with sharp focus and natural "
    "depth of field. Keep the original product image intact. Do not add any text or logos on the image."
)


def main():
    # --- 인자 파싱 ---
    if len(sys.argv) < 2:
        print("❌ 사용법: python thumbnail_bg_replace.py \"<입력이미지>\" [\"<출력경로>\"]")
        sys.exit(1)
    input_path = sys.argv[1]
    if len(sys.argv) >= 3:
        output_path = sys.argv[2]
    else:
        p = Path(input_path)
        output_path = str(p.with_name(p.stem + "-thumb.png"))

    # --- 키 로드 ---
    load_dotenv(SCRIPT_DIR / ".env")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY가 없습니다.")
        print(f"   {SCRIPT_DIR / '.env'} 파일에 OPENAI_API_KEY=sk-... 를 저장하세요.")
        sys.exit(1)

    if not os.path.exists(input_path):
        print(f"❌ 입력 이미지를 찾을 수 없습니다: {input_path}")
        sys.exit(1)

    print(f"📖 입력 로드: {input_path}")
    try:
        with open(input_path, "rb") as f:
            files = {"image": ("input.png", f, "image/png")}
            data = {
                "model": MODEL,
                "prompt": PROMPT,
                "size": "1024x1024",  # 지원 정사각 → 이후 1000으로 리사이즈
                "n": "1",
            }
            print(f"🤖 {MODEL} 배경 교체 중... (30~90초 소요)")
            resp = requests.post(
                "https://api.openai.com/v1/images/edits",
                headers={"Authorization": f"Bearer {api_key}"},
                files=files,
                data=data,
                timeout=300,
            )

        if resp.status_code != 200:
            print(f"❌ API 오류: {resp.status_code}\n{resp.text[:1000]}")
            sys.exit(1)

        payload = resp.json()
        b64 = payload["data"][0].get("b64_json")
        if not b64:
            print(f"❌ 응답에 이미지가 없습니다(안전필터 등): {str(payload)[:500]}")
            sys.exit(1)

        raw_path = SCRIPT_DIR / "_raw_1024.png"
        with open(raw_path, "wb") as out:
            out.write(base64.b64decode(b64))

        img = Image.open(raw_path).convert("RGB")
        if img.size != (1000, 1000):
            img = img.resize((1000, 1000), Image.LANCZOS)
        img.save(output_path, "PNG")
        try:
            raw_path.unlink()  # 임시파일 정리
        except OSError:
            pass

        print(f"✅ 완료: {output_path}  ({img.size[0]}x{img.size[1]})")

    except requests.exceptions.Timeout:
        print("❌ 타임아웃: API 응답이 너무 오래 걸립니다. 다시 시도해주세요.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 예외 발생: {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
