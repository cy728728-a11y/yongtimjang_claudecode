#!/usr/bin/env python3
"""캡챠 릴레이 — 캡챠 답변의 '판단'만 Aside 에게 파일로 위임한다.

Aside 는 브라우저 탭을 건드리지 않고 답변 텍스트만 파일로 돌려준다.
실제 입력·제출은 항상 호출자(Claude Code)가 한다 → 탭 제어권 충돌 없음.

    python captcha_relay.py capture --match naver          # 캡챠 화면 캡처 + 질문 추출
    python captcha_relay.py ask --id <id> --site <url> --question "..."
    python captcha_relay.py solve --match naver            # capture + ask 한 번에
    python captcha_relay.py ping                           # Aside 감시 routine 생존 확인
    python captcha_relay.py status                         # 대기 중인 요청 목록

종료코드: 0 answered · 3 needs_human · 4 timeout · 5 캡처/환경 실패
"""

import argparse
import json
import os
import random
import re
import string
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta

RELAY_DIR = os.environ.get("CAPTCHA_RELAY_DIR") or os.path.expanduser(
    "~/.aside/u/0/captcha-relay"
)
REQ_DIR = os.path.join(RELAY_DIR, "requests")
RES_DIR = os.path.join(RELAY_DIR, "responses")
ASIDE_BIN = os.environ.get("ASIDE_BIN") or os.path.expanduser("~/.local/bin/aside")

KST = timezone(timedelta(hours=9))

# Aside 는 requests/ 를 주기적으로(최대 5분 간격) 훑는다. 2분으로 잡으면 살아 있는
# 루프인데도 타임아웃으로 오판한다 → 기본 6분.
DEFAULT_TIMEOUT = 360.0
DEFAULT_POLL = 4.0

EXIT_ANSWERED, EXIT_NEEDS_HUMAN, EXIT_TIMEOUT, EXIT_ENV = 0, 3, 4, 5


def _now_iso():
    return datetime.now(KST).isoformat(timespec="seconds")


def new_id():
    """YYYYMMDD-HHMMSS-랜덤4. 같은 초에 두 번 불려도 안 겹치게 랜덤을 붙인다."""
    rnd = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return datetime.now(KST).strftime("%Y%m%d-%H%M%S-") + rnd


def _ensure_dirs():
    try:
        for d in (REQ_DIR, RES_DIR):
            os.makedirs(d, exist_ok=True)
    except OSError as e:
        sys.exit(f"[env] 릴레이 폴더를 만들지 못했다: {RELAY_DIR} ({e})")


def guess_question(text):
    """페이지 본문에서 캡챠 질문 줄을 고른다. 못 고르면 빈 문자열(Aside 가 이미지에서 읽는다)."""
    if not text:
        return ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    # 물음표로 끝나는 줄이 가장 확실한 질문. 없으면 안내 문구를 쓴다.
    for ln in lines:
        if ln.endswith("?") or ln.endswith("니까") or ln.endswith("세요?"):
            if 5 <= len(ln) <= 200:
                return ln
    for ln in lines:
        if re.search(r"보안\s*확인|자동입력\s*방지|보안문자|캡차|captcha", ln, re.I):
            if len(ln) <= 200:
                return ln
    return ""


# ────────────────────────────────────────────────────────────────────────────
# capture — Aside repl 로 캡챠 탭을 붙여 스크린샷 + 본문을 뽑는다
# ────────────────────────────────────────────────────────────────────────────

CAPTURE_JS = r"""
const MATCH = __MATCH__;
const PNG = __PNG__;
const out = { ok: false };
try {
  const tabs = await listBrowserTabs();
  let t = null;
  if (MATCH) t = tabs.find((x) => (x.url || "").includes(MATCH));
  if (!t) t = tabs.find((x) => x.active);
  if (!t) { out.error = "붙일 탭이 없다"; }
  else {
    await attachBrowserTab(t.targetId);
    // 캡챠는 화면 안에 다 들어오지만, 영수증형은 아래로 길어서 fullPage 로 찍는다.
    // path 옵션은 세션 디렉터리 밖을 막는다("escapes the session directory", 2026-08-06 실측).
    // fs.writeFile 은 안 막히므로 버퍼로 받아서 직접 쓴다.
    const buf = await page.screenshot({ fullPage: true });
    await fs.writeFile(PNG, buf);
    const info = await page.evaluate(() => ({
      url: location.href,
      title: document.title,
      text: (document.body.innerText || "").slice(0, 1500),
    }));
    out.ok = true; out.site = info.url; out.title = info.title; out.text = info.text;
  }
} catch (e) {
  out.error = String((e && e.message) || e);
}
console.log("__CAP__ " + JSON.stringify(out));
"""


