#!/usr/bin/env python3
"""소싱 파이프라인 장부 세 개 — 마켓 · 본 상품(네이버 번호) · 타오바오 번호.

설계: docs/superpowers/specs/2026-11-08-sourcing-pipeline-design.md 5절.
모두 로컬 파일(~/python_work/data/sourcing-pipeline/). 불사자가 정본인 것(그룹 소속 등)은 여기 두지 않는다.

  markets.jsonl       한 줄 = 마켓 하나 {slug,url,first_seen,full_run,last_3day,products,empty}
  seen_products.jsonl 한 줄 = 네이버 상품번호 하나 {pid,campaign,date,verdict}
  seen_taobao.txt     한 줄 = 타오바오 상품번호 하나
  internal_ids.txt    네이버 번호가 아닌 불사자 내부 번호(U01M…) — 대조에 못 쓰므로 따로 보관
"""
import json
import os
import re
import sys

DATA_DIR = os.path.expanduser("~/python_work/data/sourcing-pipeline")
MARKETS = os.path.join(DATA_DIR, "markets.jsonl")
SEEN_PRODUCTS = os.path.join(DATA_DIR, "seen_products.jsonl")
SEEN_TAOBAO = os.path.join(DATA_DIR, "seen_taobao.txt")
INTERNAL_IDS = os.path.join(DATA_DIR, "internal_ids.txt")

_SMARTSTORE_HOSTS = ("smartstore.naver.com", "m.smartstore.naver.com")


def mall_slug(url):
    """마켓 주소 → 비교용 열쇠. 스마트스토어는 상점 이름만, 나머지는 host/path 소문자. 빈 값은 None."""
    if not url or not str(url).strip():
        return None
    u = str(url).strip()
    u = re.sub(r"^[a-zA-Z]+://", "", u)          # 프로토콜 제거
    u = u.split("?", 1)[0].split("#", 1)[0]       # 질의문·앵커 제거
    u = u.rstrip("/").lower()
    if not u:
        return None
    host, _, path = u.partition("/")
    if host in _SMARTSTORE_HOSTS:
        slug = path.split("/", 1)[0]
        return slug or None
    return u


def is_naver_pid(pid):
    """네이버 상품번호인가 — 숫자만 6자리 이상. U01M… 같은 불사자 내부 번호는 False."""
    if pid is None:
        return False
    s = str(pid).strip()
    return s.isdigit() and len(s) >= 6


def taobao_item_id(item):
    """캠페인 상품 → 타오바오 상품번호(str). apply_sourcing.collect_item 과 같은 경로."""
    try:
        tb = item.get("taobaoResult") or []
        if not isinstance(tb, list) or not tb:
            return None
        it = (tb[0] or {}).get("item") or {}
        iid = it.get("itemId")
        return str(iid) if iid not in (None, "") else None
    except (AttributeError, TypeError):
        return None


def _ensure_dir(path):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError as e:
        print(f"[ledger] 폴더 생성 실패 {path}: {e}", file=sys.stderr)


def _read_lines(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [ln.rstrip("\n") for ln in f if ln.strip()]
    except FileNotFoundError:
        return []
    except OSError as e:
        print(f"[ledger] 읽기 실패 {path}: {e}", file=sys.stderr)
        return []


# ---------- 본 상품(네이버 번호) ----------

def load_seen_products(path=SEEN_PRODUCTS):
    out = set()
    for ln in _read_lines(path):
        try:
            out.add(str(json.loads(ln)["pid"]))
        except (ValueError, KeyError, TypeError):
            continue
    return out


def load_seen_products_map(path=SEEN_PRODUCTS):
    """pid → 처음 본 캠페인. 중복 판정 때 자기 캠페인 기록을 걸러내는 데 쓴다."""
    out = {}
    for ln in _read_lines(path):
        try:
            r = json.loads(ln)
            out.setdefault(str(r["pid"]), r.get("campaign") or "")
        except (ValueError, KeyError, TypeError):
            continue
    return out


def append_seen_products(rows, path=SEEN_PRODUCTS):
    """rows: [{pid,campaign,date,verdict}] — 장부에 없는 pid 만 덧붙이고 추가한 수를 돌려준다."""
    seen = load_seen_products(path)
    added = 0
    _ensure_dir(path)
    try:
        with open(path, "a", encoding="utf-8") as f:
            for r in rows:
                pid = str(r.get("pid", "")).strip()
                if not pid or pid in seen:
                    continue
                f.write(json.dumps({**r, "pid": pid}, ensure_ascii=False) + "\n")
                seen.add(pid)
                added += 1
    except OSError as e:
        print(f"[ledger] 쓰기 실패 {path}: {e}", file=sys.stderr)
    return added


# ---------- 타오바오 번호 ----------

def load_seen_taobao(path=SEEN_TAOBAO):
    return {ln.strip() for ln in _read_lines(path)}


def append_seen_taobao(ids, path=SEEN_TAOBAO):
    seen = load_seen_taobao(path)
    added = 0
    _ensure_dir(path)
    try:
        with open(path, "a", encoding="utf-8") as f:
            for i in ids:
                s = str(i).strip() if i is not None else ""
                if not s or s in seen:
                    continue
                f.write(s + "\n")
                seen.add(s)
                added += 1
    except OSError as e:
        print(f"[ledger] 쓰기 실패 {path}: {e}", file=sys.stderr)
    return added


# ---------- 마켓 ----------

def load_markets(path=MARKETS):
    out = {}
    for ln in _read_lines(path):
        try:
            row = json.loads(ln)
            out[row["slug"]] = row
        except (ValueError, KeyError, TypeError):
            continue
    return out


def upsert_markets(rows, path=MARKETS):
    """slug → row 전체를 다시 쓴다(마켓 수만 건이라 전체 쓰기로 충분)."""
    _ensure_dir(path)
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            for slug in sorted(rows):
                f.write(json.dumps(rows[slug], ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    except OSError as e:
        print(f"[ledger] 쓰기 실패 {path}: {e}", file=sys.stderr)
