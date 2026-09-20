/* 진행 로그 SSE 브라우저 검증 — **탭을 진짜로 닫았다 다시 연다.**
 *
 * 무엇을 증명하는가 (성공기준 3 / SC-03):
 *   ① 작업 중간에 로그가 화면에 흐른다 (빈 화면이면 PYTHONUNBUFFERED 가 빠진 것 — Pitfall 1)
 *   ② 2초 상태 폴링이 돌아도 EventSource 가 **한 번만** 만들어진다
 *      (패널 전체를 폴링이 갈아끼우면 2초마다 새로 만들어진다 — 그러면 여기서 잡힌다)
 *   ③ 폴링이 몇 번 돌아도 로그에 **같은 줄이 두 번 안 찍힌다**
 *   ④ 탭을 닫고 몇 초 뒤 **새 탭**을 열면 로그가 1번 줄부터 다시 흐르고,
 *      닫혀 있던 동안 찍힌 줄까지 이어진다
 *   ⑤ 작업이 끝나면 done 이벤트로 EventSource 가 닫히고(readyState 2) 폴링도 멈춘다
 *
 * 판정 기준을 "줄이 보인다"·"숫자가 움직인다" 로 쓰지 않는다. 2026-09-20 의 건수 배지
 * 버그가 정확히 그 함정이었다(01-04). 여기서는 **줄 목록이 `[1/N] tick` 부터 빠짐없이
 * 연속인지**를 본다 — 누락도 중복도 한 줄이면 실패한다.
 *
 * 쓰는 법: webapp/tests/sse_cdp.sh 가 임시 서버·크롬·합성 잡을 띄우고 이걸 부른다.
 */

const [devport, base, token, jobId, linesArg] = process.argv.slice(2);
if (!devport || !base || !token || !jobId) {
  console.error("사용법: node sse_cdp.mjs <cdp포트> <서버주소> <토큰> <잡ID> [줄수]");
  process.exit(2);
}
const 총줄수 = Number(linesArg || 40);

const 잠깐 = (ms) => new Promise((r) => setTimeout(r, ms));

let 실패 = 0;
function check(id, 설명, ok, 자세히) {
  console.log(`${ok ? "PASS" : "FAIL"} ${id}  ${설명}${자세히 ? "  " + 자세히 : ""}`);
  if (!ok) { 실패 = 1; }
}

/* ── CDP 세션 하나 (탭 하나에 붙는다) ─────────────────────────────────────── */
function 세션(wsUrl) {
  const ws = new WebSocket(wsUrl);
  let seq = 0;
  const 대기중 = new Map();

  ws.addEventListener("message", (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && 대기중.has(msg.id)) {
      const { resolve, reject } = 대기중.get(msg.id);
      대기중.delete(msg.id);
      if (msg.error) { reject(new Error(JSON.stringify(msg.error))); }
      else { resolve(msg.result); }
    }
  });

  const 열림 = new Promise((res, rej) => {
    ws.addEventListener("open", res, { once: true });
    ws.addEventListener("error", rej, { once: true });
  });

  function send(method, params) {
    const id = ++seq;
    return new Promise((resolve, reject) => {
      대기중.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params: params || {} }));
    });
  }

  async function 평가(expr) {
    const r = await send("Runtime.evaluate", {
      expression: expr, returnByValue: true, awaitPromise: true,
    });
    if (r.exceptionDetails) {
      throw new Error("페이지 예외: " + JSON.stringify(r.exceptionDetails.exception));
    }
    return r.result.value;
  }

  return { ws, 열림, send, 평가, 닫기: () => ws.close() };
}

/* 새 문서마다 심는 계측기. EventSource 를 래핑해 **몇 번 만들어졌는지** 센다.
 * 이게 없으면 "폴링이 스트림을 2초마다 다시 연다" 를 눈으로는 절대 못 잡는다 —
 * 화면에는 같은 로그가 그대로 보이기 때문이다. */
const 계측기 = `
  (function () {
    window.__ct_es = { 만든횟수: 0, 마지막: null };
    var 원래 = window.EventSource;
    window.EventSource = function (url, opts) {
      var es = new 원래(url, opts);
      window.__ct_es.만든횟수 += 1;
      window.__ct_es.마지막 = es;
      return es;
    };
    window.EventSource.prototype = 원래.prototype;
    window.EventSource.CONNECTING = 0;
    window.EventSource.OPEN = 1;
    window.EventSource.CLOSED = 2;
  })();
`;

/* 페이지에서 읽어오는 값들. 정답은 브라우저가 아니라 **로그 줄의 모양**이 정한다. */
const 읽기 = `
  (function () {
    var pre = document.getElementById("job-log");
    var 줄 = pre ? pre.textContent.split("\\n").filter(function (l) { return l.trim(); }) : [];
    var 상태 = document.getElementById("job-status");
    return {
      줄: 줄,
      패널있나: !!document.querySelector("section#job-panel"),
      스트림주소: (document.querySelector("[sse-connect]") || {}).getAttribute
        ? document.querySelector("[sse-connect]").getAttribute("sse-connect") : null,
      폴링중: !!(상태 && 상태.getAttribute("hx-trigger")),
      상태글: 상태 ? 상태.textContent.replace(/\\s+/g, " ").trim().slice(0, 80) : "",
      끝났나: (document.getElementById("job-done") || {}).textContent || "",
      만든횟수: (window.__ct_es || {}).만든횟수,
      readyState: (window.__ct_es && window.__ct_es.마지막)
        ? window.__ct_es.마지막.readyState : -1
    };
  })();
`;

