#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""광고 기반 상세페이지 우선순위 — 주 1회만 받아 오는 헬퍼 (detail-page-opus 용).

맥미니가 매주 월요일 06:10 무렵 드라이브에 `상세우선순위_최신.json` 을 갱신한다.
이 스크립트는 '이번 주 월요일 07:00 이후 아직 안 받았으면' 한 번만 받아 로컬에 저장하고,
그 뒤 일주일 동안은 네트워크 없이 로컬 사본만 쓴다.

    python3 fetch_ad_priority.py            # 필요할 때만 받기 + 다음 작업 후보 10개 출력
    python3 fetch_ad_priority.py --next 5   # 후보 5개
    python3 fetch_ad_priority.py --done <불사자상품ID 또는 스토어상품번호>   # 작업 끝난 상품 기록
    python3 fetch_ad_priority.py --force    # 이번 주에 이미 받았어도 다시 받기

준비물: python3 · gws CLI(드라이브 폴더를 볼 수 있는 계정으로 로그인).
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

FILE_ID = "1_0-eJUWKyp-WRZFCRmvTdg1kZQfQf2J5"     # 드라이브 상세우선순위_최신.json (매주 같은 파일이 갱신된다)
HOME = Path(os.environ.get("AD_PRIORITY_HOME", "~/python_work/data/detail-opus/ad-priority")).expanduser()
DATA = HOME / "상세우선순위_최신.json"
STATE = HOME / "state.json"
DONE = HOME / "완료.json"
WEEK_START_HOUR = 7          # 월요일 07:00 이후 첫 실행에서 받는다 (맥미니 업로드는 06:10 전후)


def _load(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def week_start(now):
    """이번 주 월요일 07:00. 월요일 07:00 전이면 지난주 월요일 07:00."""
    monday = (now - timedelta(days=now.weekday())).replace(hour=WEEK_START_HOUR, minute=0, second=0, microsecond=0)
    return monday if now >= monday else monday - timedelta(days=7)


def need_fetch(now, state):
    """이번 주 회차를 아직 못 받았으면 True."""
    ws = week_start(now)
    got = state.get("회차")
    return not got or got < ws.date().isoformat()


def download(dest):
    """gws 로 드라이브 파일을 받는다. JSON 파일은 gws 가 -o 를 무시하고 stdout 에 내용을 찍는다
    (앞에 'Using keyring backend' 같은 안내 줄이 붙을 수 있다 — 첫 '{' 부터 읽는다).
    gws 는 API 오류도 rc=0 + {"error":…} 로 돌려주므로 그것도 실패로 본다."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # 맥북은 gws 인증을 기본 저장소에 둔다 — 저장 방식을 'file' 로 강제하면 복호화 실패로 로그인 정보가 지워진다(2026-11-02 실측)
    env = dict(os.environ)
    p = subprocess.run(["gws", "drive", "files", "get", "--params", json.dumps({"fileId": FILE_ID, "alt": "media"})],
                       cwd=str(dest.parent), env=env, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120)
    out = p.stdout or ""
    i = out.find("{")
    if p.returncode != 0 or i < 0:
        raise RuntimeError(f"gws 실패 rc={p.returncode}: {(p.stderr or out)[-300:]}")
    doc = json.loads(out[i:])
    if isinstance(doc, dict) and isinstance(doc.get("error"), dict):
        raise RuntimeError(f"드라이브 오류 {doc['error'].get('code')}: {doc['error'].get('message')} "
                           f"— 폴더 공유·로그인 계정을 확인")
    if not isinstance(doc, dict) or "rows" not in doc:
        raise RuntimeError("받은 파일 형식이 다르다")
    _save(dest, doc)
    return doc


def ensure(now=None, force=False, log=print):
    """필요하면 받고, 로컬 데이터를 돌려준다."""
    now = now or datetime.now()
    state = _load(STATE, {})
    if force or need_fetch(now, state) or not DATA.exists():
        try:
            doc = download(DATA)
            got = (doc.get("meta") or {}).get("회차")
            _save(STATE, {"회차": got, "받은시각": now.isoformat(timespec="seconds")})
            if got and got < week_start(now).date().isoformat():
                log(f"[주의] 드라이브가 아직 지난 회차({got}) — 맥미니 월요일 실행이 늦거나 실패. 다음 시작 때 다시 받는다")
            else:
                log(f"[받음] 광고 우선순위 {got} 회차 · {len(doc.get('rows') or [])}건")
        except Exception as e:
            if DATA.exists():
                log(f"[주의] 새 회차 받기 실패({type(e).__name__}) — 지난 사본으로 진행: {e}")
            else:
                raise
    else:
        log(f"[로컬] 이번 주 회차 {state.get('회차')} 이미 받음 — 다시 받지 않는다")
    return _load(DATA, {"meta": {}, "rows": []})


def _keys(r):
    return {str(r.get("불사자상품ID") or ""), str(r.get("스토어상품번호") or "")} - {""}


def candidates(doc, n):
    done = set(_load(DONE, {}).keys())
    out = [r for r in doc.get("rows") or [] if not (_keys(r) & done)]
    return out[:n]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--next", type=int, default=10)
    ap.add_argument("--done", nargs="*", help="작업 끝난 불사자상품ID/스토어상품번호")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    if a.done:
        d = _load(DONE, {})
        for k in a.done:
            d[k] = datetime.now().isoformat(timespec="seconds")
        _save(DONE, d)
        print(f"완료 기록 {len(a.done)}건 (누적 {len(d)})")
        return 0
    doc = ensure(force=a.force)
    m = doc.get("meta") or {}
    print(f"회차 {m.get('회차')} · 7일 {m.get('7일기간')} · 등급별 {m.get('등급별')}")
    for r in candidates(doc, a.next):
        print(f"{r['순위']:>3} {r['등급']} | {r['상품명'][:30]} | {r['마켓번호']} | 불사자 {r['불사자상품ID'] or '-'} | "
              f"상세 {r['상세상태'] or '?'} | 7일 노출{r['7일노출']} 클릭{r['7일클릭']} CTR{r['7일CTR']}% | "
              f"30일 클릭{r['30일클릭']} 구매{r['30일구매']} | {r['사유']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
