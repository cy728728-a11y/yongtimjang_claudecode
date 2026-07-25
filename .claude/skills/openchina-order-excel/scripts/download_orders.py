#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
오픈차이나(openchina.co.kr) 주문내역 엑셀 다운로드.

동작:
  1. .env의 로그인 정보로 세션 로그인 (POST /Front/Join/Login_Ajax.asp)
  2. 주문내역 엑셀 다운로드 (POST /Front/Member/Acting_X17.asp)
  3. 지정한 폴더에 .xls 파일로 저장

외부 패키지 불필요 — 파이썬 표준 라이브러리(urllib)만 사용.
사이트가 브라우저 화면의 '주문 엑셀다운로드' 버튼과 동일한 요청을 그대로 재현한다.
"""

import argparse
import datetime
import http.cookiejar
import os
import sys
import urllib.parse
import urllib.request

# Windows 콘솔(cp949)에서 한글 경로가 깨지지 않도록 UTF-8 출력 강제
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = "https://www.openchina.co.kr"
LOGIN_URL = BASE + "/Front/Join/Login_Ajax.asp"
EXCEL_URL = BASE + "/Front/Member/Acting_X17.asp"  # 마이페이지 '주문 엑셀다운로드' 버튼과 동일
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


def find_env(start):
    """스크립트 위치에서 위로 올라가며 .env 파일을 찾는다."""
    d = os.path.abspath(start)
    while True:
        cand = os.path.join(d, ".env")
        if os.path.isfile(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:  # 루트 도달
            return None
        d = parent


def load_env(env_path):
    """간단한 .env 파서 (KEY=VALUE, # 주석 무시). 외부 의존성 없음."""
    creds = {}
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                creds[k.strip()] = v.strip().strip('"').strip("'")
    except Exception as e:
        print(f"[오류] .env 읽기 실패: {e}", file=sys.stderr)
    return creds


def build_opener():
    """쿠키를 유지하는 opener 생성 (세션 로그인용)."""
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", UA)]
    return op


def login(op, user_id, user_pw):
    """로그인. 성공 시 서버가 '1'을 반환한다."""
    try:
        body = urllib.parse.urlencode({"sMemId": user_id, "sMemPw": user_pw}).encode()
        req = urllib.request.Request(
            LOGIN_URL, body,
            headers={"Referer": BASE + "/Front/Join/Login.asp"},
        )
        resp = op.open(req, timeout=30).read().decode("euc-kr", "replace").strip()
    except Exception as e:
        print(f"[오류] 로그인 요청 실패: {e}", file=sys.stderr)
        return False
    if resp == "1":
        return True
    # rtn != 1 이면 아이디/비번 불일치
    print(f"[오류] 로그인 실패 (서버 응답: {resp!r}). 아이디/비밀번호를 확인하세요.", file=sys.stderr)
    return False


def download_excel(op, begin_day, end_day, stat_seq, tab_ty, out_path):
    """주문내역 엑셀을 다운로드해 out_path에 저장한다."""
    # 브라우저의 frmOrdExcel 폼과 동일한 필드 구성.
    # shOrdSeqArr 를 비우면 기간 내 전체 주문이 대상(체크박스 선택 없음).
    data = {
        "shOrdSeqArr": "",
        "shStatSeq": str(stat_seq),
        "shDateTermTy": "",
        "shTabTy": str(tab_ty),
        "shGo": "1",
        "shBeginDay": begin_day,
        "shEndDay": end_day,
        "shOrdNo": "",
        "shTrackinNo": "",
        "shProNm": "",
        "shAdrsKr": "",
        "shShopOrdNo": "",
        "shOrdIvcNo": "",
        "shKdIvc": "",
    }
    try:
        req = urllib.request.Request(
            EXCEL_URL, urllib.parse.urlencode(data).encode(),
            headers={"Referer": BASE + "/Front/Member/MyPage.asp?gMnu1=206&gMnu2=20601"},
        )
        resp = op.open(req, timeout=90)
        ctype = (resp.headers.get("Content-Type") or "").lower()
        raw = resp.read()
    except Exception as e:
        print(f"[오류] 다운로드 요청 실패: {e}", file=sys.stderr)
        return False

    # 엑셀이 아니라 로그인 페이지(HTML)가 돌아오면 세션 만료 등 문제.
    if "excel" not in ctype and "vnd.ms-excel" not in ctype:
        print(f"[오류] 엑셀 응답이 아님 (Content-Type: {ctype}). 세션이 끊겼거나 조회 결과가 없습니다.",
              file=sys.stderr)
        return False

    try:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(raw)
    except Exception as e:
        print(f"[오류] 파일 저장 실패: {e}", file=sys.stderr)
        return False

    print(f"[완료] 저장: {out_path}")
    print(f"[정보] 크기: {len(raw):,} bytes | 기간: {begin_day} ~ {end_day}")
    return True


def main():
    today = datetime.date.today()
    default_begin = today - datetime.timedelta(days=90)  # 기본 최근 90일

    p = argparse.ArgumentParser(description="오픈차이나 주문내역 엑셀 다운로드")
    p.add_argument("--begin", default=default_begin.isoformat(),
                   help="조회 시작일 YYYY-MM-DD (기본: 90일 전)")
    p.add_argument("--end", default=today.isoformat(),
                   help="조회 종료일 YYYY-MM-DD (기본: 오늘)")
    p.add_argument("--out-dir", default=None,
                   help="저장 폴더 (기본: 워크스페이스 50-resources/openchina)")
    p.add_argument("--stat-seq", default=0, type=int,
                   help="주문상태 필터 shStatSeq (기본 0=전체)")
    p.add_argument("--tab-ty", default=1, type=int,
                   help="탭 구분 shTabTy (기본 1)")
    p.add_argument("--env", default=None, help=".env 경로 (기본: 상위 폴더 자동 탐색)")
    args = p.parse_args()

    # .env 위치: 인자 > 자동 탐색
    env_path = args.env or find_env(os.path.dirname(__file__))
    if not env_path:
        print("[오류] .env 파일을 찾을 수 없습니다. 워크스페이스 루트에 .env를 두거나 --env로 지정하세요.",
              file=sys.stderr)
        return 1
    creds = load_env(env_path)
    user_id, user_pw = creds.get("OPENCHINA_ID"), creds.get("OPENCHINA_PW")
    if not user_id or not user_pw:
        print("[오류] .env에 OPENCHINA_ID / OPENCHINA_PW 가 없습니다.", file=sys.stderr)
        return 1

    # 저장 경로 결정
    if args.out_dir:
        out_dir = args.out_dir
    else:
        # env 파일이 있는 폴더(=워크스페이스 루트) 기준
        ws_root = os.path.dirname(os.path.abspath(env_path))
        out_dir = os.path.join(ws_root, "50-resources", "openchina")
    # 고정 파일명 — 매번 덮어써서 항상 최신 1개만 유지(누적 방지).
    # 조회 기간은 파일 안의 데이터로 확인. 저장 후 아래에서 기간을 함께 출력한다.
    out_path = os.path.join(out_dir, "오픈차이나_주문내역_최신.xls")

    op = build_opener()
    if not login(op, user_id, user_pw):
        return 1
    if not download_excel(op, args.begin, args.end, args.stat_seq, args.tab_ty, out_path):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