/** 줄 목록이 `[1/N] tick` 부터 빠짐없이 연속인지. 누락·중복이 한 줄이라도 있으면 false. */
function 연속인가(줄들) {
  const 틱 = 줄들.filter((l) => l.endsWith("tick"));
  for (let i = 0; i < 틱.length; i++) {
    if (틱[i] !== `[${i + 1}/${총줄수}] tick`) { return false; }
  }
  // 진행 줄 뒤에 붙는 것은 완료 줄뿐이다 (합성 잡이 마지막에 한 줄 찍는다)
  return 줄들.slice(0, 틱.length).every((l, i) => l === 틱[i]);
}

async function 새탭(url) {
  const r = await fetch(`http://127.0.0.1:${devport}/json/new?url=about:blank`, { method: "PUT" });
  const t = await r.json();
  const s = 세션(t.webSocketDebuggerUrl);
  await s.열림;
  await s.send("Page.enable");
  await s.send("Runtime.enable");
  await s.send("Page.addScriptToEvaluateOnNewDocument", { source: 계측기 });
  await s.send("Page.navigate", { url });
  return { 세션: s, id: t.id };
}

async function 탭닫기(id) {
  await fetch(`http://127.0.0.1:${devport}/json/close/${id}`);
}

async function main() {
  /* ── 1차 접속 ─────────────────────────────────────────────────────────── */
  const 첫탭 = await 새탭(`${base}/?t=${token}`);
  await 잠깐(5000);                       // 작업 시작 후 ~5초

  let a = await 첫탭.세션.평가(읽기);
  check("V-SSE-00", "새로고침만으로 도는 작업 패널이 뜬다", a.패널있나,
    `스트림 ${a.스트림주소}`);
  check("V-SSE-01", "5초 시점에 로그가 화면에 흐른다 (빈 화면이면 실패)",
    a.줄.length >= 5 && a.줄[0] === `[1/${총줄수}] tick`,
    `${a.줄.length}줄 · 첫 줄 "${a.줄[0] || "(없음)"}"`);
  check("V-SSE-02", "EventSource 가 정확히 1개 열렸다",
    a.만든횟수 === 1, `만든횟수 ${a.만든횟수}`);

  await 잠깐(4500);                       // 2초 폴링이 두 번 이상 돈 뒤
  const b = await 첫탭.세션.평가(읽기);
  check("V-SSE-03", "2초 폴링이 몇 번 돌아도 스트림은 그대로 1개다",
    b.만든횟수 === 1, `만든횟수 ${b.만든횟수} · 폴링중 ${b.폴링중}`);
  check("V-SSE-04", "폴링이 돌아도 같은 줄이 두 번 안 찍힌다",
    연속인가(b.줄) && b.줄.length > a.줄.length,
    `${a.줄.length}줄 → ${b.줄.length}줄`);

  const 닫기전 = b.줄.length;

  /* ── 탭을 진짜로 닫는다 ──────────────────────────────────────────────── */
  첫탭.세션.닫기();
  await 탭닫기(첫탭.id);
  await 잠깐(5000);                       // 탭이 없는 동안에도 자식은 계속 찍는다

  /* ── 다시 연다 ───────────────────────────────────────────────────────── */
  const 둘째탭 = await 새탭(`${base}/?t=${token}`);
  await 잠깐(3000);
  const c = await 둘째탭.세션.평가(읽기);

  check("V-SSE-05", "탭을 닫았다 열면 로그가 **1번 줄부터** 다시 흐른다",
    c.줄[0] === `[1/${총줄수}] tick`, `첫 줄 "${c.줄[0] || "(없음)"}"`);
  check("V-SSE-06", "닫혀 있던 동안 찍힌 줄까지 이어진다",
    c.줄.length > 닫기전, `닫기 전 ${닫기전}줄 → 다시 연 뒤 ${c.줄.length}줄`);
  check("V-SSE-07", "재접속 로그에 누락도 중복도 없다",
    연속인가(c.줄), `${c.줄.length}줄`);

  /* ── 끝나면 스스로 닫힌다 ───────────────────────────────────────────── */
  const 한계 = Date.now() + 25000;
  let d = c;
  while (Date.now() < 한계) {
    await 잠깐(1000);
    d = await 둘째탭.세션.평가(읽기);
    if (!d.폴링중 && d.readyState === 2) { break; }
  }
  check("V-SSE-08", "작업이 끝나면 done 으로 EventSource 가 닫힌다 (readyState 2)",
    d.readyState === 2, `readyState ${d.readyState}`);
  check("V-SSE-09", "작업이 끝나면 2초 폴링도 멈춘다", d.폴링중 === false,
    `상태 "${d.상태글}"`);
  check("V-SSE-10", "끝난 뒤 로그 전량이 남아 있다 (마지막 줄까지)",
    d.줄.includes(`[${총줄수}/${총줄수}] tick`) && 연속인가(d.줄),
    `${d.줄.length}줄`);
  check("V-SSE-11", "done 요약이 화면에 붙었다", d.끝났나.trim().length > 0,
    `"${d.끝났나.replace(/\s+/g, " ").trim().slice(0, 60)}"`);

  둘째탭.세션.닫기();
  await 탭닫기(둘째탭.id);

  console.log("----");
  console.log(실패 ? "FAIL 이 있다 — 여기서 멈춰라" : "SSE CDP 검증 전량 PASS");
  process.exit(실패);
}

main().catch((e) => {
  console.error("검증 중 터졌다:", e && e.message ? e.message : e);
  process.exit(1);
});
