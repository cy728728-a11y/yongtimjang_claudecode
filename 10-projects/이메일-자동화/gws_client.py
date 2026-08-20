#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gws CLI(@googleworkspace/cli) 래퍼 — cy728728@gmail.com 메일함 조작용.
Python subprocess에서는 gws.cmd 셸 shim을 못 찾으므로 node로 run.js를 직접 호출한다.
"""
import json
import subprocess

GWS_RUN_JS = r"C:\Users\woori\AppData\Roaming\npm\node_modules\@googleworkspace\cli\run.js"


class GwsError(Exception):
    """gws 명령 실행/파싱 실패."""


def _run_gws(args: list) -> dict:
    """node로 gws run.js를 직접 호출하고 JSON 결과를 dict로 반환."""
    cmd = ["node", GWS_RUN_JS] + args + ["--format", "json"]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", timeout=60
        )
    except subprocess.TimeoutExpired as e:
        raise GwsError(f"gws 명령 타임아웃: {' '.join(args)}") from e
    except OSError as e:
        raise GwsError(f"gws 명령 실행 실패(node/run.js 확인 필요): {e}") from e

    if result.returncode != 0:
        raise GwsError(f"gws 명령 실패(exit {result.returncode}): {result.stderr.strip()}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise GwsError(f"gws 응답 JSON 파싱 실패: {result.stdout[:200]}") from e


def list_unread_messages(max_count: int = 50) -> list:
    """cy728728 받은편지함의 안읽은 메일 목록(id/from/subject/date)을 반환."""
    data = _run_gws(["gmail", "+triage", "--query", "is:unread in:inbox", "--max", str(max_count)])
    return data.get("messages", [])


def read_message(message_id: str) -> dict:
    """메일 본문(body_text)·제목·발신자 등을 반환."""
    return _run_gws(["gmail", "+read", "--id", message_id, "--headers"])


def trash_message(message_id: str) -> None:
    """메일을 휴지통으로 이동한다(완전삭제 아님, 30일 복구 가능)."""
    _run_gws([
        "gmail", "users", "messages", "trash",
        "--params", json.dumps({"userId": "me", "id": message_id}),
    ])


def mark_read(message_id: str) -> None:
    """UNREAD 라벨을 제거해 다음 실행에서 재처리되지 않게 한다."""
    _run_gws([
        "gmail", "users", "messages", "modify",
        "--params", json.dumps({"userId": "me", "id": message_id}),
        "--json", json.dumps({"removeLabelIds": ["UNREAD"]}),
    ])


def forward_message(message_id: str, to_address: str) -> None:
    """메일을 지정 주소로 전달한다(gmail.send 스코프 필요)."""
    _run_gws(["gmail", "+forward", "--message-id", message_id, "--to", to_address])


def create_spreadsheet(title: str) -> str:
    """새 구글시트를 만들고 spreadsheetId를 반환."""
    data = _run_gws(["sheets", "spreadsheets", "create", "--json", json.dumps({"properties": {"title": title}})])
    return data["spreadsheetId"]


def append_log_row(spreadsheet_id: str, row: list) -> None:
    """로그 시트에 한 줄(row)을 추가한다."""
    _run_gws(["sheets", "+append", "--spreadsheet", spreadsheet_id, "--json-values", json.dumps([row])])
