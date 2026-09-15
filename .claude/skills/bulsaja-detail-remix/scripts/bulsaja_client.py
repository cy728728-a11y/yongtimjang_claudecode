# -*- coding: utf-8 -*-
"""불사자 MCP 클라이언트 — 상세페이지 리믹스 전용.

전송(open/call_tool/close)은 이 스킬 폴더 안에 벤더링된 `mcp_transport.py`를
쓴다(워크스페이스 공용 라이브러리 의존 없음 — 이 스킬 폴더만 복사해도 그대로
동작하도록, 2026-09-04 수강생 배포 준비).

**어떤 불사자 계정을 쓸지는 하드코딩하지 않는다.** `scripts/.env`의
`BULSAJA_ACCOUNT_KEY`에 적힌 이름으로 `~/.claude.json`의 `mcpServers`를 찾는다
(값이 없으면 기본값 "bulsaja"). 계정이 여러 개인 사람(예: 마켓용/개인용을
따로 씀)은 반드시 자기 상황에 맞는 이름을 `.env`에 지정해야 한다 — 처음 쓸 때
`scripts/.env.example`을 `scripts/.env`로 복사해서 채우면 된다.

도구 3종(find_by_code / image_upload_prepare / detail_apply)은 2026-09-01 실제
상품으로 검증된 실측 스키마를 그대로 쓴다(문서화가 안 돼 있던 값들).
"""
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

from mcp_transport import BulsajaMCP as _Transport
from mcp_transport import load_config as _load_config

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ACCOUNT_KEY = "bulsaja"


def _load_account_config():
    """scripts/.env 의 BULSAJA_ACCOUNT_KEY(없으면 기본값)로 (url, auth, account_key) 반환."""
    load_dotenv(SCRIPT_DIR / ".env")
    account_key = os.getenv("BULSAJA_ACCOUNT_KEY", DEFAULT_ACCOUNT_KEY).strip()
    url, auth = _load_config(account_key)
    return url, auth, account_key


class DetailRemixMCP(_Transport):
    """상세페이지 리믹스 전용 도구 3종. 어느 불사자 계정을 쓸지는 .env로 정한다."""

    def __init__(self):
        url, auth, self.account_key = _load_account_config()
        super().__init__(url=url, auth=auth)

    def find_product_id(self, code):
        """판매자상품코드 또는 불사자코드 → productId. 못 찾으면 RuntimeError."""
        r = self.call_tool("bulsaja_product_find_by_code", {"codes": [code]})
        # 실측(2026-09-01): 응답 키는 '항목'(한국어) — {success, 개수, 더있음, 항목:[...]}
        items = r if isinstance(r, list) else (
            r.get("항목") or r.get("items") or r.get("products") or r.get("data") or []
        )
        if not items:
            raise RuntimeError(f"상품코드 '{code}' 를 찾지 못했습니다: {str(r)[:300]}")
        first = items[0]
        pid = first.get("productId") or first.get("id")
        if not pid:
            raise RuntimeError(f"productId 없음: {str(first)[:300]}")
        return pid

    def request_upload_ticket(self, product_id, files):
        """files: [{clientId, sha256, sizeBytes}, ...]. purpose="detail" 고정."""
        return self.call_tool("bulsaja_image_upload_prepare", {
            "productId": product_id, "purpose": "detail", "files": files,
        })

    def apply_detail(self, product_id, html, image_replacements):
        """confirm:false → confirmationToken 확인 → confirm:true 2단계 반영."""
        base = {"productId": product_id, "html": html,
                "imageReplacements": image_replacements, "confirm": False}
        pre = self.call_tool("bulsaja_detail_apply", base)
        token = pre.get("confirmationToken")
        if not token:
            raise RuntimeError(f"확인토큰 없음: {str(pre)[:300]}")
        return self.call_tool(
            "bulsaja_detail_apply",
            {**base, "confirm": True, "confirmationToken": token},
        )


# ---- 실제 파일 업로드 (MCP 프로토콜 밖 — 발급받은 티켓으로 직접 HTTP POST) --------
#
# 실측(2026-09-01) bulsaja_image_upload_prepare 응답 스키마:
#   {"success": true,
#    "upload": {"url": "https://api.bulsaja.com/mcp/assets", "method": "POST",
#               "fileField": "image", "ticketHeader": "X-MCP-Upload-Ticket",
#               "maxBytesPerFile": 8388608},
#    "tickets": [{"clientId": "...", "ticket": "mcpup_...", "expiresInSeconds": 300}]}
# 업로드 주소·필드명·티켓헤더는 전부 "upload" 블록이 알려준다(고정 추측 불필요) —
# 파일 자체는 multipart form의 upload.fileField 이름으로, 티켓 문자열은
# upload.ticketHeader 라는 HTTP 헤더로 보낸다.
_RESULT_URL_KEYS = ("url", "fileUrl", "resultUrl", "cdnUrl", "publicUrl", "imageUrl")


def _find_ticket_for(ticket_response, client_id):
    """prepare 응답에서 clientId 에 해당하는 티켓 항목을 찾는다."""
    entries = ticket_response.get("tickets") or []
    if not entries:
        raise RuntimeError(f"업로드 티켓에 tickets 없음: {str(ticket_response)[:500]}")
    for e in entries:
        if e.get("clientId") == client_id:
            return e
    if len(entries) == 1:
        return entries[0]
    raise RuntimeError(f"clientId '{client_id}' 에 맞는 티켓을 못 찾음: {str(entries)[:500]}")


def upload_file_with_ticket(ticket_response, client_id, file_path):
    """image_upload_prepare 응답이 알려준 업로드 주소로 파일을 multipart 업로드하고
    최종 이미지 URL을 반환한다. 파일 필드명·업로드 주소·티켓 헤더명은 응답의
    "upload" 블록에서 그대로 읽는다(하드코딩하지 않음).
    """
    upload_spec = ticket_response.get("upload") or {}
    upload_url = upload_spec.get("url")
    file_field = upload_spec.get("fileField") or "file"
    ticket_header = upload_spec.get("ticketHeader")
    if not upload_url or not ticket_header:
        raise RuntimeError(f"upload 블록에 url/ticketHeader 없음: {str(ticket_response)[:500]}")

    entry = _find_ticket_for(ticket_response, client_id)
    ticket = entry.get("ticket")
    if not ticket:
        raise RuntimeError(f"티켓 항목에 ticket 값 없음: {str(entry)[:500]}")

    content_type = "image/jpeg" if Path(file_path).suffix.lower() in (".jpg", ".jpeg") else "image/png"
    with open(file_path, "rb") as f:
        files = {file_field: (Path(file_path).name, f, content_type)}
        resp = requests.post(
            upload_url, headers={ticket_header: ticket}, files=files, timeout=120)

    if resp.status_code not in (200, 201, 204):
        raise RuntimeError(f"업로드 실패 HTTP {resp.status_code}: {resp.text[:500]}")

    try:
        body = resp.json()
    except ValueError:
        raise RuntimeError(f"업로드 응답이 JSON이 아님: {resp.text[:500]}")

    result_url = next((body[k] for k in _RESULT_URL_KEYS if body.get(k)), None)
    if not result_url:
        raise RuntimeError(f"업로드는 성공했지만 최종 이미지 URL을 못 찾음: {str(body)[:500]}")
    return result_url
