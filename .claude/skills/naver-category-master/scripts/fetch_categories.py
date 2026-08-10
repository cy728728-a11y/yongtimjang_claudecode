#!/usr/bin/env python3
"""네이버 커머스API 전체 카테고리 수집기.

커머스API `GET /v1/categories` 를 한 번 호출해 네이버 쇼핑 전체 카테고리를
받아 마스터 파일(JSON)로 저장한다. 경로 → 코드 역조회용 색인도 같이 만든다.

사용:
    .venv/bin/python .claude/skills/naver-category-master/scripts/fetch_categories.py
    .venv/bin/python .../fetch_categories.py --output 30-knowledge/39-naver-category/master.json
"""

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

try:
    import bcrypt
    import requests
except ImportError as e:  # 의존성 누락은 원인을 바로 알려준다
    sys.exit(f"의존성 없음: {e}. `uv pip install --python .venv/bin/python bcrypt requests` 로 설치한다.")

API_BASE = "https://api.commerce.naver.com/external"
# 워크스페이스 루트 = 이 파일 기준 4단계 위 (.claude/skills/<skill>/scripts/)
ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OUTPUT = ROOT / "30-knowledge" / "39-naver-category" / "naver-category-master.json"


def load_env(path):
    """.env 를 읽어 dict 로 돌려준다. 값에 `$` 가 들어가므로 셸 확장을 쓰지 않는다."""
    env = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    except FileNotFoundError:
        sys.exit(f".env 없음: {path}\nNAVER_COMMERCE_CLIENT_ID / _SECRET 두 줄이 필요하다.")
    except OSError as e:
        sys.exit(f".env 읽기 실패: {e}")
    return env


def issue_token(client_id, client_secret):
    """전자서명(bcrypt) 방식으로 액세스 토큰을 발급받는다.

    서명 규칙: bcrypt(비밀번호="{client_id}_{timestamp}", salt=client_secret) → base64.
    client_secret 자체가 bcrypt salt(`$2a$04$...`) 라서 별도 salt 생성이 없다.
    """
    timestamp = int(time.time() * 1000)  # 밀리초. 서버 시각과 크게 벌어지면 거부된다
    try:
        hashed = bcrypt.hashpw(f"{client_id}_{timestamp}".encode("utf-8"),
                               client_secret.encode("utf-8"))
    except ValueError as e:
        sys.exit(f"시크릿 형식 오류(bcrypt salt 아님): {e}\n"
                 f"커머스API센터에서 [보기] > 인증 > [복사] 로 다시 받아 .env 에 넣는다.")

    payload = {
        "client_id": client_id,
        "timestamp": timestamp,
        "client_secret_sign": base64.b64encode(hashed).decode("utf-8"),
        "grant_type": "client_credentials",
        "type": "SELF",  # 판매자 본인 스토어용
    }
    try:
        r = requests.post(f"{API_BASE}/v1/oauth2/token", data=payload, timeout=30)
    except requests.RequestException as e:
        sys.exit(f"토큰 요청 실패(네트워크): {e}")

    if r.status_code != 200:
        sys.exit(f"토큰 발급 실패 [{r.status_code}] {r.text[:500]}\n"
                 f"→ 애플리케이션 ID/시크릿, 그리고 커머스API센터에 등록한 '호출 IP' 를 확인한다.")
    return r.json()["access_token"]


def fetch_categories(token):
    """전체 카테고리 목록을 받는다. 응답이 list 인지 dict 래핑인지 둘 다 받아준다."""
    try:
        r = requests.get(f"{API_BASE}/v1/categories",
                         headers={"Authorization": f"Bearer {token}"}, timeout=120)
    except requests.RequestException as e:
        sys.exit(f"카테고리 조회 실패(네트워크): {e}")

    if r.status_code != 200:
        sys.exit(f"카테고리 조회 실패 [{r.status_code}] {r.text[:500]}")

    data = r.json()
    if isinstance(data, dict):  # {"contents": [...]} 같은 래핑 대비
        for key in ("contents", "data", "categories", "result"):
            if isinstance(data.get(key), list):
                return data[key]
        sys.exit(f"예상치 못한 응답 형태: keys={list(data)[:10]}")
    return data


def build_master(rows):
    """원본 목록 + 역조회 색인을 담은 마스터 dict 를 만든다."""
    by_path, dup_paths = {}, set()
    for row in rows:
        # 경로 구분자가 '>' 인지 ' > ' 인지 응답마다 다를 수 있어 정규화해 둔다
        whole = (row.get("wholeCategoryName") or "").strip()
        norm = " > ".join(p.strip() for p in whole.split(">") if p.strip())
        row["경로정규화"] = norm
        if not norm:
            continue
        if norm in by_path and by_path[norm] != str(row.get("id")):
            dup_paths.add(norm)  # 같은 경로에 코드가 둘 → 자동 확정 금지 대상
        by_path.setdefault(norm, str(row.get("id")))

    return {
        "출처": f"{API_BASE}/v1/categories",
        "총건수": len(rows),
        "최종차수건수": sum(1 for r in rows if r.get("last")),
        "중복경로": sorted(dup_paths),
        "경로to코드": by_path,
        "카테고리": rows,
    }


def main():
    ap = argparse.ArgumentParser(description="네이버 커머스API 전체 카테고리 수집")
    ap.add_argument("--env", default=str(ROOT / ".env"), help=".env 경로")
    ap.add_argument("--output", default=str(DEFAULT_OUTPUT), help="마스터 JSON 저장 경로")
    args = ap.parse_args()

    env = load_env(Path(args.env))
    client_id = env.get("NAVER_COMMERCE_CLIENT_ID") or os.environ.get("NAVER_COMMERCE_CLIENT_ID")
    client_secret = env.get("NAVER_COMMERCE_CLIENT_SECRET") or os.environ.get("NAVER_COMMERCE_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit("NAVER_COMMERCE_CLIENT_ID / NAVER_COMMERCE_CLIENT_SECRET 가 .env 에 없다.")

    print("토큰 발급 중...", file=sys.stderr)
    token = issue_token(client_id, client_secret)

    print("전체 카테고리 조회 중...", file=sys.stderr)
    rows = fetch_categories(token)

    master = build_master(rows)
    out = Path(args.output)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(master, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        sys.exit(f"저장 실패: {e}")

    print(f"저장 완료: {out}")
    print(f"  총 {master['총건수']}건 / 최종차수 {master['최종차수건수']}건 "
          f"/ 중복경로 {len(master['중복경로'])}건")


if __name__ == "__main__":
    main()