def run_capture(png_path, match, timeout=90.0):
    """캡챠 탭을 스크린샷으로 저장하고 {ok, site, text} 를 돌려준다."""
    if not os.path.exists(ASIDE_BIN):
        return {"ok": False, "error": f"aside CLI 없음: {ASIDE_BIN}"}
    js = (CAPTURE_JS
          .replace("__MATCH__", json.dumps(match or ""))
          .replace("__PNG__", json.dumps(png_path)))
    try:
        proc = subprocess.run([ASIDE_BIN, "repl", js], capture_output=True,
                              text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "error": f"aside repl 실패: {e}"}
    for line in (proc.stdout or "").splitlines():
        if line.startswith("__CAP__ "):
            try:
                return json.loads(line[8:])
            except ValueError:
                return {"ok": False, "error": "capture 결과 파싱 실패"}
    tail = ((proc.stdout or "") + (proc.stderr or ""))[-300:]
    return {"ok": False, "error": f"capture 응답 없음: {tail}"}


# ────────────────────────────────────────────────────────────────────────────
# submit — 받은 답을 캡챠 입력창에 넣고 제출한다(입력·제출은 항상 이쪽이 한다)
# ────────────────────────────────────────────────────────────────────────────

SUBMIT_JS = r"""
const MATCH = __MATCH__;
const ANSWER = __ANSWER__;
const out = { ok: false, filled: false, submitted: false };

// driver.js 의 PAGESTATE 와 같은 판정 — 단, **URL 조건은 뺐다**.
// driver 는 '캡챠가 떴나'(감지)를 보지만 여기는 '캡챠가 걷혔나'(검증)를 본다.
// URL 에 captcha 가 남아 있어도 화면은 이미 통과일 수 있고, 실제로 그래서
// 성공을 실패로 오판했다(2026-08-06 검증 페이지 파일명에 captcha 가 들어가 오탐).
const PAGESTATE = () => {
  const t = document.body.innerText || "";
  if (/자동입력 방지|보안문자|캡차|captcha/i.test(t)) return "캡챠";
  if (document.querySelector('img[src*="captcha" i], input[id*="captcha" i], input[name*="captcha" i]')) return "캡챠";
  if (/일시적으로 제한|접속이 제한|비정상적인 접근|비정상적인 검색/.test(t)) return "차단";
  return "정상";
};

try {
  const tabs = await listBrowserTabs();
  let t = null;
  if (MATCH) t = tabs.find((x) => (x.url || "").includes(MATCH));
  if (!t) t = tabs.find((x) => x.active);
  if (!t) throw new Error("붙일 탭이 없다 — 캡챠 탭이 닫혔다");
  await attachBrowserTab(t.targetId);

  // 캡챠 전용 셀렉터 → 없으면 화면에 보이는 단일 텍스트 입력. 후보가 여럿이면
  // 아무 데나 넣지 않고 스냅샷을 돌려준다(엉뚱한 칸에 넣으면 캡챠를 한 번 더 태운다).
  const SPECIFIC = 'input[name*="captcha" i], input[id*="captcha" i]';
  const GENERIC = 'input[type="text"]:not([readonly]), input:not([type]):not([readonly])';
  let box = null;
  if (await page.locator(SPECIFIC).count() > 0) box = page.locator(SPECIFIC).first();
  else {
    const n = await page.locator(GENERIC).count();
    if (n === 1) box = page.locator(GENERIC).first();
    else out.candidates = n;
  }

  if (!box) {
    out.error = "입력창을 특정하지 못했다";
    out.tree = (await snapshot(page, { interactive: true })).tree;
  } else {
    await box.fill(ANSWER);
    out.filled = true;
    await page.keyboard.press("Enter");
    await sleep(2500);
    let st = await page.evaluate(PAGESTATE);
    // Enter 를 안 먹는 폼이면 확인/제출 버튼을 눌러 본다.
    if (st === "캡챠") {
      for (const name of ["확인", "제출", "완료", "입력"]) {
        const btn = page.getByRole("button", { name });
        if (await btn.count() > 0) {
          await btn.first().click();
          await sleep(2500);
          st = await page.evaluate(PAGESTATE);
          out.clicked = name;
          break;
        }
      }
    }
    out.submitted = true;
    out.pageState = st;
    out.ok = st === "정상";
    out.url = page.url();
    if (!out.ok) out.error = `제출 후에도 상태가 ${st}`;
  }
} catch (e) {
  out.error = String((e && e.message) || e);
}
console.log("__SUB__ " + JSON.stringify(out));
"""


