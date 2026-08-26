#!/usr/bin/env python3
"""
이메일 자동관리 — 수집함(cy728728@gmail.com) 받은편지함 정리.

사용법:
    python3 triage.py            # 미리보기 (삭제 안 함)
    python3 triage.py --apply    # 실제 휴지통 이동 (30일 복구 가능)
    python3 triage.py --apply --query "in:inbox is:unread"

판정 규칙은 rules.py 참조. KEEP 이 DELETE 보다 항상 우선(오삭제 방지).
"""
import json, subprocess, sys, argparse, os, threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rules import judge2

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")


def gws(args, body=None, timeout=180):
    """gws CLI 호출 후 JSON 파싱. 실패 시 예외."""
    cmd = ["gws"] + args
    if body is not None:
        cmd += ["--json", json.dumps(body)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-300:])
    return json.loads(r.stdout[r.stdout.index("{"):])


def list_ids(query):
    """검색 조건에 맞는 메시지 ID 전체를 페이지네이션으로 수집"""
    ids, token = [], None
    while True:
        p = {"userId": "me", "q": query, "maxResults": 500}
        if token:
            p["pageToken"] = token
        d = gws(["gmail", "users", "messages", "list", "--params", json.dumps(p), "--format", "json"])
        ids += [m["id"] for m in d.get("messages", [])]
        token = d.get("nextPageToken")
        if not token:
            return ids


def fetch_meta(ids, workers=12):
    """메시지 헤더를 병렬 수집"""
    lock, cnt = threading.Lock(), [0]

    def one(mid):
        params = json.dumps({"userId": "me", "id": mid, "format": "metadata",
                             "metadataHeaders": ["From", "Subject", "Date", "List-Unsubscribe"]})
        for _ in range(2):  # 일시 오류 1회 재시도
            try:
                d = gws(["gmail", "users", "messages", "get", "--params", params, "--format", "json"], timeout=90)
                h = {x["name"]: x["value"] for x in d.get("payload", {}).get("headers", [])}
                res = {"id": mid, "from": h.get("From", ""), "subject": h.get("Subject", ""),
                       "date": h.get("Date", ""), "unsub": bool(h.get("List-Unsubscribe")),
                       "snippet": d.get("snippet", "")[:150]}
                break
            except Exception as e:
                res = {"id": mid, "from": "", "subject": "", "error": str(e)}
        with lock:
            cnt[0] += 1
            if cnt[0] % 500 == 0:
                print(f"  메타 수집 {cnt[0]}/{len(ids)}", flush=True)
        return res

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(one, ids))


def trash(ids, chunk=1000):
    """batchModify 로 일괄 휴지통 이동"""
    moved = 0
    for i in range(0, len(ids), chunk):
        batch = ids[i:i + chunk]
        gws(["gmail", "users", "messages", "batchModify", "--params", json.dumps({"userId": "me"})],
            body={"addLabelIds": ["TRASH"], "removeLabelIds": ["INBOX"], "ids": batch}, timeout=300)
        moved += len(batch)
        print(f"  휴지통 이동 {moved}/{len(ids)}", flush=True)
    return moved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제 삭제 실행 (미지정 시 미리보기)")
    ap.add_argument("--query", default="in:inbox", help="Gmail 검색 조건")
    a = ap.parse_args()

    try:
        who = gws(["gmail", "users", "getProfile", "--params", '{"userId":"me"}', "--format", "json"])
        print("계정:", who["emailAddress"])
    except Exception as e:
        print("gws 인증 실패 — `gws auth login --services gmail` 먼저 실행.", e)
        sys.exit(1)

    ids = list_ids(a.query)
    print(f"대상 {len(ids)}건 ({a.query})")
    if not ids:
        return

    meta = fetch_meta(ids)
    dele = [m for m in meta if judge2(m) == "DELETE"]
    keep = [m for m in meta if judge2(m) != "DELETE"]
    print(f"\n삭제 대상 {len(dele)} / 남김 {len(keep)}")

    os.makedirs(LOG_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    logfile = os.path.join(LOG_DIR, f"{stamp}-{'apply' if a.apply else 'preview'}.json")
    json.dump({"query": a.query, "delete": dele, "keep": keep},
              open(logfile, "w"), ensure_ascii=False, indent=1)
    print("로그:", logfile)

    if not a.apply:
        print("\n[미리보기] 삭제 예정 상위 20건:")
        for m in dele[:20]:
            print("  -", m["from"][:35], "|", (m["subject"] or "")[:55])
        print("\n실제 삭제하려면 --apply 를 붙여 다시 실행.")
        return

    trash([m["id"] for m in dele])
    print(f"\n완료. {len(dele)}건 휴지통 이동 (30일 복구 가능). 남은 받은편지함 {len(keep)}건.")


if __name__ == "__main__":
    main()
