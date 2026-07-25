# -*- coding: utf-8 -*-
"""용쌤1-1 100건 썸네일 배경교체 배치 생성 (로컬 생성 단계만).

products.json 의 각 상품 대표 썸네일을 내려받아 gpt-image-2 로 배경만
스튜디오 톤으로 교체한 1000x1000 PNG 를 만든다. 불사자 업로드는 별도 단계.

- 모델: gpt-image-2 고정 (용팀장님 지시 — 다른 모델 금지)
- 체크포인트: gen_status.json (성공 건 스킵 → 중단·재개 안전)
- 전역 완료 대장: thumbnail-done.json — 과거 run에서 이미 썸네일 교체한 상품은
  생성 자체를 skip (API 비용 절약). --ignore-ledger 로 강제 재작업 가능.
- 병렬: 기본 3워커, 429/5xx 지수 백오프 재시도

사용: python stage2_gen.py --run-dir <RUN> --account bulsaja|bulsaja-yongssaem
      [--limit N] [--workers 3] [--ignore-ledger]
      (--account 는 필수 — BULSAJA_ACCOUNT 환경변수로 대체 가능.
       계정이 틀리면 대장 대조가 무력화되어 전량 재생성 과금이 나므로 기본값 없음)
"""
import argparse
import base64
import io
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from PIL import Image

# 전역 완료 대장 (thumbnail-bg-replace 스킬 공용 모듈)
LEDGER_SCRIPTS = r"C:\Users\workspace\.claude\skills\thumbnail-bg-replace\scripts"
sys.path.insert(0, LEDGER_SCRIPTS)
import thumb_ledger  # noqa: E402


def load_env_key(env_path, key):
    """단순 .env 파서 (KEY=VALUE) — dotenv 의존성 제거."""
    try:
        for line in Path(env_path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return None

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SKILL_ENV = Path(r"C:\Users\workspace\.claude\skills\thumbnail-bg-replace\scripts\.env")
MODEL = "gpt-image-2"  # 고정
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

_lock = threading.Lock()


def load_status(path):
    """체크포인트 로드 (없으면 빈 dict)."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_status(path, status):
    """체크포인트 즉시 저장 (락 잡고 원자적으로)."""
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def download_thumb(url, dst):
    """원본 썸네일 다운로드 → PNG 정규화(1024 이하로 축소)."""
    r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content)).convert("RGB")
    if max(img.size) > 1024:
        img.thumbnail((1024, 1024), Image.LANCZOS)
    img.save(dst, "PNG")


def gen_one(api_key, src_png, out_png):
    """gpt-image-2 배경 교체 1건. 429/5xx 는 지수 백오프 재시도."""
    for attempt in range(4):
        try:
            with open(src_png, "rb") as f:
                resp = requests.post(
                    "https://api.openai.com/v1/images/edits",
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"image": ("input.png", f, "image/png")},
                    data={"model": MODEL, "prompt": PROMPT,
                          "size": "1024x1024", "n": "1"},
                    timeout=300,
                )
            if resp.status_code in (429, 500, 502, 503, 504):
                wait = 15 * (2 ** attempt)
                print(f"  [재시도] HTTP {resp.status_code} → {wait}초 대기")
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                raise RuntimeError(f"API {resp.status_code}: {resp.text[:200]}")
            b64 = resp.json()["data"][0].get("b64_json")
            if not b64:
                raise RuntimeError("응답에 이미지 없음(안전필터 가능)")
            img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
            if img.size != (1000, 1000):
                img = img.resize((1000, 1000), Image.LANCZOS)
            img.save(out_png, "PNG")
            return
        except requests.exceptions.Timeout:
            print("  [재시도] 타임아웃")
            time.sleep(10)
    raise RuntimeError("재시도 소진")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--limit", type=int, default=0, help="이번 실행 처리 건수(0=전부)")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--account",
                    help="불사자 계정 키 (필수 — 또는 BULSAJA_ACCOUNT 환경변수)")
    ap.add_argument("--ignore-ledger", action="store_true",
                    help="완료 대장 무시하고 강제 재생성")
    args = ap.parse_args()

    # 계정 명시 필수 — 기본값으로 잘못 대조하면 skip 0건 → 전량 재생성 과금
    try:
        account = thumb_ledger.resolve_account(args.account, require=True)
    except RuntimeError as e:
        print(f"[오류] {e}")
        sys.exit(1)

    run = Path(args.run_dir)
    src_dir = run / "thumbs_src"
    gen_dir = run / "thumbs_gen"
    src_dir.mkdir(exist_ok=True)
    gen_dir.mkdir(exist_ok=True)
    status_path = run / "gen_status.json"

    api_key = os.getenv("OPENAI_API_KEY") or load_env_key(SKILL_ENV, "OPENAI_API_KEY")
    if not api_key:
        print("[오류] OPENAI_API_KEY 없음")
        sys.exit(1)

    with open(run / "products.json", encoding="utf-8") as f:
        products = json.load(f)
    status = load_status(status_path)

    # 전역 완료 대장: 과거 run에서 이미 작업한 상품은 생성 자체를 skip
    ledger_done = set()
    if not args.ignore_ledger:
        try:
            ledger_done = thumb_ledger.done_set(thumb_ledger.load_ledger(), account)
        except RuntimeError as e:
            print(f"[오류] {e}")
            print("대장이 깨진 상태로 진행하면 중복 작업 위험 → 중단. "
                  "무시하려면 --ignore-ledger")
            sys.exit(1)

    # run 체크포인트 성공 건 + 대장 완료 건 스킵 → 남은 것만
    todo = [p for p in products
            if status.get(p["productId"], {}).get("status") != "ok"
            and p["productId"] not in ledger_done]
    n_ledger_skip = sum(1 for p in products
                        if status.get(p["productId"], {}).get("status") != "ok"
                        and p["productId"] in ledger_done)
    if args.limit:
        todo = todo[:args.limit]
    print(f"대상 {len(todo)}건 (전체 {len(products)}, run완료 "
          f"{sum(1 for v in status.values() if v.get('status') == 'ok')}, "
          f"대장skip {n_ledger_skip} [계정 {account}])")

    def work(p):
        pid = p["productId"]
        try:
            thumbs = p.get("썸네일") or []
            if not thumbs:
                raise RuntimeError("원본 썸네일 없음")
            src = src_dir / f"{pid}.png"
            out = gen_dir / f"{pid}.png"
            if not src.exists():
                download_thumb(thumbs[0], src)
            gen_one(api_key, src, out)
            with _lock:
                status[pid] = {"status": "ok"}
                save_status(status_path, status)
            return pid, "ok", ""
        except Exception as e:
            with _lock:
                status[pid] = {"status": "fail", "error": str(e)[:200]}
                save_status(status_path, status)
            return pid, "fail", str(e)[:120]

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(work, p) for p in todo]
        for fut in as_completed(futs):
            pid, st, err = fut.result()
            done += 1
            mark = "OK" if st == "ok" else f"FAIL {err}"
            print(f"[{done}/{len(todo)}] {pid[-8:]} {mark}", flush=True)

    ok = sum(1 for v in status.values() if v.get("status") == "ok")
    fail = sum(1 for v in status.values() if v.get("status") == "fail")
    print(f"###GEN### 완료 {ok} / 실패 {fail} / 전체 {len(products)}")


if __name__ == "__main__":
    main()