def run_submit(answer, match, timeout=90.0):
    """답을 입력창에 넣고 제출한 뒤 캡챠가 걷혔는지까지 확인한다."""
    if not os.path.exists(ASIDE_BIN):
        return {"ok": False, "error": f"aside CLI 없음: {ASIDE_BIN}"}
    js = (SUBMIT_JS
          .replace("__MATCH__", json.dumps(match or ""))
          .replace("__ANSWER__", json.dumps(answer)))
    try:
        proc = subprocess.run([ASIDE_BIN, "repl", js], capture_output=True,
                              text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "error": f"aside repl 실패: {e}"}
    for line in (proc.stdout or "").splitlines():
        if line.startswith("__SUB__ "):
            try:
                return json.loads(line[8:])
            except ValueError:
                return {"ok": False, "error": "submit 결과 파싱 실패"}
    tail = ((proc.stdout or "") + (proc.stderr or ""))[-300:]
    return {"ok": False, "error": f"submit 응답 없음: {tail}"}


# ────────────────────────────────────────────────────────────────────────────
# ask — 요청 파일을 쓰고 응답을 폴링한다
# ────────────────────────────────────────────────────────────────────────────

def write_request(rid, site, question, has_png):
    """requests/<id>.json 을 쓴다. png 는 이미 같은 id 로 저장돼 있어야 한다."""
    req = {
        "id": rid,
        "createdAt": _now_iso(),
        "site": site or "",
        "question": question or "",
    }
    if has_png:
        req["screenshot"] = f"{rid}.png"
    path = os.path.join(REQ_DIR, f"{rid}.json")
    try:
        # 임시파일 → rename. Aside 가 반쯤 쓰인 JSON 을 읽고 실패하는 걸 막는다.
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(req, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except OSError as e:
        sys.exit(f"[env] 요청 파일을 쓰지 못했다: {path} ({e})")
    return path


def read_response(rid):
    """responses/<id>.json 을 읽는다. 아직 없거나 쓰는 중이면 None."""
    path = os.path.join(RES_DIR, f"{rid}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        # 쓰는 도중일 수 있다 — 다음 폴링에서 다시 본다.
        return None


def wait_response(rid, timeout=DEFAULT_TIMEOUT, poll=DEFAULT_POLL, quiet=False):
    """응답 파일이 생길 때까지 폴링. 타임아웃이면 None."""
    deadline = time.time() + timeout
    ticks = 0
    while time.time() < deadline:
        res = read_response(rid)
        if res is not None:
            return res
        time.sleep(poll)
        ticks += 1
        if not quiet and ticks % 15 == 0:  # 대략 1분마다
            left = int(deadline - time.time())
            print(f"[wait] {rid} 응답 대기 중… 남은 {left}초", file=sys.stderr, flush=True)
    return None


def finish(rid, res, extra=None):
    """결과를 JSON 한 덩어리로 찍고 상태에 맞는 종료코드를 돌려준다."""
    out = {"id": rid}
    if extra:
        out.update(extra)
    if res is None:
        out.update({"status": "timeout",
                    "note": "Aside 가 제한 시간 안에 답하지 않았다 — 이룸님에게 직접 물어본다"})
        code = EXIT_TIMEOUT
    else:
        out.update({k: v for k, v in res.items() if k != "id"})
        status = res.get("status")
        code = EXIT_ANSWERED if status == "answered" and res.get("answer") else EXIT_NEEDS_HUMAN
        if status == "answered" and not res.get("answer"):
            out["note"] = (out.get("note") or "") + " / answer 가 비어 있어 needs_human 으로 처리"
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return code


# ────────────────────────────────────────────────────────────────────────────
# 서브커맨드
# ────────────────────────────────────────────────────────────────────────────

def open_app_tab(url, wait=3.0):
    """Aside 앱에 탭을 띄운다.

    repl 의 openTab 으로 연 탭은 CLI 프로세스가 끝나면 사라져서(2026-08-06 실측)
    다음 repl 호출이 붙을 수 없다. 릴레이는 요청↔응답 사이에 몇 분이 뜨므로
    반드시 앱 탭이어야 한다.
    """
    try:
        subprocess.run(["open", "-a", "Aside", url], check=True,
                       capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "error": f"Aside 앱 탭 열기 실패: {e}"}
    time.sleep(wait)
    return {"ok": True, "url": url}


def cmd_open(args):
    r = open_app_tab(args.url, args.wait)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r["ok"] else EXIT_ENV


def cmd_submit(args):
    r = run_submit(args.answer, args.match, timeout=args.capture_timeout)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok") else EXIT_ENV


def cmd_capture(args):
    _ensure_dirs()
    rid = args.id or new_id()
    png = os.path.join(REQ_DIR, f"{rid}.png")
    cap = run_capture(png, args.match, timeout=args.capture_timeout)
    ok = bool(cap.get("ok")) and os.path.exists(png)
    out = {
        "id": rid,
        "ok": ok,
        "site": cap.get("site", ""),
        "question": guess_question(cap.get("text", "")),
        "png": png if ok else None,
        "error": cap.get("error"),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if ok else EXIT_ENV


def cmd_ask(args):
    _ensure_dirs()
    rid = args.id or new_id()
    has_png = os.path.exists(os.path.join(REQ_DIR, f"{rid}.png"))
    write_request(rid, args.site, args.question, has_png)
    if not args.no_wait:
        res = wait_response(rid, args.timeout, args.poll, args.quiet)
        return finish(rid, res, {"screenshot": has_png})
    print(json.dumps({"id": rid, "status": "requested", "screenshot": has_png},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_solve(args):
    """(열기 →) capture → ask (→ submit). 스크린샷이 없으면 요청을 보내지 않는다."""
    _ensure_dirs()
    rid = args.id or new_id()
    png = os.path.join(REQ_DIR, f"{rid}.png")
    if args.url:
        op = open_app_tab(args.url, args.open_wait)
        if not op["ok"]:
            print(json.dumps({"id": rid, "status": "open_failed", "error": op["error"]},
                             ensure_ascii=False, indent=2))
            return EXIT_ENV
    cap = run_capture(png, args.match, timeout=args.capture_timeout)
    if not cap.get("ok") or not os.path.exists(png):
        print(json.dumps({"id": rid, "status": "capture_failed",
                          "error": cap.get("error")}, ensure_ascii=False, indent=2))
        return EXIT_ENV
    site = args.site or cap.get("site", "")
    question = args.question or guess_question(cap.get("text", ""))
    write_request(rid, site, question, True)
    print(f"[relay] 요청 전송 {rid} · 질문: {question or '(스크린샷에서 읽도록 위임)'}",
          file=sys.stderr, flush=True)
    res = wait_response(rid, args.timeout, args.poll, args.quiet)
    extra = {"site": site, "question": question, "png": png}

    # 제출은 답을 확신(answered)했을 때만. needs_human·timeout 을 제출로 흘리면
    # 캡챠를 한 번 더 태우고 차단만 깊어진다.
    if args.submit and res and res.get("status") == "answered" and res.get("answer"):
        extra["submit"] = run_submit(res["answer"], args.match, timeout=args.capture_timeout)
    return finish(rid, res, extra)


def cmd_ping(args):
    """Aside 감시 routine 이 살아 있는지 확인한다. 어떤 응답이든 오면 살아 있는 것."""
    _ensure_dirs()
    rid = "ping-" + new_id()
    write_request(rid, "captcha-relay ping (실제 캡챠 아님)",
                  "연결 확인용 요청입니다. status를 answered, answer를 PONG 으로 응답해 주세요.",
                  False)
    res = wait_response(rid, args.timeout, args.poll, args.quiet)
    alive = res is not None
    print(json.dumps({"id": rid, "alive": alive, "response": res},
                     ensure_ascii=False, indent=2))
    return 0 if alive else EXIT_TIMEOUT


def cmd_status(args):
    """응답이 아직 안 온 요청 목록. 릴레이가 막혀 있는지 눈으로 보는 용도."""
    _ensure_dirs()
    try:
        reqs = sorted(f[:-5] for f in os.listdir(REQ_DIR) if f.endswith(".json"))
    except OSError as e:
        sys.exit(f"[env] 요청 폴더를 읽지 못했다: {e}")
    rows = [{"id": r, "answered": read_response(r) is not None} for r in reqs]
    print(json.dumps({"relayDir": RELAY_DIR, "pending": rows},
                     ensure_ascii=False, indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser(description="캡챠 답변 판단을 Aside 에 위임하는 파일 릴레이")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, with_capture=False):
        p.add_argument("--id", help="요청 id. 기본 YYYYMMDD-HHMMSS-rand4")
        p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                       help=f"응답 대기 최대 초. 기본 {DEFAULT_TIMEOUT:.0f}"
                            "(Aside 감시 주기가 최대 5분이라 2분은 짧다)")
        p.add_argument("--poll", type=float, default=DEFAULT_POLL, help="폴링 간격(초)")
        p.add_argument("--quiet", action="store_true", help="대기 진행 로그 끄기")
        if with_capture:
            p.add_argument("--match", default="", help="붙을 탭 URL 부분문자열. 기본 활성 탭")
            p.add_argument("--capture-timeout", type=float, default=90.0,
                           help="aside repl 캡처 타임아웃(초)")

    p = sub.add_parser("capture", help="캡챠 탭 스크린샷 + 질문 추출(요청은 안 보냄)")
    common(p, with_capture=True)
    p.set_defaults(func=cmd_capture)

    p = sub.add_parser("ask", help="요청 파일을 쓰고 응답을 기다린다")
    common(p)
    p.add_argument("--site", default="", help="캡챠가 뜬 페이지 URL")
    p.add_argument("--question", default="", help="캡챠 질문 원문(모르면 비워둔다)")
    p.add_argument("--no-wait", action="store_true", help="요청만 쓰고 즉시 종료")
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("solve", help="(열기 →) capture → ask (→ submit) 한 번에")
    common(p, with_capture=True)
    p.add_argument("--url", help="캡챠가 뜨는 URL. 주면 Aside 앱 탭으로 먼저 연다")
    p.add_argument("--open-wait", type=float, default=4.0, help="탭이 뜰 때까지 대기(초)")
    p.add_argument("--site", default="", help="비우면 캡처한 탭의 URL 을 쓴다")
    p.add_argument("--question", default="", help="비우면 본문에서 추정")
    p.add_argument("--submit", action="store_true",
                   help="answered 면 답을 입력창에 넣고 제출까지 한다")
    p.set_defaults(func=cmd_solve)

    p = sub.add_parser("open", help="Aside 앱 탭으로 URL 열기(repl 탭은 곧 사라진다)")
    p.add_argument("--url", required=True)
    p.add_argument("--wait", type=float, default=4.0)
    p.set_defaults(func=cmd_open)

    p = sub.add_parser("submit", help="받은 답을 입력창에 넣고 제출")
    p.add_argument("--answer", required=True)
    p.add_argument("--match", default="", help="붙을 탭 URL 부분문자열. 기본 활성 탭")
    p.add_argument("--capture-timeout", type=float, default=90.0)
    p.set_defaults(func=cmd_submit)

    p = sub.add_parser("ping", help="Aside 감시 routine 생존 확인")
    common(p)
    p.set_defaults(func=cmd_ping)

    p = sub.add_parser("status", help="응답 안 온 요청 목록")
    p.set_defaults(func=cmd_status)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
