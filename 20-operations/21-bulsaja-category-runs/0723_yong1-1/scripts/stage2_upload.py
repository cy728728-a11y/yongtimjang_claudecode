# -*- coding: utf-8 -*-
"""생성된 썸네일을 불사자(용쌤 서버)에 업로드하고 대표이미지로 저장.

흐름(상품별): 업로드 티켓 발급 → multipart 전송 → CDN 주소 획득
→ 기존 썸네일 목록 조회 → [새 이미지 + 기존 목록] 으로 2단계 확인 저장.

- 체크포인트: upload_status.json (성공 건 스킵)
- 전역 완료 대장: 저장 성공 시 thumbnail-done.json 에 자동 기록
  → 이후 다른 run에서 같은 상품 재작업 방지
- 서버 라우팅: run_yong.py 래퍼로 실행 (BULSAJA_MCP_URL/TOKEN/ACCOUNT 환경변수)

사용:
  python run_yong.py python stage2_upload.py --run-dir <RUN> [--limit N] [--probe <productId>]
  (계정 명시 필수 — run_yong.py 경유 시 BULSAJA_ACCOUNT 자동 주입,
   직접 실행(용팀장 계정)이면 --account bulsaja 를 줄 것. 기본값 없음)
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SKILL_SCRIPTS = r"C:\Users\workspace\.claude\skills\bulsaja-category-fix\scripts"
sys.path.insert(0, SKILL_SCRIPTS)
from bulsaja_mcp import BulsajaMCP  # noqa: E402

# 전역 완료 대장 (thumbnail-bg-replace 스킬 공용 모듈)
LEDGER_SCRIPTS = r"C:\Users\workspace\.claude\skills\thumbnail-bg-replace\scripts"
sys.path.insert(0, LEDGER_SCRIPTS)
import thumb_ledger  # noqa: E402


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj):
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def sanitize(obj, depth=0):
    """응답 구조 확인용 — 값은 자르고 키/형태만 (토큰·티켓 노출 방지)."""
    if depth > 3:
        return "..."
    if isinstance(obj, dict):
        return {k: sanitize(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(v, depth + 1) for v in obj[:2]] + (["..."] if len(obj) > 2 else [])
    s = str(obj)
    return s[:80] + ("..." if len(s) > 80 else "")


def upload_image(mcp, product_id, png_path):
    """티켓 발급 → 고정 주소에 티켓 헤더로 multipart 전송 → CDN 주소 반환.

    prepare 응답 구조(실측):
      upload: {url, method, fileField, ticketHeader, maxBytesPerFile}
      tickets: [{clientId, ticket, expiresInSeconds}]
    """
    data = Path(png_path).read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    client_id = Path(png_path).stem[-16:] + "-thumb"
    r = mcp.call_tool("bulsaja_image_upload_prepare", {
        "productId": product_id, "purpose": "thumbnail",
        "files": [{"clientId": client_id, "sha256": sha,
                   "sizeBytes": len(data)}],
    })
    up = r.get("upload") or {}
    upload_url = up.get("url")
    file_field = up.get("fileField") or "image"
    ticket_header = up.get("ticketHeader") or "X-MCP-Upload-Ticket"
    tickets = r.get("tickets") or []
    if not upload_url or not tickets:
        raise RuntimeError(f"티켓 응답 파싱 실패: {list(r.keys())}")
    ticket = tickets[0].get("ticket")
    if not ticket:
        raise RuntimeError("티켓 없음")

    with open(png_path, "rb") as f:
        resp = requests.post(
            upload_url,
            headers={ticket_header: ticket},
            files={file_field: (f"{client_id}.png", f, "image/png")},
            timeout=120,
        )
    if resp.status_code >= 400:
        raise RuntimeError(f"업로드 HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        j = resp.json()
    except Exception:
        raise RuntimeError(f"업로드 응답 JSON 아님: {resp.text[:200]}")
    final_url = (j.get("url") or j.get("imageUrl") or j.get("cdnUrl")
                 or (j.get("data") or {}).get("url")
                 or j.get("이미지주소"))
    if not final_url:
        raise RuntimeError(f"CDN 주소 없음 (업로드응답 키: {list(j.keys())})")
    return final_url


def set_thumbnail(mcp, product_id, new_url):
    """기존 썸네일 목록 조회 → [새이미지 + 기존] 저장 (2단계 확인)."""
    cur = mcp.call_tool("bulsaja_thumbnail_update", {"productId": product_id})
    # 기존 목록 추출 (형태 유연 대응)
    existing = []
    for key in ("thumbnails", "현재썸네일", "후보", "candidates", "images"):
        v = cur.get(key)
        if isinstance(v, list) and v:
            existing = [x if isinstance(x, str) else
                        (x.get("url") or x.get("이미지주소") or "") for x in v]
            break
    existing = [u for u in existing if u and u != new_url]
    new_list = ([new_url] + existing)[:20]

    pre = mcp.call_tool("bulsaja_thumbnail_update", {
        "productId": product_id, "thumbnails": new_list, "confirm": False})
    token = pre.get("confirmationToken") or ""
    if not token:
        raise RuntimeError(f"확인토큰 없음: {str(sanitize(pre))[:200]}")
    fin = mcp.call_tool("bulsaja_thumbnail_update", {
        "productId": product_id, "thumbnails": new_list,
        "confirm": True, "confirmationToken": token})
    if not (fin.get("success") or fin.get("성공")):
        raise RuntimeError(f"저장 실패: {str(sanitize(fin))[:200]}")
    return len(new_list)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--probe", help="상품 1건 응답 구조 확인(업로드 티켓만, 저장 안 함)")
    ap.add_argument("--sleep", type=float, default=0.5)
    ap.add_argument("--account",
                    help="불사자 계정 키 (필수 — 또는 BULSAJA_ACCOUNT 환경변수)")
    args = ap.parse_args()
    # 계정 명시 필수 — 잘못된 계정으로 대장에 기록되면 이후 skip 판정이 틀어짐
    try:
        account = thumb_ledger.resolve_account(args.account, require=True)
    except RuntimeError as e:
        print(f"[오류] {e}")
        sys.exit(1)

    run = Path(args.run_dir)
    gen_dir = run / "thumbs_gen"
    status_path = run / "upload_status.json"
    gen_status = load_json(run / "gen_status.json", {})
    products = load_json(run / "products.json", [])
    status = load_json(status_path, {})

    mcp = BulsajaMCP()
    mcp.open()
    try:
        if args.probe:
            pid = args.probe
            png = gen_dir / f"{pid}.png"
            data = png.read_bytes()
            r = mcp.call_tool("bulsaja_image_upload_prepare", {
                "productId": pid, "purpose": "thumbnail",
                "files": [{"clientId": "probe-thumb",
                           "sha256": hashlib.sha256(data).hexdigest(),
                           "sizeBytes": len(data)}],
            })
            print("[prepare 응답 구조]")
            print(json.dumps(sanitize(r), ensure_ascii=False, indent=1))
            cur = mcp.call_tool("bulsaja_thumbnail_update", {"productId": pid})
            print("[thumbnail_update(조회) 응답 구조]")
            print(json.dumps(sanitize(cur), ensure_ascii=False, indent=1))
            return

        todo = [p for p in products
                if gen_status.get(p["productId"], {}).get("status") == "ok"
                and status.get(p["productId"], {}).get("status") not in ("ok", "skip")]
        if args.limit:
            todo = todo[:args.limit]
        print(f"업로드 대상 {len(todo)}건")

        for i, p in enumerate(todo, 1):
            pid = p["productId"]
            try:
                png = gen_dir / f"{pid}.png"
                url = upload_image(mcp, pid, png)
                n = set_thumbnail(mcp, pid, url)
                status[pid] = {"status": "ok", "url": url, "count": n}
                try:
                    # 전역 완료 대장 기록 — 이후 run에서 이 상품 skip
                    thumb_ledger.mark_done(account, pid, status="ok",
                                           run=run.name, url=url,
                                           name=p.get("상품명"))
                except Exception as le:
                    print(f"  [경고] 대장 기록 실패: {str(le)[:100]}")
                print(f"[{i}/{len(todo)}] {pid[-8:]} OK (총 {n}장)", flush=True)
            except Exception as e:
                status[pid] = {"status": "fail", "error": str(e)[:200]}
                print(f"[{i}/{len(todo)}] {pid[-8:]} FAIL {str(e)[:120]}", flush=True)
            save_json(status_path, status)
            time.sleep(args.sleep)

        ok = sum(1 for v in status.values() if v.get("status") == "ok")
        fail = sum(1 for v in status.values() if v.get("status") == "fail")
        print(f"###UPLOAD### 성공 {ok} / 실패 {fail}")
    finally:
        mcp.close()


if __name__ == "__main__":
    main()
