/* 선택 → 미리보기 브라우저 검증 — 진짜 크롬 안에서 페이지를 **조작해서** 확인한다.
 *
 * 왜 pytest 가 아니라 여기인가:
 *   Tabulator 의 행 선택은 브라우저 JS 안에서만 산다. TestClient 는 ASGI 앱을 부를 뿐
 *   JS 를 한 줄도 실행하지 않아, "헤더 체크박스가 무엇을 고르는가" 를 볼 방법이 없다.
 *   그런데 거기에 **화면 증상이 전혀 없는** 사고가 있다:
 *     `titleFormatterParams.rowRange` 를 안 주면 Tabulator 는
 *     `selectRows(undefined)` → `rowManager.rows`, 즉 **필터를 무시한 전체 행**을 고른다.
 *     화면엔 걸러진 행만 보이는데 선택은 전체다. 계정 하나로 좁혀 놓고 헤더를 누르면
 *     다른 계정 소재까지 입찰가가 오른다. 육안으로는 영원히 안 잡힌다.
 *
 * 판정 기준을 "표가 뜬다"·"숫자가 움직인다" 로 쓰지 않는다(01-04·01-06 의 교훈).
 * 정답은 페이지에 박힌 원본 JSON 에서 **직접 세서** 대조하고, 가격은 **정확히 몇에서
 * 몇으로** 를 본다.
 *
 * 실제로 미리보기를 접수한다 — dry-run 이라 광고 API 호출 0 · 크레딧 0 · 광고비 0.
 *
 * 쓰는 법: webapp/tests/preview_cdp.sh 가 크롬을 띄우고 이걸 부른다.
 */

