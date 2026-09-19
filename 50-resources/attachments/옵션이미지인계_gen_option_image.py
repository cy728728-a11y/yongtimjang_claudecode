# -*- coding: utf-8 -*-
"""
옵션 이미지 재생성 테스트 (실버 강화형 1장).
모델: gpt-image-2 (고정). 엔드포인트: /v1/images/edits (원본 사진 기반 편집 - 제품 왜곡 방지).

사용법:
    python gen_option_image.py <입력이미지경로> <출력이미지경로>
"""
import os
import sys
from pathlib import Path

import requests

ENV_DIR = Path(r"C:\Users\workspace\.claude\skills\smartstore-brand\scripts")
MODEL = "gpt-image-2"


def load_env_file(path):
    """python-dotenv 없이 .env 파일에서 KEY=VALUE 를 os.environ 에 채워 넣는다."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

PROMPT = (
    "Use the attached product photo as the exact reference. "
    "Do NOT redesign, restyle, or change the product's shape, proportions, parts, or materials in any way - "
    "this must remain the identical physical stainless steel beverage dispenser, just photographed from a "
    "slightly different camera angle. "
    "Camera angle: rotate the product about 15 degrees to the left from a straight-on, eye-level view. "
    "Keep it a clean e-commerce studio product shot on a soft light blue gradient background, no clutter, "
    "no Chinese brand logo or Chinese text anywhere. "
    "Overlay clean Korean sans-serif text only (no Chinese characters): "
    "1) Bottom banner: \"단일 헤드 8리터 - 두꺼운 유형 - {color}\" "
    "2) Left side vertical measurement line: \"높이 58CM\" "
    "3) Two bottom dimension callouts near the base: \"폭 35CM\" and \"길이 26CM\" "
    "4) Small badge near the faucet: \"스테인리스 수도꼭지 업그레이드\" "
    "All Korean text spelling must be exactly correct and crisp."
)


def main():
    if len(sys.argv) < 3:
        print("사용법: python gen_option_image.py <입력이미지경로> <출력이미지경로>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    color = sys.argv[3] if len(sys.argv) > 3 else "실버"  # 색상 라벨 (실버/골드)

    if not input_path.exists():
        print(f"입력 이미지 없음: {input_path}")
        sys.exit(1)

    # --- 키 로드 ---
    load_env_file(ENV_DIR / ".env")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print(f"OPENAI_API_KEY 없음. {ENV_DIR / '.env'} 확인 필요.")
        sys.exit(1)

    try:
        print(f"{MODEL} 옵션 이미지 편집 생성 중... (30~90초)")
        with open(input_path, "rb") as f:
            resp = requests.post(
                "https://api.openai.com/v1/images/edits",
                headers={"Authorization": f"Bearer {api_key}"},
                data={"model": MODEL, "prompt": PROMPT.format(color=color), "size": "1024x1024", "n": 1},
                files={"image": (input_path.name, f, "image/jpeg")},
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

        import base64
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as out:
            out.write(base64.b64decode(b64))

        print(f"완료: {output_path}")

    except requests.exceptions.Timeout:
        print("타임아웃: API 응답이 너무 오래 걸립니다. 다시 시도해주세요.")
        sys.exit(1)
    except Exception as e:
        print(f"예외 발생: {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
