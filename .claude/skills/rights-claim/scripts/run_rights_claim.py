#!/usr/bin/env python3
"""네이버 권리보호센터 소명요청 자동처리 (rights-claim).

흐름: 수집함 IMAP 감지·파싱 → Aside 로 소명페이지 OTP 조회(신고 상품번호)
      → 커머스API 로 판매자상품코드 → 불사자 원본+상표명 복사본 삭제
      → 마켓삭제 확인 폴링 → Aside 로 고정 문구 소명 제출 → 카톡 보고 + 대장 기록.

안전 원칙:
  - 삭제 대상은 소명페이지 상품번호 → 커머스 sellerManagementCode → find_by_code 체인으로만 정한다.
    메일의 권리명으로 불사자를 검색하지 않는다 (2026-10-27 '물레방아' 상표 신고에 분수대 수십 건이 잡힌 사고).
  - 잠금(판매된) 상품은 삭제하지 않는다.
  - Aside 쓰기 예외는 right.naver.com 소명 페이지 한정.
"""
import html
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
APPEAL_PATH = os.path.join(SKILL_DIR, "references", "소명문구.txt")

# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------
CLAIM_FROM = "nv_shopping_ips@navercorp.com"
CLAIM_SUBJECT_KEY = "소명요청"
SENTINEL = "###RC###"
APPEAL_MAX = 500
SUCCESS_TEXT_NOSPACE = "권리소명이접수되었어요"
LINK_PREFIX = "https://right.naver.com/otp?code="   # 이 접두가 아니면 브라우저로 열지 않는다
KAKAO_MAX = 200


# ===========================================================================
# 순수함수 — 외부 호출 없음
# ===========================================================================
def html_to_text(s):
    """HTML → 평문. br/p/div/tr/td/li 는 줄바꿈, style/script 는 통째로 제거, 엔티티 언이스케이프."""
    if not s:
        return ""
    t = re.sub(r"(?is)<(style|script)\b.*?</\1\s*>", "", s)
    t = re.sub(r"(?i)<br\s*/?>", "\n", t)
    t = re.sub(r"(?i)</(p|div|tr|li|h\d|table)\s*>", "\n", t)
    t = re.sub(r"(?i)</td\s*>", "\t", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t ]+\n", "\n", t)
    return t


def _looks_html(s):
    return bool(re.search(r"(?i)<(html|body|p|div|br|table|a)\b", s or ""))


_LINK_RE = re.compile(r"https?://[^\s\"'<>]*otp\?code=[A-Za-z0-9_\-+/%=&;.]+")
_OTP_RE = re.compile(r"(?<![0-9A-Za-z])(\d{6})(?![0-9A-Za-z])")


def _clean_link(raw):
    """링크 끝의 잔여 구두점 정리 + &amp; 언이스케이프."""
    link = html.unescape(raw).strip()
    link = link.rstrip(".,;)")
    return link


def parse_mail(body, to="", date="", subject=""):
    """소명요청 메일 본문(텍스트 또는 HTML) → dict.

    필수값(receipt·link·otp) 이 빠지면 {"error": "누락: ...", ...부분값} 을 돌려준다(예외 아님).
    링크가 right.naver.com/otp 접두가 아니면 error (사칭 메일 방지, 브라우저 미오픈).
    """
    body = body or ""
    is_html = _looks_html(body)
    text = html_to_text(body) if is_html else body
    out = {"to": to or "", "mail_date": date or "", "subject": subject or "",
           "reporter": "", "right_name": "", "right_no": "", "receipt": "", "link": "", "otp": ""}

    m = re.search(r"신고자\s*\[(.+?)\]", text)
    if m:
        out["reporter"] = m.group(1).strip()

    m = re.search(r"등록권리\s*\(([^()]*?)\)\s*\(\s*(\d+)\s*\)", text) or \
        re.search(r"\(([^()]+)\)\s*\(\s*(\d{6,})\s*\)", text)
    if m:
        out["right_name"] = m.group(1).strip()
        out["right_no"] = m.group(2).strip()

    m_rc = re.search(r"대표접수번호\s*\[\s*([0-9A-Z]+)\s*\]", text)
    if m_rc:
        out["receipt"] = m_rc.group(1)

    # 링크: HTML 이면 href 원문에서 먼저 찾는다 (본문 텍스트엔 앵커 문구만 남는다)
    link_raw = ""
    if is_html:
        m = re.search(r"""(?i)href\s*=\s*["']([^"']*otp\?code=[^"']*)["']""", body)
        if m:
            link_raw = m.group(1)
    m_link = _LINK_RE.search(text)
    if not link_raw and m_link:
        link_raw = m_link.group(0)
    link = _clean_link(link_raw) if link_raw else ""
    bad_link = ""
    if link and not link.startswith(LINK_PREFIX):
        bad_link = link
        link = ""
    out["link"] = link

    # OTP: 링크가 본문에 보이면 그 뒤, 아니면 'OTP' 글자 뒤, 아니면 대표접수번호 뒤 첫 독립 6자리
    start = 0
    if m_link:
        start = m_link.end()
    else:
        idx = text.rfind("OTP")
        if idx >= 0:
            start = idx
        elif m_rc:
            start = m_rc.end()
    m = _OTP_RE.search(text, start)
    if m:
        out["otp"] = m.group(1)

    missing = [k for k in ("receipt", "link", "otp") if not out[k]]
    if bad_link:
        out["error"] = f"허용되지 않은 링크 도메인: {bad_link[:60]}"
    elif missing:
        out["error"] = "누락: " + ",".join(missing)
    return out


