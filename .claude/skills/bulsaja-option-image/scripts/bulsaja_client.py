# -*- coding: utf-8 -*-
"""불사자 MCP 클라이언트 — 옵션 이미지 교체 전용.

전송은 이 폴더에 벤더링된 `mcp_transport.py`(bulsaja-detail-remix 와 동일 사본).
어느 계정을 쓸지는 `scripts/.env` 의 BULSAJA_ACCOUNT_KEY 또는 `--account` 인자로 정한다.

도구 4종 실측 스키마 (2026-09-16 실제 상품으로 검증):
- bulsaja_product_find_by_code  {codes:[...]} → {항목:[{productId,...}]}
- bulsaja_product_workdata      {productId, mode:"summary"} → {data:{uploadSkuProps, uploadSkus,...}}
- bulsaja_image_upload_prepare  {productId, purpose:"option", files:[{clientId,sha256,sizeBytes}]}
                                → {upload:{url,fileField,ticketHeader}, tickets:[{clientId,ticket}]}
- bulsaja_option_image_update   {productId, images:[{vid, imageUrl}]} → 1차: confirmationToken
                                → 2차: confirm:true + confirmationToken → {success, 변경수}
"""
import hashlib
import os
from pathlib import Path

import requests

from mcp_transport import BulsajaMCP as _Transport
from mcp_transport import load_config as _load_config

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ACCOUNT_KEY = "bulsaja"


def load_env_file(path):
    """python-dotenv 없이 .env 의 KEY=VALUE 를 os.environ 에 채운다(기존 값 우선)."""
    path = Path(path)
    if not path.exists():
        return
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception as e:  # .env 가 깨져도 실행은 계속 (키 없으면 뒤에서 명확히 실패)
        print(f"[경고] .env 읽기 실패: {e}")


def resolve_account_key(cli_value=None):
    load_env_file(SCRIPT_DIR / ".env")
    return (cli_value or os.getenv("BULSAJA_ACCOUNT_KEY") or DEFAULT_ACCOUNT_KEY).strip()


def load_config_by_key(account_key):
    """계정 이름으로만 ~/.claude.json 을 찾는다.

    mcp_transport.load_config 는 환경변수 BULSAJA_MCP_URL/TOKEN 이 있으면 계정 이름을
    무시하고 그 토큰을 쓴다. 이 PC 는 그 변수가 전역으로 박혀 있어(실측 2026-09-16)
    '용쌤' 을 지정해도 용팀장 계정으로 붙는 사고가 났다. 여기서는 잠시 걷어내고 찾는다.
    """
    saved = {k: os.environ.pop(k) for k in ("BULSAJA_MCP_URL", "BULSAJA_MCP_TOKEN") if k in os.environ}
    try:
        return _load_config(account_key)
    finally:
        os.environ.update(saved)


class OptionImageMCP(_Transport):
    """옵션 이미지 교체에 필요한 도구 4종."""

    def __init__(self, account_key=None):
        self.account_key = resolve_account_key(account_key)
        url, auth = load_config_by_key(self.account_key)
        super().__init__(url=url, auth=auth)

    def whoami(self):
        """연결된 계정 요약 한 줄 (닉네임·이메일). 쓰기 전에 반드시 찍는다."""
        r = self.call_tool("bulsaja_my_profile", {})
        return (r or {}).get("요약") or str(r)[:120]

    def find_product_id(self, code):
        """판매자상품코드(또는 불사자 상품ID 그대로) → productId."""
        if code.startswith("U01") and len(code) >= 26:
            return code  # 이미 불사자 상품 ID
        r = self.call_tool("bulsaja_product_find_by_code", {"codes": [code]})
        items = r if isinstance(r, list) else (r.get("항목") or r.get("items") or [])
        if not items:
            raise RuntimeError(f"상품코드 '{code}' 를 찾지 못했다: {str(r)[:300]}")
        pid = items[0].get("productId") or items[0].get("id")
        if not pid:
            raise RuntimeError(f"productId 없음: {str(items[0])[:300]}")
        return pid

    def workdata(self, product_id):
        r = self.call_tool("bulsaja_product_workdata", {"productId": product_id, "mode": "summary"})
        data = r.get("data") if isinstance(r, dict) else None
        if not data:
            raise RuntimeError(f"가공 현황 조회 실패: {str(r)[:300]}")
        return r

    def request_upload_ticket(self, product_id, files):
        return self.call_tool("bulsaja_image_upload_prepare", {
            "productId": product_id, "purpose": "option", "files": files,
        })

    def update_option_images(self, product_id, images):
        """images: [{vid, imageUrl}]. 확인키 2단계를 한 번에 처리한다."""
        base = {"productId": product_id, "images": images, "confirm": False}
        pre = self.call_tool("bulsaja_option_image_update", base)
        if isinstance(pre, dict) and pre.get("success"):
            return pre  # 확인 없이 바로 된 경우
        token = (pre or {}).get("confirmationToken") if isinstance(pre, dict) else None
        if not token:
            raise RuntimeError(f"확인키 없음: {str(pre)[:400]}")
        r = self.call_tool("bulsaja_option_image_update",
                           {**base, "confirm": True, "confirmationToken": token})
        if not (isinstance(r, dict) and r.get("success")):
            raise RuntimeError(f"옵션 이미지 수정 실패: {str(r)[:400]}")
        return r


# ---- 파일 업로드 (MCP 밖 — 발급받은 티켓으로 직접 HTTP POST) ------------------------
_RESULT_URL_KEYS = ("url", "fileUrl", "resultUrl", "cdnUrl", "publicUrl", "imageUrl")


def file_meta(path, client_id):
    p = Path(path)
    data = p.read_bytes()
    return {"clientId": client_id, "sha256": hashlib.sha256(data).hexdigest(), "sizeBytes": len(data)}


def upload_file_with_ticket(ticket_response, client_id, file_path):
    """prepare 응답의 upload 블록(주소·필드명·헤더명)을 그대로 읽어 업로드 → 최종 이미지 URL."""
    spec = ticket_response.get("upload") or {}
    url, field, header = spec.get("url"), spec.get("fileField") or "file", spec.get("ticketHeader")
    if not url or not header:
        raise RuntimeError(f"upload 블록에 url/ticketHeader 없음: {str(ticket_response)[:400]}")
    entry = next((t for t in ticket_response.get("tickets") or [] if t.get("clientId") == client_id), None)
    if not entry or not entry.get("ticket"):
        raise RuntimeError(f"'{client_id}' 티켓 없음: {str(ticket_response.get('tickets'))[:400]}")
    ctype = "image/jpeg" if Path(file_path).suffix.lower() in (".jpg", ".jpeg") else "image/png"
    with open(file_path, "rb") as f:
        resp = requests.post(url, headers={header: entry["ticket"]},
                             files={field: (Path(file_path).name, f, ctype)}, timeout=120)
    if resp.status_code not in (200, 201, 204):
        raise RuntimeError(f"업로드 실패 HTTP {resp.status_code}: {resp.text[:400]}")
    body = resp.json()
    out = next((body[k] for k in _RESULT_URL_KEYS if body.get(k)), None)
    if not out:
        raise RuntimeError(f"업로드 응답에 이미지 URL 없음: {str(body)[:400]}")
    return out
