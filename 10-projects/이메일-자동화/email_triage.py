#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
이메일 자동관리 — cy728728 수집함을 훑어 정크는 휴지통, 확인 필요 메일은 Daum으로 전달.
Windows 작업 스케줄러로 하루 4회(09/12/15/18시) 무인 실행됨.

사용법:
  python email_triage.py            # 실제 처리
  python email_triage.py --dry-run  # 분류 결과만 미리보기(휴지통/전달 실행 안 함)
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import gws_client
import classifier
import state

FORWARD_TO = "cy728@daum.net"


def load_env(env_path: Path) -> dict:
    """.env 파일을 파싱해 dict로 반환한다."""
    data = {}
    try:
        if not env_path.exists():
            return data
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            data[key.strip()] = val.strip().strip('"').strip("'")
    except OSError as e:
        print(f"[경고] .env 읽기 실패: {e}", file=sys.stderr)
    return data


def find_env() -> Path:
    """워크스페이스 루트 .env 경로(스크립트 기준 2단계 위)."""
    return Path(__file__).resolve().parents[2] / ".env"


def process_inbox(api_key: str, sheet_id: str, dry_run: bool, max_count: int = 50) -> dict:
    """받은편지함 안읽은 메일을 훑어 분류·처리한다. 결과 요약 dict를 반환한다."""
    summary = {"trashed": [], "forwarded": [], "errors": []}

    try:
        messages = gws_client.list_unread_messages(max_count=max_count)
    except gws_client.GwsError as e:
        summary["errors"].append(f"목록 조회 실패: {e}")
        return summary

    for msg in messages:
        message_id = msg["id"]
        try:
            detail = gws_client.read_message(message_id)
            subject = detail.get("subject", "")
            sender = detail.get("from", {}).get("email", "")
            body_text = detail.get("body_text") or ""

            result = classifier.classify_email(subject, sender, body_text, api_key)
            category = result["category"]

            if dry_run:
                bucket = "trashed" if category == "junk" else "forwarded"
                summary[bucket].append({"id": message_id, "subject": subject, "reason": result["reason"]})
                continue

            if category == "junk":
                gws_client.trash_message(message_id)
                summary["trashed"].append({"id": message_id, "subject": subject})
                action = "휴지통"
            else:
                gws_client.forward_message(message_id, FORWARD_TO)
                gws_client.mark_read(message_id)
                summary["forwarded"].append({"id": message_id, "subject": subject})
                action = "전달"

            if sheet_id:
                gws_client.append_log_row(sheet_id, [
                    datetime.now(timezone.utc).isoformat(),
                    sender,
                    subject,
                    category,
                    action,
                ])
        except Exception as e:
            summary["errors"].append(f"{message_id} 처리 실패: {e}")

    if not dry_run and not summary["errors"]:
        state.record_success(datetime.now(timezone.utc).isoformat())

    return summary


def main():
    parser = argparse.ArgumentParser(description="이메일 자동관리 — cy728728 수집함 정리")
    parser.add_argument("--dry-run", action="store_true", help="실제 처리 없이 분류 결과만 미리보기")
    parser.add_argument("--max", type=int, default=50, help="1회 처리할 최대 메일 수")
    args = parser.parse_args()

    env = load_env(find_env())
    api_key = env.get("ANTHROPIC_API_KEY")
    sheet_id = env.get("EMAIL_TRIAGE_SHEET_ID")

    if not api_key:
        print("[오류] ANTHROPIC_API_KEY가 .env에 없습니다.", file=sys.stderr)
        sys.exit(1)

    summary = process_inbox(api_key, sheet_id, dry_run=args.dry_run, max_count=args.max)

    print(f"[결과] 휴지통 {len(summary['trashed'])}건 / 전달 {len(summary['forwarded'])}건 / 오류 {len(summary['errors'])}건")
    for err in summary["errors"]:
        print(f"  [오류] {err}", file=sys.stderr)


if __name__ == "__main__":
    main()
