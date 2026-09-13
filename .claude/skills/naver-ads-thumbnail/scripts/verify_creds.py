#!/usr/bin/env python3
"""커머스API 자격증명 검증 — 앱을 하나 발급할 때마다 이걸로 확인한다.

스토어별 앱이 (1) 토큰이 나오는지 (2) 어느 채널에 붙었는지 (3) 상품 조회가 되는지
세 가지를 순서대로 찔러본다. 쓰기는 전혀 하지 않는다.

    .venv/bin/python3 .claude/skills/naver-ads-thumbnail/scripts/verify_creds.py
    .venv/bin/python3 ... --alias 오운웨이컴퍼니     # 한 곳만
"""
import argparse
import base64
import json
import sys
import time
from pathlib import Path

try:
    import bcrypt
    import requests
except ImportError as e:
    sys.exit(f"의존성 없음: {e}. `uv pip install --python .venv/bin/python bcrypt requests`")

BASE = "https://api.commerce.naver.com/external"
CREDS = Path.home() / ".eroom" / "naver-commerce.json"


def issue_token(client_id, client_secret):
    """bcrypt 전자서명으로 액세스 토큰 발급. secret 자체가 bcrypt salt 라 별도 생성 없음."""
    ts = int(time.time() * 1000)
    try:
        hashed = bcrypt.hashpw(f"{client_id}_{ts}".encode(), client_secret.encode())
    except ValueError as e:
        return None, f"시크릿 형식 오류(bcrypt salt 아님): {e}"
    try:
        r = requests.post(f"{BASE}/v1/oauth2/token", timeout=30, data={
            "client_id": client_id, "timestamp": ts,
            "client_secret_sign": base64.b64encode(hashed).decode(),
            "grant_type": "client_credentials", "type": "SELF"})
    except requests.RequestException as e:
        return None, f"네트워크 실패: {e}"
    if r.status_code != 200:
        return None, f"토큰 발급 실패 [{r.status_code}] {r.text[:200]}"
    return r.json()["access_token"], None


def check(store):
    """스토어 한 곳을 검증하고 사람이 읽는 한 줄로 요약."""
    alias = store.get("alias", "?")
    cid, sec = store.get("client_id", ""), store.get("client_secret", "")
    if not cid or not sec or cid.startswith("커머스"):
        return f"  {alias:16s} ⏳ 미발급 (client_id/secret 비어 있음)"

    tok, err = issue_token(cid, sec)
    if err:
        return f"  {alias:16s} ❌ {err}"
    H = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

    try:
        ch = requests.get(f"{BASE}/v1/seller/channels", headers=H, timeout=30)
        names = [c.get("name") for c in ch.json()] if ch.status_code == 200 else []
        pr = requests.post(f"{BASE}/v1/products/search", headers=H,
                           json={"page": 1, "size": 1}, timeout=30)
    except requests.RequestException as e:
        return f"  {alias:16s} ❌ 조회 실패: {e}"

    if pr.status_code != 200:
        return f"  {alias:16s} ⚠️  토큰 OK · 채널{names} · 상품조회 [{pr.status_code}] — 권한에 '상품' 추가 필요"
    total = pr.json().get("totalElements", "?")
    match = "✅" if alias in names else "⚠️ 채널명 불일치"
    return f"  {alias:16s} {match} 채널{names} · 상품 {total}건 조회 가능"


def main():
    ap = argparse.ArgumentParser(description="커머스API 스토어별 자격증명 검증")
    ap.add_argument("--alias", help="이 스토어만 검사")
    ap.add_argument("--creds", default=str(CREDS))
    args = ap.parse_args()

    try:
        data = json.loads(Path(args.creds).read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"자격증명 없음: {args.creds}\n"
                 f"~/.eroom/naver-commerce.json.example 를 복사해 채운다.")
    except json.JSONDecodeError as e:
        sys.exit(f"JSON 형식 오류: {e}")

    stores = data.get("stores", [])
    if args.alias:
        stores = [s for s in stores if s.get("alias") == args.alias]
        if not stores:
            sys.exit(f"'{args.alias}' 를 찾지 못했다.")

    print(f"커머스API 자격증명 검증 — {len(stores)}곳\n")
    ok = 0
    for s in stores:
        line = check(s)
        print(line, flush=True)
        if line.count("✅"):
            ok += 1
    print(f"\n사용 가능: {ok}/{len(stores)}")


if __name__ == "__main__":
    main()
