/* 보드 건수 배지 회귀 검증 — 진짜 브라우저 안에서 확인한다.
 *
 * 왜 pytest 가 아니라 여기인가:
 *   배지 갱신은 Tabulator 의 이벤트 순서에 달린 **브라우저 JS 동작**이다.
 *   TestClient 는 ASGI 앱을 부를 뿐이라 JS 를 한 줄도 실행하지 않는다.
 *   pytest 안에서 이걸 흉내 내면 "우리가 짠 가짜 Tabulator" 를 검증하게 되는데,
 *   그건 진짜 버그를 하나도 못 잡으면서 초록색만 주는 테스트다.
 *   그래서 security_curl.sh 와 **같은 계층**에 둔다 — 살아 있는 서버에 실제로 쏘는
 *   통합 검증. 자동 스위트에는 안 들어가고, 보드 JS 를 건드리면 손으로 돌린다.
 *
 * 무엇을 잡는가 (2026-09-20 실제로 났던 버그):
 *   `dataFiltered` 핸들러 안에서 `table.getDataCount("active")` 를 읽으면 배지가
 *   정확히 **한 스텝 뒤처진다**. Tabulator 의 Filter.filter() 가 결과를 만든 뒤
 *   먼저 이벤트를 쏘고, 그 다음에 RowManager 가 activeRows 를 갈아끼우기 때문이다.
 *   필터를 바꾸면 숫자가 *움직이긴 해서* 육안으론 절대 안 잡힌다.
 *   **두 번 연속 바꿔 직전 값과 대조해야만** 드러난다 — 그걸 기계로 한다.
 *
 * 정답은 Tabulator 에게 묻지 않는다. 페이지에 박힌 원본 JSON 에서 직접 세서
 * 배지와 대조한다 — 검증 대상의 내부 상태를 정답으로 쓰면 같이 틀린다.
 *
 * 쓰는 법: webapp/tests/board_cdp.sh 가 크롬을 띄우고 이걸 부른다.
 */

const wsUrl = process.argv[2];
if (!wsUrl) {
  console.error("사용법: node board_cdp.mjs <webSocketDebuggerUrl>");
  process.exit(2);
}

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

function send(method, params) {
  const id = ++seq;
  return new Promise((resolve, reject) => {
    대기중.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params: params || {} }));
  });
}

/** 페이지 안에서 식을 평가하고 값을 돌려받는다. */
async function 평가(expr) {
  const r = await send("Runtime.evaluate", {
    expression: expr, returnByValue: true, awaitPromise: true,
  });
  if (r.exceptionDetails) {
    throw new Error("페이지 예외: " + JSON.stringify(r.exceptionDetails.exception));
  }
  return r.result.value;
}

const 잠깐 = (ms) => new Promise((r) => setTimeout(r, ms));

let 실패 = 0;
function check(id, 설명, ok, 자세히) {
  console.log(`${ok ? "PASS" : "FAIL"} ${id}  ${설명}${자세히 ? "  " + 자세히 : ""}`);
  if (!ok) { 실패 = 1; }
}

/* 페이지 안에서 돌릴 헬퍼. 배지를 읽고, 원본 JSON 에서 정답을 직접 센다. */
const HELPERS = `
window.__ct = {
  배지: function () {
    var el = document.getElementById("board-count");
    return el ? Number((el.textContent || "").replace(/[^0-9]/g, "")) : -1;
  },
  원본: function () {
    return JSON.parse(document.getElementById("board-rows").textContent || "[]");
  },
  계정옵션: function () {
    return Array.prototype.map.call(document.getElementById("f-acct").options,
      function (o) { return o.value; });
  },
  규칙옵션: function () {
    return Array.prototype.map.call(document.getElementById("f-rule").options,
      function (o) { return o.value; });
  },
  고르기: function (id, values) {
    var sel = document.getElementById(id);
    Array.prototype.forEach.call(sel.options, function (o) {
      o.selected = values.indexOf(o.value) !== -1;
    });
    sel.dispatchEvent(new Event("change", { bubbles: true }));
  },
  검색: function (q) {
    var el = document.getElementById("f-title");
    el.value = q;
    el.dispatchEvent(new Event("input", { bubbles: true }));
  },
  초기화: function () {
    document.getElementById("f-reset").click();
  },
  // Tabulator 내부 집계(참고용). 정답으로 쓰지 않는다.
  내부: function () {
    try { return Tabulator.findTable("#board")[0].getDataCount("active"); }
    catch (e) { return -1; }
  },
  렌더된셀: function () {
    return Array.prototype.map.call(
      document.querySelectorAll(".tabulator-cell"),
      function (c) { return c.textContent; });
  }
};
true;
`;

