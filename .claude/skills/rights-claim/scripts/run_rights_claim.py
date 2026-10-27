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
import argparse
import email
import fcntl
import html
import imaplib
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
SKILLS_DIR = os.path.dirname(SKILL_DIR)
CLAUDE_DIR = os.path.dirname(SKILLS_DIR)
WS_ROOT = os.path.dirname(CLAUDE_DIR)
LIB_DIR = os.path.join(CLAUDE_DIR, "lib")
SOLD_LOCK_DIR = os.path.join(SKILLS_DIR, "sold-lock", "scripts")
ATTR_TAG_DIR = os.path.join(SKILLS_DIR, "attr-tag", "scripts")
CATFIX_DIR = os.path.join(SKILLS_DIR, "bulsaja-category-fix", "scripts")
MAIL_DIR = os.path.join(WS_ROOT, "10-projects", "이메일-자동화")
APPEAL_PATH = os.path.join(SKILL_DIR, "references", "소명문구.txt")
STORES_PATH = os.path.expanduser("~/.eroom/naver-commerce-stores.json")
ASIDE_BIN = "/Users/choiyongsmacbook/.local/bin/aside"

for _p in (SOLD_LOCK_DIR, LIB_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import sold_lock_rules as SR  # noqa: E402  (redact · lock_state)

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


# ===========================================================================
# 대장 (ledger.jsonl) — append-only. 링크·OTP 는 저장하지 않는다
# ===========================================================================
def ledger_dir(data_root):
    return os.path.join(data_root, "rights-claim")


def read_ledger(data_root):
    path = os.path.join(ledger_dir(data_root), "ledger.jsonl")
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return rows


def _now_iso():
    return datetime.now(SR.KST).isoformat(timespec="seconds")


def ledger_append(data_root, row):
    d = ledger_dir(data_root)
    os.makedirs(d, exist_ok=True)
    row = dict(row)
    row.setdefault("ts", _now_iso())
    with open(os.path.join(d, "ledger.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()


LEDGER_FIELDS = ("receipt", "explain_no", "reporter", "right_name", "right_no", "to", "mail_date", "status",
                 "deleted", "copies", "locked", "already_deleted", "market_confirmed", "appeal_ok",
                 "fail_stage", "issues", "shot", "targets")


# ===========================================================================
# Aside 소명페이지 JS — ref 하드코딩 금지, 셀렉터만. 값은 json.dumps 로 주입
# ===========================================================================
# Aside 의 Playwright 판엔 getByPlaceholder 가 없다(2026-10-27 실측 "not a function") → 속성 셀렉터로
_JS_OPEN = r"""
  const OTP_SEL = 'input[placeholder="인증번호를 입력하세요."]';
  const APPEAL_SEL = 'textarea[placeholder^="재게시를 요청하는 이유"]';
  const __sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const PRODUCT_SEL = 'a[href*="smartstore.naver.com/main/products/"]';
  const __arrived = async (p) => {
    if (p.url().includes('/explains/')) return true;
    try {
      return (await p.locator(PRODUCT_SEL).count()) > 0 || (await p.locator(APPEAL_SEL).count()) > 0;
    } catch (e) { return false; }
  };
  const __open = async (link, otp) => {
    const p = await openTab(link);
    globalThis.rcPage = p;
    globalThis.rcLink = link;
    await p.locator(OTP_SEL).first().fill(otp);
    await p.getByRole('button', { name: '확인', exact: true }).click();
    for (let i = 0; i < 30 && !(await __arrived(p)); i++) await __sleep(500);
    if (!(await __arrived(p))) throw new Error('소명 페이지로 이동 안 됨 (OTP 단계)');
    return p;
  };
"""


def js_lookup(link, otp):
    """OTP 입력 → /explains/ 대기 → 신고대상 상품번호·항목 텍스트를 센티널로 출력."""
    return ("await (async () => {\n" + _JS_OPEN + r"""
  const LINK = __LINK__, OTP = __OTP__;
  try {
    const p = await __open(LINK, OTP);
    const targets = await p.locator(PRODUCT_SEL).evaluateAll((as) => as.map((a) => {
      const m = (a.href || '').match(/products\/(\d+)/);
      const no = m ? m[1] : '';
      let text = '';
      for (let el = a.parentElement, d = 0; el && d < 6 && !text; el = el.parentElement, d++) {
        const lines = (el.innerText || '').split('\n').map((s) => s.trim()).filter(Boolean);
        const idx = lines.findIndex((l) => no && l.includes(no));
        for (let i = idx; i >= 0; i--) { if (/^\d+\.\s/.test(lines[i])) { text = lines[i]; break; } }
      }
      return { no, text };
    }));
    let em = p.url().match(/explains\/([0-9A-Z]+)/);
    if (!em) { const bm = (await p.locator('body').innerText()).match(/(\d{6})-([A-Z]\d{6})/); if (bm) em = [0, bm[1] + bm[2]]; }
    console.log('###RC###' + JSON.stringify({ ok: true, url: p.url(), explainNo: em ? em[1] : '', targets }));
  } catch (e) {
    console.log('###RC###' + JSON.stringify({ ok: false, error: String(e && e.message || e) }));
  }
})();
""").replace("__LINK__", json.dumps(link)).replace("__OTP__", json.dumps(otp))


def js_appeal(link, otp, text, shot_path):
    """소명란 입력 → 서약 체크 → 소명 접수하기 → 성공 문구 확인. 실패 시 스크린샷."""
    return ("await (async () => {\n" + _JS_OPEN + r"""
  const LINK = __LINK__, OTP = __OTP__, TEXT = __TEXT__, SHOT = __SHOT__, OKTXT = __OKTXT__;
  // Aside 의 fs 는 세션 폴더 밖에 못 쓴다 → base64 로 돌려주고 파이썬이 저장한다
  const __shot = async (pg) => {
    if (!SHOT) return '';
    try { const buf = await pg.screenshot({ fullPage: true, type: 'png' }); return Buffer.from(buf).toString('base64'); }
    catch (e) { return ''; }
  };
  let p = globalThis.rcPage;
  try {
    let alive = false;
    try {
      // 같은 소명링크로 연 페이지일 때만 재사용 (다른 건의 페이지에 제출하는 사고 방지)
      alive = !!p && globalThis.rcLink === LINK && !(p.isClosed && p.isClosed()) &&
        (await p.locator(APPEAL_SEL).count()) > 0;
    } catch (e) { alive = false; }
    if (!alive) p = await __open(LINK, OTP);
    await p.locator(APPEAL_SEL).first().fill(TEXT);
    const cb = p.getByRole('checkbox', { name: '서약 및 동의' });
    try { if (!(await cb.isChecked())) await p.locator('label', { hasText: '서약 및 동의' }).first().click(); } catch (e) {}
    if (!(await cb.isChecked())) await cb.check({ force: true });
    const btn = p.getByRole('button', { name: '소명 접수하기' });
    for (let i = 0; i < 20 && !(await btn.isEnabled()); i++) await __sleep(500);
    await btn.click();
    let ok = false;
    for (let i = 0; i < 30 && !ok; i++) {
      const body = (await p.locator('body').innerText()).replace(/\s+/g, '');
      ok = body.includes(OKTXT);
      if (!ok) await __sleep(500);
    }
    let shot = '';
    if (!ok) shot = await __shot(p);
    console.log('###RC###' + JSON.stringify({ ok, url: p.url(), shot }));
    if (ok) { try { await closeTab(p); } catch (e) {} globalThis.rcPage = null; globalThis.rcLink = null; }
  } catch (e) {
    let shot = '';
    if (p) shot = await __shot(p);
    console.log('###RC###' + JSON.stringify({ ok: false, error: String(e && e.message || e), shot }));
  }
})();
""").replace("__LINK__", json.dumps(link)).replace("__OTP__", json.dumps(otp)) \
        .replace("__TEXT__", json.dumps(text, ensure_ascii=False)).replace("__SHOT__", json.dumps(shot_path or "")) \
        .replace("__OKTXT__", json.dumps(SUCCESS_TEXT_NOSPACE, ensure_ascii=False))


JS_CLEANUP = ("await (async () => { const p = globalThis.rcPage; if (p) { try { await closeTab(p); } catch (e) {} } "
              "globalThis.rcPage = null; globalThis.rcLink = null; console.log('###RC###{\"ok\":true}'); })();")


# ===========================================================================
# 어댑터
# ===========================================================================
class _Log:
    """진행로그 — 항상 시크릿을 마스킹해서 찍는다."""

    def __init__(self, secrets):
        self.secrets = secrets

    def __call__(self, msg):
        print(SR.redact(msg, self.secrets), flush=True)


class AsideMCP:
    """`aside mcp` 최소 stdio JSON-RPC 클라이언트 (claude -p 안 씀).

    줄 단위 JSON. 응답은 요청 id 와 일치하는 줄만 채택하고 통지·로그 줄은 무시한다.
    repl 변수(globalThis.rcPage)는 같은 aside 프로세스 안에서 호출 간 유지된다.
    """

    def __init__(self, cmd=None, timeout=120):
        self.cmd = cmd or [ASIDE_BIN, "mcp"]
        self.timeout = timeout
        self.proc = None
        self.q = queue.Queue()
        self._id = 0

    def _reader(self):
        try:
            for line in self.proc.stdout:
                self.q.put(line)
        except Exception:
            pass
        self.q.put(None)

    def _send(self, obj):
        self.proc.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def _request(self, method, params, timeout=None):
        self._id += 1
        rid = self._id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        deadline = time.monotonic() + (timeout or self.timeout)
        while True:
            remain = deadline - time.monotonic()
            if remain <= 0:
                raise TimeoutError(f"aside {method} 응답 시간초과")
            try:
                line = self.q.get(timeout=remain)
            except queue.Empty:
                raise TimeoutError(f"aside {method} 응답 시간초과")
            if line is None:
                raise RuntimeError("aside mcp 프로세스가 종료됨")
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if not isinstance(msg, dict) or msg.get("id") != rid:
                continue
            if msg.get("error"):
                raise RuntimeError(f"aside {method} 오류: {str(msg['error'])[:300]}")
            return msg.get("result") or {}

    def open(self):
        self.proc = subprocess.Popen(self.cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, bufsize=1, encoding="utf-8")
        threading.Thread(target=self._reader, daemon=True).start()
        self._request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                     "clientInfo": {"name": "rights-claim", "version": "1.0"}})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def repl(self, title, code, timeout=None):
        if self.proc is None:
            self.open()
        res = self._request("tools/call", {"name": "repl", "arguments": {"title": title, "code": code}}, timeout)
        text = "\n".join(str(c.get("text") or "") for c in res.get("content") or [] if isinstance(c, dict))
        if res.get("isError"):
            raise RuntimeError(f"repl 오류: {text[:300]}")
        return text

    def close(self):
        if not self.proc:
            return
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.terminate()
            self.proc.wait(5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _imap_date(dt):
    """IMAP SINCE 날짜(로케일 무관 영문 월)."""
    return f"{dt.day:02d}-{_MONTHS[dt.month - 1]}-{dt.year}"


def _mail_bodies(msg):
    """(html, plain) 본문. 첨부는 건너뛴다."""
    h = p = None
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if str(part.get("Content-Disposition") or "").lower().startswith("attachment"):
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        cs = part.get_content_charset() or "utf-8"
        try:
            s = payload.decode(cs, "replace")
        except LookupError:
            s = payload.decode("utf-8", "replace")
        ct = part.get_content_type()
        if ct == "text/html" and h is None:
            h = s
        elif ct == "text/plain" and p is None:
            p = s
    return h, p


class MailSource:
    """수집함 IMAP — imap_triage(계정·키체인 비번·헤더 디코드) 재사용. 읽기전용(BODY.PEEK)."""

    def __init__(self, secrets, log):
        self.secrets = secrets
        self.log = log

    def fetch(self, since_days):
        if MAIL_DIR not in sys.path:
            sys.path.insert(0, MAIL_DIR)
        from imap_triage import ACCOUNT, decode, find_special, get_password
        pw = get_password()
        self.secrets.append(pw)
        out = []
        M = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        try:
            M.login(ACCOUNT, pw)
            # 전체보관함(읽고 보관한 메일도 잡힘) → 실패하면 INBOX
            box = find_special(M, "\\All", '"[Gmail]/All Mail"')
            typ, _ = M.select(box, readonly=True)
            if typ != "OK":
                M.select("INBOX", readonly=True)
            since = _imap_date(datetime.now() - timedelta(days=since_days))
            typ, data = M.uid("SEARCH", None, "SINCE", since, "FROM", f'"{CLAIM_FROM}"')
            uids = (data[0] or b"").split() if typ == "OK" and data else []
            for uid in uids:
                try:
                    typ, d = M.uid("FETCH", uid, "(BODY.PEEK[])")
                    raw = next((x[1] for x in d or [] if isinstance(x, tuple)), None)
                    if not raw:
                        continue
                    msg = email.message_from_bytes(raw)
                    frm, subj = decode(msg.get("From")), decode(msg.get("Subject"))
                    if not is_claim_mail(frm, subj):
                        continue
                    to, date = decode(msg.get("To")), decode(msg.get("Date"))
                    h, p = _mail_bodies(msg)
                    cand = [parse_mail(b, to=to, date=date, subject=subj) for b in (h, p) if b]
                    good = [c for c in cand if "error" not in c]
                    out.append((good or cand or [parse_mail("", to=to, date=date, subject=subj)])[0])
                except Exception as e:
                    self.log(f"[mail] uid {uid!r} 읽기 실패: {type(e).__name__}: {e}")
        finally:
            try:
                M.logout()
            except Exception:
                pass
        return out


# ===========================================================================
# 오케스트레이션
# ===========================================================================
FIND_TOOL = "bulsaja_product_find_by_code"
DELETE_TOOL = "bulsaja_market_delete"
PROFILE_TOOL = "bulsaja_my_profile"
DELETE_ARGS = {"scope": "ALL", "deleteAction": "MARKET_AND_SOURCE"}   # category_gate.DELETE_ARGS 와 같은 값
FIND_BATCH = 50
NOT_FOUND_MARK = "원상품번호를 찾지 못함"
DELETE_OK = ("접수", "이미없음")


class Deps:
    """외부 의존성 묶음. 테스트는 가짜를 넣고, 실제 구현은 main() 에서만 만든다."""

    def __init__(self, mail=None, aside_factory=None, commerce_factory=None, bulsaja_factory=None,
                 delete_batch=None, kakao=None, stores=None, data_root=None, sleep=time.sleep,
                 appeal_text=None, confirm_rounds=40, confirm_interval=30, secrets=None):
        self.mail = mail
        self.aside_factory = aside_factory
        self.commerce_factory = commerce_factory
        self.bulsaja_factory = bulsaja_factory
        self.delete_batch = delete_batch
        self.kakao = kakao
        self.stores = stores or {}
        self.data_root = data_root
        self.sleep = sleep
        self.appeal_text = appeal_text
        self.confirm_rounds = confirm_rounds
        self.confirm_interval = confirm_interval
        self.secrets = secrets if secrets is not None else []


class _Ctx:
    """한 번의 실행 동안 공유하는 지연 생성 핸들."""

    def __init__(self, deps):
        self.deps = deps
        self._aside = None
        self._commerce = None

    def aside(self):
        if self._aside is None:
            self._aside = self.deps.aside_factory()
        return self._aside

    def commerce(self):
        if self._commerce is None:
            self._commerce = self.deps.commerce_factory()
        return self._commerce

    def close(self):
        if self._aside is not None:
            try:
                self._aside.repl("rc-cleanup", JS_CLEANUP)      # 남은 소명 탭 닫기
            except Exception:
                pass
            try:
                self._aside.close()
            except Exception:
                pass


def _seller_code(product):
    op = (product or {}).get("originProduct") or {}
    code = (((op.get("detailAttribute") or {}).get("sellerCodeInfo") or {}).get("sellerManagementCode") or "")
    return str(code).strip(), str(op.get("statusType") or "")


def _find_items(mcp, codes):
    """find_by_code 배치 조회 → 항목 리스트. `항목` 키가 없으면 예외("못 물어봤다"를 0건으로 접지 않는다)."""
    items = []
    for i in range(0, len(codes), FIND_BATCH):
        chunk = codes[i:i + FIND_BATCH]
        r = mcp.call_tool(FIND_TOOL, {"codes": chunk})
        v = (r or {}).get("항목")
        if not isinstance(v, list):
            raise RuntimeError(f"find_by_code 응답 모양 이상: {str(r)[:160]}")
        items += [x for x in v if isinstance(x, dict)]
    return items


def _resolve_targets(ctx, targets, res, log):
    """신고 상품번호 → (마켓, 판매자상품코드). 이미 삭제된 상품은 already_deleted."""
    stores = ctx.deps.stores
    issues = []
    for t in targets:
        no = t["no"]
        market = t.get("market") or store_market(t.get("store"), stores)
        candidates = [market] if market else list(stores)
        if not market:
            t["fallback"] = True
        product, err, gone = None, "", False
        for mk in candidates:
            try:
                product = ctx.commerce().get_product(mk, no)
                t["market"] = mk
                break
            except RuntimeError as e:
                if NOT_FOUND_MARK in str(e):
                    if market:          # 정확한 마켓에서 못 찾음 = 이미 삭제됨
                        gone = True
                        break
                    continue
                err = f"{type(e).__name__}: {e}"
                if market:
                    break
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                if market:
                    break
        if gone:
            t["state"] = "already_deleted"
            res["already_deleted"] += 1
            log(f"  - {no} ({market}) 커머스에 없음 → 이미 삭제됨")
            continue
        if product is None:
            t["state"] = "commerce_failed"
            issues.append("commerce")
            log(f"  - {no} 커머스 조회 실패: {err or '전 마켓에서 못 찾음'}")
            continue
        code, status = _seller_code(product)
        t["seller_code"], t["status"] = code, status
        if not code:
            t["state"] = "commerce_failed"
            issues.append("commerce")
            log(f"  - {no} ({t['market']}) 판매자상품코드 없음")
            continue
        t["state"] = "resolved"
        log(f"  - {no} ({t['market']}{', 폴백' if t.get('fallback') else ''}) 판매자코드 {code} · {status}")
    return issues


def _bulsaja_stage(ctx, args, res, targets, log):
    """불사자: 계정 확인 → 원본+상표명 복사본 → (dry: 미리보기 / apply: 삭제).

    반환 (hard_fail_stage or '', issues, nick_bad, confirm_nos)
    """
    deps = ctx.deps
    codes = [t["seller_code"] for t in targets if t.get("state") == "resolved"]
    if not codes:
        return "", [], False, []
    issues = []
    try:
        mcp = deps.bulsaja_factory()
        mcp.open()
    except Exception as e:
        log(f"[불사자] 연결 실패: {type(e).__name__}: {e}")
        return "bulsaja_connect", issues, False, []
    try:
        try:
            nick = str((mcp.call_tool(PROFILE_TOOL, {}) or {}).get("닉네임") or "")
        except Exception as e:
            log(f"[불사자] 계정 조회 실패: {type(e).__name__}")
            return "bulsaja_account", issues, True, []
        if nick != args.expect_nick:
            log(f"[불사자] 계정이 '{args.expect_nick}' 가 아니다 (현재 '{nick}') — 삭제·소명 중단")
            return "bulsaja_account", issues, True, []

        try:
            code_set = set(codes)
            originals = [it for it in _find_items(mcp, codes) if str(it.get("판매자상품코드") or "") in code_set]
            found_codes = {str(it.get("판매자상품코드")) for it in originals}
            missing = [c for c in codes if c not in found_codes]
            if missing:
                issues.append("bulsaja_find")
                log(f"[불사자] 판매자코드로 못 찾음 {len(missing)}건: {', '.join(missing)}")
            bcodes = sorted({str(it.get("불사자코드") or "") for it in originals} - {""})
            sibling = [it for it in _find_items(mcp, bcodes) if str(it.get("불사자코드") or "") in set(bcodes)] \
                if bcodes else []
        except Exception as e:
            log(f"[불사자] find_by_code 실패: {type(e).__name__}: {e}")
            return "bulsaja_find", issues, False, []

        orig_pids = []
        for it in originals:
            pid = str(it.get("productId") or "")
            if pid and pid not in orig_pids:
                orig_pids.append(pid)
        copies = filter_copies(sibling, right_tokens(res.get("right_name")), set(orig_pids))
        copy_pids = {str(c["productId"]) for c in copies}
        to_delete, locked_pids = [], []
        by_pid = {}
        for it in originals + copies:
            pid = str(it.get("productId") or "")
            if not pid or pid in by_pid:
                continue
            by_pid[pid] = it
            if SR.lock_state(it) is True:
                locked_pids.append(pid)
            else:
                to_delete.append(pid)
        res["locked"] = len(locked_pids)
        for pid in to_delete + locked_pids:
            it = by_pid[pid]
            kind = "복사본" if pid in copy_pids else "원본"
            mark = " [잠금-제외]" if pid in locked_pids else ""
            log(f"  · {kind} {pid} 판매자코드 {it.get('판매자상품코드')} 불사자코드 {it.get('불사자코드')} "
                f"{_cut(it.get('상품명'), 40)}{mark}")
        log(f"[불사자] 원본 {len(orig_pids)} · 상표명 복사본 {len(copies)} · 잠금 {len(locked_pids)} "
            f"→ 삭제대상 {len(to_delete)}")

        # 확인 폴링 대상: 잠금 아닌 원본이 있는 신고 상품
        del_codes = {str(by_pid[p].get("판매자상품코드")) for p in to_delete if p not in copy_pids}
        confirm_nos = [t for t in targets if t.get("state") == "resolved" and t["seller_code"] in del_codes]

        if not to_delete:
            return "", issues, False, confirm_nos
        if not args.apply:
            # 미리보기 = 확인키 2단계의 1단계(confirm=true → 계획+토큰). 토큰 재제출은 절대 안 한다
            try:
                plan = mcp.call_tool(DELETE_TOOL, dict(DELETE_ARGS, productIds=to_delete, confirm=True))
                tok = (plan or {}).get("confirmationToken")
                if tok:
                    deps.secrets.append(str(tok))
                log(f"[dry-run] 삭제 미리보기: 확인키 {'발급됨' if tok else '없음'} · "
                    f"{_cut((plan or {}).get('message') or plan, 120)} (재제출 안 함)")
            except Exception as e:
                log(f"[dry-run] 삭제 미리보기 실패: {type(e).__name__}: {e}")
            return "", issues, False, confirm_nos

        try:
            results = deps.delete_batch(mcp, to_delete, log)
        except Exception as e:
            log(f"[불사자] 삭제 호출 실패: {type(e).__name__}: {e}")
            return "delete", issues, False, []
        ok_pids = set()
        for r in results or []:
            pid, j = str(r.get("productId")), r.get("판정")
            if j in DELETE_OK:
                ok_pids.add(pid)
                res["deleted"] += 1
                if pid in copy_pids:
                    res["copies"] += 1
            elif j == "잠금":
                res["locked"] += 1
            else:
                issues.append("delete")
                log(f"  ! 삭제 {j}: {pid} {_cut(r.get('사유'), 80)}")
        res["delete_results"] = [{"productId": r.get("productId"), "판정": r.get("판정")} for r in results or []]
        ok_codes = {str(by_pid[p].get("판매자상품코드")) for p in ok_pids if p not in copy_pids}
        confirm_nos = [t for t in confirm_nos if t["seller_code"] in ok_codes]
        return "", sorted(set(issues)), False, confirm_nos
    finally:
        try:
            mcp.close()
        except Exception:
            pass


def _confirm_market(ctx, confirm_targets, log):
    """원본 상품번호를 커머스로 재조회 — 없어지거나 SALE 아님이면 확인. 상한 rounds×interval."""
    deps = ctx.deps
    pending = {t["no"]: t["market"] for t in confirm_targets}
    for rnd in range(1, deps.confirm_rounds + 1):
        for no, mk in list(pending.items()):
            try:
                _, status = _seller_code(ctx.commerce().get_product(mk, no))
                if status and status != "SALE":
                    pending.pop(no)
            except RuntimeError as e:
                if NOT_FOUND_MARK in str(e):
                    pending.pop(no)
            except Exception:
                pass
        if not pending:
            log(f"[확인] 마켓삭제 확인 ({rnd}회차)")
            return True
        if rnd < deps.confirm_rounds:
            deps.sleep(deps.confirm_interval)
    log(f"[확인] 마켓삭제 미확인 {len(pending)}건: {', '.join(pending)}")
    return False


def save_shot(b64, path, log=print):
    """repl 이 돌려준 base64 PNG 를 저장 → 경로. 없거나 실패면 ''."""
    if not b64 or not isinstance(b64, str):
        return ""
    try:
        import base64
        data = base64.b64decode(b64, validate=False)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return path
    except Exception as e:
        log(f"[aside] 스크린샷 저장 실패: {type(e).__name__}: {e}")
        return ""


def process_claim(ctx, args, m, rows, log):
    """소명요청 1건 처리 → 종료코드(0/1/3)."""
    deps = ctx.deps
    dry = not args.apply
    link, otp = m.get("link") or "", m.get("otp") or ""
    if otp:
        deps.secrets.append(otp)
    if link:
        deps.secrets.append(link)
        if "code=" in link:
            deps.secrets.append(link.split("code=", 1)[1])
    res = {"receipt": m.get("receipt") or "", "explain_no": "", "reporter": m.get("reporter") or "",
           "right_name": m.get("right_name") or "", "right_no": m.get("right_no") or "",
           "to": m.get("to") or "", "mail_date": m.get("mail_date") or "", "status": "",
           "deleted": 0, "copies": 0, "locked": 0, "already_deleted": 0, "market_confirmed": None,
           "appeal_ok": False, "fail_stage": "", "issues": [], "shot": "", "targets": [],
           "otp": otp, "link": link}
    log(f"[소명요청] 대표접수번호 {res['receipt'] or '?'} · 신고자 {res['reporter']} · "
        f"권리 {res['right_name']}({res['right_no']}) · To {res['to']} · 메일 {res['mail_date']}")
    link_disp = (LINK_PREFIX + "***") if link.startswith(LINK_PREFIX) else "-"
    log(f"  링크 {link_disp} · OTP {('***(' + str(len(otp)) + '자리)') if otp else '-'}")

    hard, nick_bad, issues = "", False, []
    targets = []
    if m.get("error"):
        hard = "mail"
        log(f"[mail] 파싱 실패: {m['error']}")
    else:
        prior = None
        for r in rows:
            if r.get("receipt") == res["receipt"]:
                prior = r
        reuse = bool(prior and prior.get("appeal_ok") and prior.get("targets"))
        # ① 신고대상
        if reuse:
            targets = [dict(t) for t in prior["targets"]]
            res["explain_no"] = prior.get("explain_no") or ""
            res["appeal_ok"] = True
            log(f"[재시도] 소명은 이미 접수됨 — 저장된 신고대상 {len(targets)}건으로 삭제·확인만")
        elif args.no_browser:
            log("[aside] --no-browser — 소명페이지 조회 생략(신고대상 없음으로 진행)")
        else:
            try:
                d = parse_targets(ctx.aside().repl("rc-lookup", js_lookup(link, otp)))
            except Exception as e:
                d = {"targets": [], "error": f"{type(e).__name__}: {e}"}
            if d.get("error"):
                hard = "aside_lookup"
                log(f"[aside] 소명페이지 조회 실패: {d['error']}")
            else:
                targets = d["targets"]
                res["explain_no"] = d.get("explain_no") or ""
                log(f"[aside] 개별접수번호 {res['explain_no']} · 신고대상 {len(targets)}건")
                for t in targets:
                    log(f"  - {t['no']} [{t['store']}] {_cut(t['title'], 50)}")
        # ② 커머스
        if not hard and targets:
            issues += _resolve_targets(ctx, targets, res, log)
            if not any(t.get("state") in ("resolved", "already_deleted") for t in targets):
                hard = "commerce"
        # ③ 불사자
        confirm_targets = []
        if not hard and targets:
            h, iss, nick_bad, confirm_targets = _bulsaja_stage(ctx, args, res, targets, log)
            hard = h
            issues += iss
        # ④ 마켓삭제 확인
        if not hard and not dry and targets:
            if confirm_targets:
                res["market_confirmed"] = _confirm_market(ctx, confirm_targets, log)
                if not res["market_confirmed"]:
                    issues.append("confirm")
            elif res["already_deleted"] and not any(t.get("state") == "resolved" for t in targets):
                res["market_confirmed"] = True
        # ⑤ 소명 제출
        if not hard and not dry and not res["appeal_ok"]:
            if args.no_browser:
                hard = "appeal"
                log("[aside] --no-browser 라 소명 제출 불가")
            else:
                shot = os.path.join(ledger_dir(deps.data_root), "shots",
                                    f"{res['receipt']}_{datetime.now().strftime('%Y%m%d%H%M%S')}.png")
                try:
                    os.makedirs(os.path.dirname(shot), exist_ok=True)
                    p = _sentinel_payload(ctx.aside().repl("rc-appeal", js_appeal(link, otp, deps.appeal_text, shot)))
                except Exception as e:
                    p = {"ok": False, "error": f"{type(e).__name__}: {e}"}
                p = p if isinstance(p, dict) else {"ok": False, "error": "센티널 없음"}
                res["appeal_ok"] = bool(p.get("ok"))
                res["shot"] = save_shot(p.get("shot"), shot, log)
                if res["appeal_ok"]:
                    log("[aside] 소명 접수 완료 (성공 문구 확인)")
                else:
                    hard = "appeal"
                    log(f"[aside] 소명 제출 실패: {p.get('error') or '성공 문구 미확인'}"
                        + (f" · 스크린샷 {res['shot']}" if res["shot"] else ""))
        res["targets"] = [{k: t.get(k) for k in ("no", "store", "market", "seller_code", "state") if t.get(k)}
                          for t in targets]

    res["issues"] = sorted(set(issues))
    if dry:
        res["status"] = "dry-run"
        log(f"[dry-run] 결과: {'실패 단계 ' + hard if hard else '조회 정상'}"
            + (f" · 미완 {','.join(res['issues'])}" if res["issues"] else "")
            + " — 삭제·소명·카톡·대장 쓰기 없음")
        return 1 if hard else 0

    if hard:
        res["status"], res["fail_stage"] = "failed", hard
    elif res["issues"]:
        res["status"], res["fail_stage"] = "partial", ",".join(res["issues"])
    else:
        res["status"] = "done"
    row = {k: res.get(k) for k in LEDGER_FIELDS}
    try:
        ledger_append(deps.data_root, row)
    except Exception as e:
        log(f"[대장] 기록 실패: {type(e).__name__}: {e}")
    text, klink = build_report(res)
    try:
        deps.kakao(text, klink)
    except Exception as e:
        log(f"[kakao] 발송 실패: {type(e).__name__}: {e}")
    log(f"[결과] {res['receipt']} {res['status']}" + (f" ({res['fail_stage']})" if res["fail_stage"] else ""))
    if nick_bad:
        return 3
    return 0 if res["status"] == "done" else 1


def run(args, deps):
    """1회 실행 → 종료코드. 0 정상 · 1 실패/부분 있음 · 3 불사자 계정 불일치 · 4 다른 실행 중."""
    log = _Log(deps.secrets)
    if args.mark_done:
        ledger_append(deps.data_root, {"receipt": args.mark_done, "status": "done", "source": "manual"})
        log(f"[대장] {args.mark_done} done 기록 (수동)")
        return 0
    if not args.apply and not args.dry_run:
        log("[안내] --apply 가 없어 dry-run 으로 동작한다 (삭제·소명·카톡 없음)")
    d = ledger_dir(deps.data_root)
    os.makedirs(d, exist_ok=True)
    lockf = open(os.path.join(d, ".lock"), "w")
    try:
        try:
            fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            log("[중단] 다른 rights-claim 실행 중")
            return 4
        try:
            mails = deps.mail.fetch(args.since_days)
        except BaseException as e:      # get_password 는 SystemExit 을 던진다
            if isinstance(e, KeyboardInterrupt):
                raise
            log(f"[mail] 수집함 조회 실패: {type(e).__name__}: {e}")
            return 1
        rows = read_ledger(deps.data_root)
        claims, seen = [], set()
        for m in reversed(mails):           # 최신 메일 우선, 같은 접수번호는 1회
            rc = m.get("receipt") or ""
            if args.receipt and rc != args.receipt:
                continue
            if rc and rc in seen:
                continue
            if rc and not args.receipt and ledger_should_skip(rows, rc):
                log(f"[대장] {rc} 대장 done — 건너뜀")
                seen.add(rc)
                continue
            seen.add(rc)
            claims.append(m)
        if not claims:
            log("새 소명요청 없음")
            return 0
        ctx = _Ctx(deps)
        codes = []
        try:
            for m in claims:
                try:
                    codes.append(process_claim(ctx, args, m, rows, log))
                except Exception as e:
                    log(f"[오류] {m.get('receipt')} 처리 중 예외: {type(e).__name__}: {e}")
                    codes.append(1)
        finally:
            ctx.close()
        return 3 if 3 in codes else (1 if 1 in codes else 0)
    finally:
        try:
            fcntl.flock(lockf, fcntl.LOCK_UN)
        except OSError:
            pass
        lockf.close()


def build_parser():
    ap = argparse.ArgumentParser(description="권리보호센터 소명요청 자동처리")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="조회만 (기본)")
    g.add_argument("--apply", action="store_true", help="삭제·소명·카톡·대장 실제 실행")
    ap.add_argument("--since-days", type=int, default=14, help="수집함 조회 기간(일)")
    ap.add_argument("--receipt", help="이 대표접수번호만 처리 (대장 done 무시)")
    ap.add_argument("--mark-done", metavar="RECEIPT", help="대장에 수동 처리 완료(done) 1행 기록")
    ap.add_argument("--no-browser", action="store_true", help="Aside 단계 전부 생략")
    ap.add_argument("--expect-nick", default="부킹", help="기대 불사자 계정 닉네임")
    return ap


# ===========================================================================
# 실제 의존성 — main() 에서만 만든다
# ===========================================================================
def _real_deps():
    secrets = []
    from eroomlib.config import cfg
    data_root = os.path.expanduser(cfg("paths.data_root", required=True))
    log = _Log(secrets)

    def stores():
        try:
            with open(STORES_PATH, encoding="utf-8") as f:
                raw = json.load(f)
            return {mk: {"name": (v or {}).get("name", "")} for mk, v in raw.items() if isinstance(v, dict)}
        except (OSError, ValueError) as e:
            log(f"[stores] {STORES_PATH} 읽기 실패: {e}")
            return {}

    def commerce_factory():
        if ATTR_TAG_DIR not in sys.path:
            sys.path.insert(0, ATTR_TAG_DIR)
        import attr_tag
        api = attr_tag._default_api(secrets)
        # 전 마켓 키를 한 번에 올린다. 안 그러면 첫 조회 마켓만 로드돼 두 번째 스토어부터 '커머스 키 없음'
        try:
            api.load(list(stores().keys()))
        except Exception as e:
            log(f"[commerce] 키 일괄 로드 실패: {type(e).__name__}")
        return api

    def bulsaja_factory():
        from eroomlib.bulsaja import BulsajaMCP
        return BulsajaMCP()

    def delete_batch(mcp, pids, log_=print):
        if CATFIX_DIR not in sys.path:
            sys.path.insert(0, CATFIX_DIR)
        import category_gate
        return category_gate.delete_batch(mcp, pids, log_)

    def kakao(text, link=None):
        # 카톡 발송 끔 (2026-10-27 용팀장 지시 "도움 안 되니 보내지 마") — 보고문은 로그에만 남긴다
        log(f"[보고] {text}")

    return Deps(mail=MailSource(secrets, log), aside_factory=AsideMCP, commerce_factory=commerce_factory,
                bulsaja_factory=bulsaja_factory, delete_batch=delete_batch, kakao=kakao, stores=stores(),
                data_root=data_root, appeal_text=load_appeal_text(), secrets=secrets)


def _mark_done_deps():
    from eroomlib.config import cfg
    return Deps(data_root=os.path.expanduser(cfg("paths.data_root", required=True)))


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        deps = _mark_done_deps() if args.mark_done else _real_deps()
    except Exception as e:
        print(f"[중단] 초기화 실패: {type(e).__name__}: {e}", flush=True)
        return 1
    return run(args, deps)


if __name__ == "__main__":
    sys.exit(main())