const [wsUrl, base, runDir, targetAd] = process.argv.slice(2);
if (!wsUrl || !base || !runDir || !targetAd) {
  console.error("사용법: node preview_cdp.mjs <webSocketDebuggerUrl> <서버주소> <회차> <기준소재>");
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

/* 새 문서마다 심는 계측기. EventSource 를 래핑해 **몇 개가 열려 있는지** 센다.
 * 미리보기를 두 번 누르면 작업 패널이 통째로 갈리는데, 그때 옛 커넥션이 안 닫히면
 * 화면에는 아무 증상이 없고 커넥션만 쌓인다(T-1-24). 그건 세는 수밖에 없다. */
const 계측기 = `
  (function () {
    window.__ct_es = { 만든횟수: 0, 목록: [] };
    var 원래 = window.EventSource;
    window.EventSource = function (url, opts) {
      var es = new 원래(url, opts);
      window.__ct_es.만든횟수 += 1;
      window.__ct_es.목록.push(es);
      return es;
    };
    window.EventSource.prototype = 원래.prototype;
    window.EventSource.CONNECTING = 0;
    window.EventSource.OPEN = 1;
    window.EventSource.CLOSED = 2;
  })();
`;

/* 페이지 안에서 돌릴 헬퍼. 정답은 Tabulator 가 아니라 **원본 JSON** 에서 센다 —
 * 검증 대상의 내부 상태를 정답으로 쓰면 같이 틀린다. */
const HELPERS = `
window.__ct = {
  표: function () { return Tabulator.findTable("#board")[0]; },
  원본: function () {
    return JSON.parse(document.getElementById("board-rows").textContent || "[]");
  },
  계정옵션: function () {
    return Array.prototype.map.call(document.getElementById("f-acct").options,
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
  초기화: function () { document.getElementById("f-reset").click(); },

  선택: function () { return window.__ct.표().getSelectedData(); },
  선택수: function () { return window.__ct.선택().length; },
  선택계정: function () {
    var s = {}; window.__ct.선택().forEach(function (r) { s[r.acct] = 1; });
    return Object.keys(s).sort();
  },
  선택대상수: function () {
    var n = 0; window.__ct.선택().forEach(function (r) { n += (r.rule1_count || 0); });
    return n;
  },
  활성수: function () { return window.__ct.표().getData("active").length; },
  보이는수: function () { return window.__ct.표().getRows("visible").length; },
  요약: function () { return (document.getElementById("sel-summary").textContent || "").trim(); },
  전체링크보임: function () { return !document.getElementById("sel-all-wrap").hidden; },
  전체링크N: function () {
    return Number((document.getElementById("sel-all-n").textContent || "").replace(/[^0-9]/g, ""));
  },
  전체링크클릭: function () { document.getElementById("sel-all").click(); },
  배너보임: function () { return !document.getElementById("sel-banner").hidden; },
  배너말: function () { return (document.getElementById("sel-banner-msg").textContent || "").trim(); },
  배너취소: function () { document.getElementById("sel-banner-cancel").click(); },
  배너확인: function () { document.getElementById("sel-banner-ok").click(); },
  헤더체크: function () {
    var el = document.querySelector(".tabulator-header input[type=checkbox]");
    if (!el) { return false; }
    el.click();
    return true;
  },
  버튼막힘: function () { return document.getElementById("preview-btn").disabled; },
  미리보기클릭: function () { document.getElementById("preview-btn").click(); },
  미리보기보임: function () { return !document.getElementById("preview").hidden; },
  미리보기글: function () {
    return (document.getElementById("preview-body").textContent || "").replace(/\\s+/g, " ").trim();
  },
  미리보기줄수: function () {
    return document.querySelectorAll("#preview-body tbody tr").length;
  },
  미리보기행: function (adId) {
    var tr = Array.prototype.filter.call(
      document.querySelectorAll("#preview-body tbody tr"),
      function (r) { return (r.textContent || "").indexOf(adId) !== -1; });
    if (!tr.length) { return null; }
    return Array.prototype.map.call(tr[0].cells, function (c) {
      return (c.textContent || "").trim();
    });
  },
  오류: function () {
    var el = document.getElementById("job-error");
    return el.hidden ? "" : (el.textContent || "").trim();
  },
  타이핑칸: function () {
    // 건수를 타이핑해 확인받는 입력칸이 없어야 한다 (FLOW-04). 상품명 검색은 제외.
    return Array.prototype.filter.call(document.querySelectorAll("input"), function (i) {
      return ["checkbox", "hidden", "radio", "search"].indexOf(i.type) === -1
        && i.id !== "f-title";
    }).length;
  },
  스트림수: function () {
    return { 만든횟수: window.__ct_es.만든횟수,
             열린것: window.__ct_es.목록.filter(function (e) { return e.readyState !== 2; }).length };
  },
  // 화면을 거치지 않고 서버로 직접 쏜다 — 오염된 대상의 **에러 경로** 확인용.
  직접쏘기: function (ids) {
    var 토큰 = JSON.parse(document.body.getAttribute("hx-headers"))["X-CT-Token"];
    return fetch("/jobs/bids/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CT-Token": 토큰 },
      body: JSON.stringify({ run_dir: document.getElementById("job-run-dir").value, ad_ids: ids })
    }).then(function (r) {
      return r.text().then(function (t) { return { code: r.status, 본문: t }; });
    });
  }
};
true;
`;

/** 미리보기 표가 그려질 때까지 기다린다. */
async function 표기다리기(초 = 60) {
  for (let i = 0; i < 초 * 5; i++) {
    const 글 = await 평가(`window.__ct.미리보기글()`);
    if (글 && !/만드는 중/.test(글)) { return 글; }
    await 잠깐(200);
  }
  return null;
}

async function main() {
  await new Promise((res, rej) => {
    ws.addEventListener("open", res, { once: true });
    ws.addEventListener("error", rej, { once: true });
  });
  await send("Runtime.enable");
  await send("Page.enable");
  // 계측기를 심고 **다시 연다** — 페이지가 이미 떠 있으면 EventSource 를 못 센다.
  await send("Page.addScriptToEvaluateOnNewDocument", { source: 계측기 });
  await send("Page.navigate", { url: `${base}/?run_dir=${encodeURIComponent(runDir)}` });

  let 준비 = false;
  for (let i = 0; i < 150; i++) {
    await 잠깐(200);
    try {
      const n = await 평가(`document.querySelectorAll(".tabulator-row").length`);
      if (n > 0) { 준비 = true; break; }
    } catch (e) { /* 이동 중 */ }
  }
  check("V-PRE-00", "Tabulator 가 표를 그렸다", 준비);
  if (!준비) { return; }

  await 평가(HELPERS);
  const 원본 = await 평가(`window.__ct.원본()`);
  const 계정들 = await 평가(`window.__ct.계정옵션()`);

  // 기준 소재가 든 상품 줄을 원본에서 찾는다. 정답의 출처는 서버가 넘긴 데이터다.
  const 기준행 = 원본.find((r) => (r.rule1_ads || []).indexOf(targetAd) !== -1);
  if (!기준행) {
    check("V-PRE-00b", `기준 소재 ${targetAd} 가 이 회차 보드에 없다`, false,
      `회차 ${runDir} · 행 ${원본.length}`);
    return;
  }

  // ── 초기 상태 ────────────────────────────────────────────────────────────
  {
    const 막힘 = await 평가(`window.__ct.버튼막힘()`);
    const 요약 = await 평가(`window.__ct.요약()`);
    check("V-PRE-01", "고른 게 없으면 버튼이 막히고 이유를 말한다",
      막힘 === true && /0개 선택/.test(요약) && /먼저 상품을 골라라/.test(요약), 요약);
  }

  // ── 건수 타이핑 입력칸 없음 (FLOW-04 / D-07) ─────────────────────────────
  {
    const n = await 평가(`window.__ct.타이핑칸()`);
    check("V-PRE-02", "건수를 타이핑해 확인받는 입력칸이 0개다 (되돌릴 수 있는 작업)",
      n === 0, `입력칸 ${n}개`);
  }

  // ── 핵심: 헤더 체크박스가 필터 밖 행을 고르지 않는다 ─────────────────────
  // 이게 이 하네스의 존재 이유다. rowRange 를 빼면 여기서만 잡힌다.
  {
    const 계정 = 계정들.find((a) => 원본.filter((r) => r.acct === a).length > 50) || 계정들[0];
    await 평가(`window.__ct.고르기("f-acct", ${JSON.stringify([계정])})`);
    await 잠깐(700);
    const 활성 = await 평가(`window.__ct.활성수()`);
    const 보이는 = await 평가(`window.__ct.보이는수()`);
    const 눌림 = await 평가(`window.__ct.헤더체크()`);
    await 잠깐(700);
    const 선택수 = await 평가(`window.__ct.선택수()`);
    const 선택계정 = await 평가(`window.__ct.선택계정()`);
    const 정답활성 = 원본.filter((r) => r.acct === 계정).length;

    check("V-PRE-03a", "헤더 체크박스가 있다", 눌림 === true);
    check("V-PRE-03b", `헤더 선택은 **그 계정만** 고른다 (${계정})`,
      선택계정.length === 1 && 선택계정[0] === 계정,
      `고른 계정 [${선택계정.join(",")}] · 고른 줄 ${선택수}`);
    check("V-PRE-03c", "헤더 선택 수 = 뷰포트에 그려진 줄 수 (전체가 아니다)",
      선택수 === 보이는, `선택 ${선택수} / 보이는 ${보이는} / 전체 ${원본.length}`);
    check("V-PRE-03d", "'보이는 것' 과 '필터 전체' 가 **다른 수**다 (BOARD-03)",
      선택수 < 활성 && 활성 === 정답활성,
      `선택 ${선택수} < 필터전체 ${활성} (정답 ${정답활성})`);

    const 요약 = await 평가(`window.__ct.요약()`);
    const 정답대상 = 원본.filter((r) => r.acct === 계정).length;   // 참고용
    const 선택대상 = await 평가(`window.__ct.선택대상수()`);
    check("V-PRE-04", "요약 줄이 상품 수와 대상 ①소재 수를 갈라 말한다",
      요약.indexOf(선택수.toLocaleString("ko-KR")) !== -1
      && 요약.indexOf("대상 " + 선택대상.toLocaleString("ko-KR") + "건") !== -1,
      `${요약}  (정답활성 ${정답대상})`);

    // ── 필터 전체 선택 링크 ────────────────────────────────────────────────
    const 링크보임 = await 평가(`window.__ct.전체링크보임()`);
    const 링크N = await 평가(`window.__ct.전체링크N()`);
    check("V-PRE-05", "'필터 전체 N건 선택' 의 N 이 필터 통과 수와 정확히 같다",
      링크보임 === true && 링크N === 정답활성, `링크 N=${링크N} / 정답 ${정답활성}`);

    // ── 배너: 취소하면 선택이 안 넘어간다 (FLOW-04 / D-07) ─────────────────
    await 평가(`window.__ct.전체링크클릭()`);
    await 잠깐(300);
    const 배너떴나 = await 평가(`window.__ct.배너보임()`);
    const 배너말 = await 평가(`window.__ct.배너말()`);
    check("V-PRE-06a", "전체 선택은 배너로 한 번 더 확인한다",
      배너떴나 === true && /진행할래/.test(배너말), 배너말);

    await 평가(`window.__ct.배너취소()`);
    await 잠깐(300);
    const 취소후 = await 평가(`window.__ct.선택수()`);
    const 배너닫혔나 = await 평가(`window.__ct.배너보임()`);
    check("V-PRE-06b", "취소하면 선택이 **그대로** 다 (한 줄도 안 넘어간다)",
      취소후 === 선택수 && 배너닫혔나 === false,
      `취소 전 ${선택수} → 취소 후 ${취소후}`);

    await 평가(`window.__ct.전체링크클릭()`);
    await 잠깐(300);
    await 평가(`window.__ct.배너확인()`);
    await 잠깐(1200);
    const 확인후 = await 평가(`window.__ct.선택수()`);
    check("V-PRE-06c", "확인하면 필터 전체가 선택된다",
      확인후 === 정답활성, `선택 ${확인후} / 정답 ${정답활성}`);

    // ── 선택을 남겨 둔 채 필터를 바꾸면 그 사실을 말한다 ────────────────────
    const 다른계정 = 계정들.find((a) => a !== 계정);
    if (다른계정) {
      await 평가(`window.__ct.고르기("f-acct", ${JSON.stringify([다른계정])})`);
      await 잠깐(800);
      const 요약2 = await 평가(`window.__ct.요약()`);
      check("V-PRE-07", "선택을 남긴 채 필터를 바꾸면 '필터 밖' 건수를 말한다",
        /필터 밖/.test(요약2), 요약2.slice(0, 120));
    }
    await 평가(`window.__ct.초기화()`);
    await 잠깐(600);
    // 필터 초기화는 선택을 지우지 않는다 — 다음 단계를 위해 직접 비운다.
    await 평가(`window.__ct.표().deselectRow()`);
    await 잠깐(400);
  }

  // ── 실제 미리보기 (BID-03) ───────────────────────────────────────────────
  // 기준 소재가 든 상품만 남기고, 그 상품을 골라 접수한다.
  let 첫결과 = null;
  {
    const 검색어 = (기준행.title || "").slice(0, 12);
    await 평가(`window.__ct.검색(${JSON.stringify(검색어)})`);
    await 잠깐(800);
    await 평가(`window.__ct.전체링크클릭()`);
    await 잠깐(300);
    await 평가(`window.__ct.배너확인()`);
    await 잠깐(800);

    const 고른수 = await 평가(`window.__ct.선택수()`);
    const 막힘 = await 평가(`window.__ct.버튼막힘()`);
    check("V-PRE-08", "상품을 고르면 버튼이 열린다",
      고른수 > 0 && 막힘 === false, `선택 ${고른수}`);

    await 평가(`window.__ct.미리보기클릭()`);
    const 글 = await 표기다리기(90);
    check("V-PRE-09", "미리보기 표가 뜬다", 글 !== null,
      글 ? 글.slice(0, 90) : "(시간 초과)");
    if (글 === null) { return; }
    첫결과 = 글;

    const 보임 = await 평가(`window.__ct.미리보기보임()`);
    check("V-PRE-10", "미리보기 자리가 열린다", 보임 === true);

    // **이게 BID-03 의 핵심이다.** 소재 줄의 현재가가 그룹 기본가에서 출발해야 한다.
    const 행 = await 평가(`window.__ct.미리보기행(${JSON.stringify(targetAd)})`);
    if (!행) {
      check("V-PRE-11", `기준 소재 줄이 표에 있다 (${targetAd})`, false, 글.slice(0, 150));
    } else {
      // 컬럼: 계정 · 상품명 · 소재ID · 판정 · 현재가 · → · 인상 후 · 그룹입찰따름
      const [계정칸, , , 판정, 현재가, , 인상후, 그룹] = 행;
      const 보드입찰 = String(기준행.bid);
      check("V-PRE-11", "기준 소재 줄이 표에 있다", true, 행.join(" | "));
      check("V-PRE-12a", `현재가가 보드의 현재입찰과 **같다** (그룹 기본가 ${보드입찰})`,
        현재가 === 보드입찰, `표 ${현재가} / 보드 ${보드입찰}`);
      check("V-PRE-12b", "인상 후 = 현재가 + 10 (CLI 가 계산한 값이다)",
        Number(인상후) === Number(현재가) + 10, `${현재가} → ${인상후}`);
      check("V-PRE-12c", "그룹입찰따름이 예/아니오 로 나온다 (1/0 이 아니다)",
        그룹 === "예" || 그룹 === "아니오", `"${그룹}"`);
      check("V-PRE-12d", "판정이 5종 중 하나다",
        ["인상", "최근인상", "연속실패중단", "상한도달", "입찰가불명"].indexOf(판정) !== -1,
        판정);
      check("V-PRE-12e", "계정이 보드 줄의 계정과 같다",
        계정칸 === 기준행.acct, `${계정칸} / ${기준행.acct}`);
    }

    // 집계 줄은 **항상** 있다 (Pitfall 6 — 인상 0건이어도)
    const 줄수 = await 평가(`window.__ct.미리보기줄수()`);
    check("V-PRE-13", "집계 줄에 대상 건수와 예상 인상액 합계가 같이 있다",
      /대상 \d+건/.test(글) && /예상 인상액 합계/.test(글), `표 ${줄수}줄 · ${글.slice(0, 100)}`);

    const 스트림 = await 평가(`window.__ct.스트림수()`);
    check("V-PRE-14", "진행 로그 스트림이 1개만 열렸다",
      스트림.만든횟수 === 1 && 스트림.열린것 <= 1,
      `만든횟수 ${스트림.만든횟수} · 열린것 ${스트림.열린것}`);
  }

  // ── 같은 선택으로 한 번 더: dry-run 은 이력을 오염시키지 않는다 ──────────
  {
    await 평가(`window.__ct.미리보기클릭()`);
    await 잠깐(1500);
    const 글 = await 표기다리기(90);
    check("V-PRE-15", "같은 선택으로 두 번 눌러도 결과가 같다 (dry-run 은 이력을 안 건드린다)",
      글 !== null && 글 === 첫결과,
      글 === 첫결과 ? "동일" : `1차: ${(첫결과 || "").slice(0, 70)} / 2차: ${(글 || "").slice(0, 70)}`);

    const 스트림 = await 평가(`window.__ct.스트림수()`);
    check("V-PRE-16", "두 번째 접수에도 커넥션이 쌓이지 않는다 (열린 것 1개 이하)",
      스트림.열린것 <= 1, `만든횟수 ${스트림.만든횟수} · 열린것 ${스트림.열린것}`);
  }

  // ── 에러 경로: 오염된 대상은 조용히 버려지지 않는다 (T-1-30) ─────────────
  // 성공 경로만 보면 "버리는 구현" 과 "거부하는 구현" 이 똑같이 초록으로 보인다.
  {
    const 가짜 = "nad-a001-02-000000000000000";   // 모양은 맞지만 ①소재가 아니다
    const 응답 = await 평가(`window.__ct.직접쏘기(${JSON.stringify([가짜])})`);
    check("V-PRE-17a", "규칙① 소재가 아닌 대상은 400 으로 거부된다",
      응답.code === 400, `코드 ${응답.code}`);
    check("V-PRE-17b", "거부 사유에 '규칙①' 이 실린다 (조용히 버리지 않는다)",
      /규칙①/.test(응답.본문), 응답.본문.slice(0, 140));

    // 섞어 보내도 **전부** 거부다 — 일부만 처리하면 화면의 N 과 실제가 갈라진다
    const 섞음 = await 평가(`window.__ct.직접쏘기(${JSON.stringify([targetAd, 가짜])})`);
    check("V-PRE-17c", "정상 대상에 하나만 섞여도 전부 거부한다",
      섞음.code === 400, `코드 ${섞음.code}`);

    // 모양이 틀린 adId 는 모델에서 막힌다 (ASVS V5 / T-1-31)
    const 주입 = await 평가(`window.__ct.직접쏘기(${JSON.stringify(["; rm -rf ~"])})`);
    check("V-PRE-17d", "adId 모양이 아니면 422 (명령 주입 시도가 argv 근처도 못 간다)",
      주입.code === 422, `코드 ${주입.code}`);

    // 화면 쪽 오류 표시도 살아 있는지 — 버튼 경로로 한 번 확인한다.
    const 오류 = await 평가(`window.__ct.오류()`);
    check("V-PRE-18", "직접 쏜 요청은 화면 오류칸을 건드리지 않는다 (버튼 경로만 쓴다)",
      오류 === "", 오류);
  }
}

main()
  .then(() => {
    console.log("----");
    console.log(실패 === 0 ? "미리보기 CDP 검증 전량 PASS" : "FAIL 이 있다 — 여기서 멈춰라");
    ws.close();
    process.exit(실패);
  })
  .catch((e) => {
    console.error("검증 중 오류:", e.message);
    ws.close();
    process.exit(2);
  });