async function main() {
  await new Promise((res, rej) => {
    ws.addEventListener("open", res, { once: true });
    ws.addEventListener("error", rej, { once: true });
  });
  await send("Runtime.enable");

  // Tabulator 가 표를 다 그릴 때까지 기다린다 (최대 20초)
  let 준비 = false;
  for (let i = 0; i < 100; i++) {
    const n = await 평가(`document.querySelectorAll(".tabulator-row").length`);
    if (n > 0) { 준비 = true; break; }
    await 잠깐(200);
  }
  check("V-BOARD-00", "Tabulator 가 실제로 표를 그렸다", 준비);
  if (!준비) { return; }

  await 평가(HELPERS);

  const 원본 = await 평가(`window.__ct.원본()`);
  const 계정들 = await 평가(`window.__ct.계정옵션()`);
  const 규칙들 = await 평가(`window.__ct.규칙옵션()`);

  // ── 초기 상태 ────────────────────────────────────────────────────────────
  {
    const 배지 = await 평가(`window.__ct.배지()`);
    check("V-BOARD-01", "초기 배지 = 전체 행 수",
      배지 === 원본.length, `배지 ${배지} / 실제 ${원본.length}`);
  }

  // ── 핵심: 계정 필터를 **연속으로** 바꾸며 매번 대조한다 ────────────────────
  // 한 번만 바꿔서는 한 스텝 랙이 안 보인다. 직전 값과 다른 값이 연달아 나와야
  // "직전 것을 보여주고 있다" 가 드러난다.
  console.log("---- 계정 필터 연속 전환 (한 스텝 랙 탐지) ----");
  let 직전 = null;
  for (const a of 계정들) {
    await 평가(`window.__ct.고르기("f-acct", ${JSON.stringify([a])})`);
    await 잠깐(600);
    const 배지 = await 평가(`window.__ct.배지()`);
    const 내부 = await 평가(`window.__ct.내부()`);
    const 정답 = 원본.filter((r) => r.acct === a).length;
    const 랙 = 직전 !== null && 배지 === 직전 && 배지 !== 정답;
    console.log(`  ${a.padEnd(10)} 정답 ${String(정답).padStart(5)} | 배지 ${String(배지).padStart(5)} | 내부 ${String(내부).padStart(5)}${랙 ? "   ← 직전 값이다" : ""}`);
    check("V-BOARD-02", `계정 ${a} 배지 = 정답`, 배지 === 정답,
      `배지 ${배지} / 정답 ${정답}`);
    직전 = 정답;
  }

  // ── 규칙 필터도 같은 증상이었다 ───────────────────────────────────────────
  console.log("---- 규칙 필터 연속 전환 ----");
  await 평가(`window.__ct.초기화()`);
  await 잠깐(500);
  for (const 기호 of 규칙들) {
    await 평가(`window.__ct.고르기("f-rule", ${JSON.stringify([기호])})`);
    await 잠깐(500);
    const 배지 = await 평가(`window.__ct.배지()`);
    const 정답 = 원본.filter((r) => (r.rules || "").indexOf(기호) !== -1).length;
    console.log(`  ${기호} 정답 ${String(정답).padStart(5)} | 배지 ${String(배지).padStart(5)}`);
    check("V-BOARD-03", `규칙 ${기호} 배지 = 정답`, 배지 === 정답,
      `배지 ${배지} / 정답 ${정답}`);
  }

  // ── 상품명 검색 ──────────────────────────────────────────────────────────
  console.log("---- 상품명 검색 ----");
  await 평가(`window.__ct.초기화()`);
  await 잠깐(500);
  for (const q of ["카트", "전정기", "ZZ존재하지않는단어ZZ"]) {
    await 평가(`window.__ct.검색(${JSON.stringify(q)})`);
    await 잠깐(500);
    const 배지 = await 평가(`window.__ct.배지()`);
    const 말 = q.toLowerCase();
    const 정답 = 원본.filter((r) => (r.title || "").toLowerCase().indexOf(말) !== -1).length;
    console.log(`  "${q}" 정답 ${String(정답).padStart(5)} | 배지 ${String(배지).padStart(5)}`);
    check("V-BOARD-04", `검색 "${q}" 배지 = 정답`, 배지 === 정답,
      `배지 ${배지} / 정답 ${정답}`);
  }

  // ── 초기화 버튼 ──────────────────────────────────────────────────────────
  await 평가(`window.__ct.초기화()`);
  await 잠깐(600);
  {
    const 배지 = await 평가(`window.__ct.배지()`);
    check("V-BOARD-05", "초기화하면 배지가 전체로 돌아온다",
      배지 === 원본.length, `배지 ${배지} / 전체 ${원본.length}`);
  }

  // ── 렌더된 셀에 undefined/NaN 0건 ────────────────────────────────────────
  {
    const 셀 = await 평가(`window.__ct.렌더된셀()`);
    const 나쁨 = 셀.filter((t) => /undefined|NaN|\[object/.test(t));
    check("V-BOARD-06", `렌더된 셀 ${셀.length}개에 undefined/NaN 0건`,
      나쁨.length === 0, 나쁨.slice(0, 3).join(","));
  }

  // ── 레이아웃: 가로 스크롤이 없다 ─────────────────────────────────────────
  {
    const 폭 = await 평가(`(function(){
      var h = document.querySelector(".tabulator-tableholder");
      var t = document.querySelector(".tabulator-table");
      return { holder: h ? h.clientWidth : -1, table: t ? t.scrollWidth : -1 };
    })()`);
    check("V-BOARD-07", "표가 컨테이너 안에 들어온다 (가로 스크롤 없음)",
      폭.table <= 폭.holder + 2, `표 ${폭.table} / 컨테이너 ${폭.holder}`);
  }

  // ── 상품명 툴팁이 달려 있다 (잘린 상품명을 hover 로 읽는다) ──────────────
  {
    const 툴팁 = await 평가(`(function(){
      var t = Tabulator.findTable("#board")[0];
      var c = t.getColumn("title");
      return !!(c && c.getDefinition().tooltip);
    })()`);
    check("V-BOARD-08", "상품명 열에 툴팁이 있다 (잘려도 전문을 읽는다)", 툴팁 === true);
  }
}

main()
  .then(() => {
    console.log("----");
    console.log(실패 === 0 ? "보드 CDP 검증 전량 PASS" : "FAIL 이 있다 — 여기서 멈춰라");
    ws.close();
    process.exit(실패);
  })
  .catch((e) => {
    console.error("검증 중 오류:", e.message);
    ws.close();
    process.exit(2);
  });