def _addr(from_):
    m = re.search(r"<([^<>]+)>", from_ or "")
    return (m.group(1) if m else (from_ or "")).strip().lower()


def is_claim_mail(from_, subject):
    """발신 주소 정확일치 + 제목에 '소명요청'."""
    return _addr(from_) == CLAIM_FROM and CLAIM_SUBJECT_KEY in (subject or "")


def _sentinel_payload(text):
    """repl 출력에서 마지막 센티널 줄의 JSON. 없거나 깨졌으면 None."""
    found = None
    for line in (text or "").splitlines():
        i = line.find(SENTINEL)
        if i < 0:
            continue
        try:
            found = json.loads(line[i + len(SENTINEL):].strip())
        except ValueError:
            continue
    return found


_URL_TAIL = re.compile(r"\s*https?://\S+\s*$")


def parse_targets(text):
    """lookup repl 출력 → {"targets": [{no, store, title}], "explain_no", "url", "error"}."""
    out = {"targets": [], "explain_no": "", "url": "", "error": None}
    p = _sentinel_payload(text)
    if not isinstance(p, dict):
        out["error"] = "센티널 없음"
        return out
    if not p.get("ok", True):
        out["error"] = str(p.get("error") or "repl 실패")
        return out
    out["url"] = str(p.get("url") or "")
    out["explain_no"] = str(p.get("explainNo") or "")
    seen = set()
    for t in p.get("targets") or []:
        no = str((t or {}).get("no") or "").strip()
        if not no.isdigit() or no in seen:
            continue
        seen.add(no)
        raw = _URL_TAIL.sub("", str(t.get("text") or "")).strip()
        m = re.match(r"^\s*\d+\.\s*(\S+)\s*(.*)$", raw)
        store, title = (m.group(1), m.group(2).strip()) if m else ("", raw)
        out["targets"].append({"no": no, "store": store, "title": title})
    if not out["targets"]:
        out["error"] = "신고대상 0건"
    return out


def right_tokens(right_name):
    """권리명 → 한글/영문 run 분리 토큰(2자 이상, 숫자 무시, 순서 유지 중복제거)."""
    toks = []
    for t in re.findall(r"[가-힣]+|[A-Za-z]+", right_name or ""):
        if len(t) >= 2 and t not in toks:
            toks.append(t)
    return toks


def _norm(s):
    return re.sub(r"\s+", "", str(s or "")).lower()


def filter_copies(items, tokens, exclude_pids):
    """상품명에 토큰 하나라도(대소문자·공백 무시) 들어간 항목만. 원본·중복 productId 제외."""
    toks = [_norm(t) for t in tokens if t]
    out, seen = [], set(str(p) for p in (exclude_pids or ()))
    for it in items or []:
        if not isinstance(it, dict):
            continue
        pid = str(it.get("productId") or "")
        if not pid or pid in seen:
            continue
        name = _norm(it.get("상품명"))
        if any(t in name for t in toks):
            seen.add(pid)
            out.append(it)
    return out


def store_market(name, stores):
    """스토어명 → 마켓번호(정확일치). stores 값은 {"name":..} 또는 이름 문자열."""
    key = (name or "").strip()
    if not key:
        return None
    for market, v in (stores or {}).items():
        nm = v.get("name") if isinstance(v, dict) else v
        if str(nm or "").strip() == key:
            return market
    return None


def ledger_should_skip(rows, receipt):
    """해당 대표접수번호의 **마지막** 행이 done 일 때만 건너뛴다(failed/partial 은 재시도)."""
    last = None
    for r in rows or []:
        if r.get("receipt") == receipt:
            last = r
    return bool(last and last.get("status") == "done")


def load_appeal_text(path=APPEAL_PATH):
    """고정 소명 문구. 500자 초과면 AssertionError (소명란 제한)."""
    with open(path, encoding="utf-8") as f:
        s = f.read()
    assert s.strip(), "소명 문구가 비었다"
    assert len(s) <= APPEAL_MAX, f"소명 문구 {len(s)}자 > {APPEAL_MAX}자"
    return s


def _cut(s, n):
    s = str(s or "")
    return s if len(s) <= n else s[:n - 1] + "…"


def build_report(result):
    """카톡 보고 → (text, link). text 는 200자 이내. 실패 시 소명링크는 link 로(본문 X)."""
    r = result
    receipt = r.get("receipt") or "?"
    head = f"신고자 {_cut(r.get('reporter'), 20)} · {_cut(r.get('right_name'), 30)}"
    dele = (f"삭제 {r.get('deleted', 0)}(복사본 {r.get('copies', 0)}, 잠금 {r.get('locked', 0)}"
            + (f", 기삭제 {r['already_deleted']}" if r.get("already_deleted") else "") + ")")
    mc = r.get("market_confirmed")
    mtxt = "마켓삭제 확인" if mc else ("마켓삭제 미확인" if mc is False else "마켓삭제 해당없음")
    status = r.get("status")
    if status == "failed":
        text = (f"[권리침해] 수동 처리 필요 {receipt}\n{head}\n실패단계 {r.get('fail_stage') or '?'}\n"
                f"OTP {r.get('otp') or '?'} (링크 버튼)\n{dele} · {mtxt}")
        link = r.get("link") or "https://mail.google.com"
    else:
        tail = "소명 완료" if r.get("appeal_ok") else "소명 미실행"
        if status == "partial":
            tail += " · 일부 미완(내일 재시도)"
        text = f"[권리침해] {tail} {receipt}\n{head}\n{dele} · {mtxt}"
        if status == "partial" and r.get("fail_stage"):
            text += f"\n미완단계 {r['fail_stage']}"
        link = None
    return _cut(text, KAKAO_MAX), link
