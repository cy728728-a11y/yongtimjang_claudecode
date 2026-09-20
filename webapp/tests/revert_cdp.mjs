/* 되돌리기 버튼(BID-04 / D-14 / T-1-43) 브라우저 검증 — 진짜 크롬에서 배선과 배치를 본다.
 *
 * **되돌리기 요청이 서버에 한 건도 안 나간다.** 확인하려는 것이 "무엇이 나가는가" 라서
 * 진짜로 보낼 수는 없다 — 보내면 실제 광고 입찰가가 내려간다. 그래서:
 *
 *   ① 페이지 안에서 `window.fetch` 를 가로챈다 (board.js 는 fetch 를 쓴다. htmx 는 XHR 이라 무관)
 *   ② **프로브 한 번으로 가로채기가 실제로 걸렸는지 확인한다** — 이게 안전의 전부다.
 *      프로브가 안 잡히면 거기서 멈추고 버튼을 누르지 않는다
 *   ③ 그때만 버튼을 누르고, 가로챈 요청 본문을 검사한다
 *   ④ 마지막에 `GET /jobs` 를 다시 읽어 `revert_*` 잡이 **0건**인지 사후 확인한다
 *
 * 왜 pytest 가 아닌가:
 *   서버는 "두 버튼이 다른 조각에서 온다" 까지만 보장한다(test_revert.py). 화면에서
 *   **실제로 몇 픽셀 떨어져 있는지**, 위험 구역이 접혀 있는지, 취소가 정말 아무것도 안
 *   보내는지는 진짜 렌더링에만 있다. 이 화면의 최대 위험이 오클릭이다 (T-1-43).
 *
 * 판정 기준을 "버튼이 보인다" 로 쓰지 않는다(01-04·01-06·01-07 의 교훈).
 * 건수는 **서버에서 직접 받아** 화면과 대조한다.
 *
 * 쓰는 법: webapp/tests/revert_cdp.sh 가 크롬을 띄우고 이걸 부른다.
 */
const [wsUrl, base, runDir] = process.argv.slice(2);
const ws = new WebSocket(wsUrl);
let seq = 0; const 대기 = new Map();
ws.addEventListener("message", (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && 대기.has(m.id)) { const {resolve,reject}=대기.get(m.id); 대기.delete(m.id);
    m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result); }
});
function send(method, params) { const id = ++seq;
  return new Promise((res, rej) => { 대기.set(id,{resolve:res,reject:rej});
    ws.send(JSON.stringify({id, method, params: params||{}})); }); }
async function 평가(e) { const r = await send("Runtime.evaluate",
  {expression:e, returnByValue:true, awaitPromise:true});
  if (r.exceptionDetails) throw new Error("페이지 예외: "+JSON.stringify(r.exceptionDetails.exception));
  return r.result.value; }
const 잠깐 = (ms) => new Promise(r=>setTimeout(r,ms));
let 실패 = 0;
function check(id, 설명, ok, 자세히) {
  console.log(`${ok?"PASS":"FAIL"} ${id}  ${설명}${자세히?"  "+자세히:""}`); if(!ok) 실패=1; }
function 중단(왜) { console.log(`FAIL ---  ${왜}`); console.log("----");
  console.log("되돌리기 CDP 검증 중단 — 버튼을 누르지 않았다"); process.exit(1); }

await new Promise(r => ws.addEventListener("open", r));
await send("Page.enable"); await send("Runtime.enable");
await send("Page.navigate", {url: `${base}/?run_dir=${runDir}`});
await 잠깐(3500);

// ── 사전 상태: 되돌리기 잡의 **id 집합** ────────────────────────────────────
//
// **개수를 세면 안 된다** (WR-05). `GET /jobs` 는 최근 20건만 준다. 창 안에 이미
// revert_* 잡이 1건 이상 있는 상태에서 하네스가 진짜로 되돌리기를 접수해 버리면,
// 새 잡이 들어오면서 제일 오래된 revert 잡이 창 밖으로 밀려 **개수가 그대로**다
// → "한 건도 안 나갔다" 가 거짓인데 초록이 된다. 이 하네스의 제일 강한 주장이
// 하필 그 자리였다. 어제 472건을 실제로 되돌린 뒤라 레지스트리에 revert 잡이
// 있는 지금이 정확히 그 조건이다.
//
// 그래서 id 집합으로 본다. 판정은 **"사전에 없던 revert 잡 id 가 0개"** 다 —
// 창 밖으로 밀려난 것(사전에만 있는 id)은 새 요청이 나갔다는 증거가 아니므로
// 그것 때문에 빨개지지 않고, 새로 생긴 것은 무조건 잡힌다.
const 되돌리기id = `j => j.jobs.filter(x=>/^revert_/.test(x.kind)).map(x=>x.id).sort()`;
const 사전 = await 평가(`fetch("/jobs",{headers:{"Accept":"application/json"}}).then(r=>r.json())
  .then(j => ({ 되돌리기: (${되돌리기id})(j),
                실행잡: (j.jobs.find(x=>x.kind==="bids_commit")||{}).id || null }))`);
console.log(`기준: 되돌리기 잡 ${사전.되돌리기.length}건 [${사전.되돌리기.map(x=>x.slice(0,8)).join(" ")}] · 최근 실행 잡 ${사전.실행잡 || "없음"}`);

// ── 위험 구역 (D-14 / T-1-43) ───────────────────────────────────────────────
const 위험 = await 평가(`(() => {
  var s = document.getElementById("danger-zone");
  var d = document.getElementById("danger-details");
  var b = document.getElementById("revert-round-btn");
  var c = document.getElementById("revert-round-confirm");
  return { 있나: !!s, 접힘: d ? !d.open : null, 버튼있나: !!b,
           확인숨김: c ? c.hidden : null,
           글: s ? s.textContent.replace(/\\s+/g," ") : "",
           작업분버튼: !!document.getElementById("revert-job-btn") };
})()`);
check("V-RVT-01", "위험 구역이 있고 **기본이 접혀 있다**",
      위험.있나 && 위험.접힘 === true, JSON.stringify({접힘:위험.접힘}));
check("V-RVT-02", "회차 전체 되돌리기 버튼이 그 안에 있다", 위험.버튼있나);
check("V-RVT-03", "확인 단계는 처음엔 숨어 있다", 위험.확인숨김 === true);
check("V-RVT-04", "회차 전체가 무엇인지 글로 말한다",
      /인상분 전부/.test(위험.글) && /이 작업분만 되돌리기/.test(위험.글));
check("V-RVT-05", "보드 화면에는 작업분 버튼이 없다 (조각이 다르다)",
      위험.작업분버튼 === false);

// ── 실행 결과 조각을 띄운다 (실제 실행 잡의 산출물) ────────────────────────
if (!사전.실행잡) { 중단("실행(bids_commit) 잡이 레지스트리에 없다 — 결과 표를 띄울 수 없다"); }

await 평가(`(() => {
  document.getElementById("result").hidden = false;
  htmx.ajax("GET", "/jobs/${사전.실행잡}/result", {target:"#result-body", swap:"innerHTML"});
})()`);
await 잠깐(2500);

const 결과 = await 평가(`(() => {
  var b = document.getElementById("revert-job-btn");
  if (!b) return null;
  return { job: b.dataset.job, n: Number(b.dataset.n), 잠김: b.disabled,
           문구: b.textContent.trim(),
           회차전체버튼이표안에: !!document.querySelector("#result-body #revert-round-btn") };
})()`);
check("V-RVT-06", "결과 표에 작업분 되돌리기 버튼이 그려진다", !!결과, JSON.stringify(결과));
if (!결과) { 중단("결과 표에 되돌리기 버튼이 없다"); }
check("V-RVT-07", "그 버튼이 가리키는 잡이 방금 그 실행 잡이다", 결과.job === 사전.실행잡);
check("V-RVT-08", "결과 표 안에 회차 전체 버튼이 **없다** (T-1-43)",
      결과.회차전체버튼이표안에 === false);

// 건수는 서버 산출물에서 직접 받아 대조한다 — 화면이 말한 수를 믿지 않는다.
const 정답 = await 평가(`fetch("/jobs/${사전.실행잡}/result?format=json",
  {headers:{"Accept":"application/json"}}).then(r=>r.json())
  .then(j => ({ 성공: j.succeeded, 총: j.total, 날짜경고: !!j.date_mismatch,
                인상일: j.raise_date, 오늘: j.today }))`);
check("V-RVT-09", "버튼 옆 건수 == 서버가 센 인상 성공 건수",
      결과.n === 정답.성공, `화면 ${결과.n} / 서버 ${정답.성공}`);
check("V-RVT-10", "성공이 0건이 아니면 버튼이 열려 있다",
      정답.성공 > 0 ? 결과.잠김 === false : 결과.잠김 === true,
      `성공 ${정답.성공} · 잠김 ${결과.잠김}`);

// Pitfall 4 배너 — **같으면 안 뜨고 다르면 뜬다.** 늘 떠 있으면 경고가 아니라 배경이다.
const 배너 = await 평가(`document.getElementById("result-body").textContent.replace(/\\s+/g," ")`);
check("V-RVT-11", `Pitfall 4 배너가 날짜에 따라 갈린다 (인상일 ${정답.인상일} · 오늘 ${정답.오늘})`,
      정답.날짜경고 === /날짜를 넘겼다/.test(배너),
      정답.날짜경고 ? "다름 → 떠야 한다" : "같음 → 안 떠야 한다");

// ── 두 버튼의 **실제 화면상 거리** (T-1-43) ────────────────────────────────
// "조각이 다르다" 까지는 pytest 가 본다. 여기서는 픽셀을 잰다 — 접힌 위험 구역을
// 일부러 펼쳐 놓고도 멀리 떨어져 있어야 한다.
await 평가(`document.getElementById("danger-details").open = true`);
await 잠깐(400);
const 거리 = await 평가(`(() => {
  var a = document.getElementById("revert-job-btn").getBoundingClientRect();
  var b = document.getElementById("revert-round-btn").getBoundingClientRect();
  var sa = document.getElementById("revert-job-btn").closest("section");
  var sb = document.getElementById("revert-round-btn").closest("section");
  return { 세로거리: Math.round(Math.abs((b.top + window.scrollY) - (a.top + window.scrollY))),
           같은섹션: sa === sb, 섹션a: sa ? sa.id : null, 섹션b: sb ? sb.id : null };
})()`);
check("V-RVT-12", "두 버튼이 서로 다른 섹션에 있다",
      거리.같은섹션 === false, `${거리.섹션a} vs ${거리.섹션b}`);
check("V-RVT-13", "두 버튼의 세로 거리가 한 화면(1000px)보다 멀다",
      거리.세로거리 > 1000, `${거리.세로거리}px`);

// ── 회차 전체: 확인 단계 (D-14) ────────────────────────────────────────────
const 서버건수 = await 평가(`fetch("/jobs/revert/round/count?run_dir=${runDir}",
  {headers:{"Accept":"application/json"}}).then(r=>r.json()).then(j=>j.total)`);

await 평가(`document.getElementById("revert-round-btn").click()`);
await 잠깐(1500);
const 확인 = await 평가(`(() => {
  var c = document.getElementById("revert-round-confirm");
  return { 열림: !c.hidden,
           글: document.getElementById("revert-round-msg").textContent.replace(/\\s+/g," ").trim(),
           수: document.getElementById("revert-round-count").value,
           ok잠김: document.getElementById("revert-round-ok").disabled };
})()`);
check("V-RVT-14", "회차 전체 버튼은 **바로 접수하지 않고** 확인 단계를 띄운다", 확인.열림 === true);
check("V-RVT-15", "확인 문구의 건수 == 서버가 센 수",
      Number(확인.수) === 서버건수, `화면 ${확인.수} / 서버 ${서버건수}`);
check("V-RVT-16", "확인 문구가 '방금 누른 작업만이 아니다' 를 말한다",
      /방금 누른 작업만이 아니다/.test(확인.글), 확인.글);
// V-RVT-26 과 **같은 잣대**를 쓴다 — 개수가 아니라 id 집합이다(WR-05).
const 확인단계잡 = await 평가(`fetch("/jobs",{headers:{"Accept":"application/json"}})
  .then(r=>r.json()).then(${되돌리기id})`);
const 확인단계새것 = 확인단계잡.filter(id => 사전.되돌리기.indexOf(id) === -1);
check("V-RVT-17", "확인 단계가 떠도 아직 아무 잡도 안 생겼다",
      확인단계새것.length === 0,
      `새로 생긴 것 ${확인단계새것.length}건`);

// 취소 — **아무 요청도 보내지 않는다.**
await 평가(`document.getElementById("revert-round-cancel").click()`);
await 잠깐(600);
const 취소후 = await 평가(`(() => ({
  닫힘: document.getElementById("revert-round-confirm").hidden,
  수: document.getElementById("revert-round-count").value,
  버튼열림: !document.getElementById("revert-round-btn").disabled }))()`);
check("V-RVT-18", "취소하면 확인 단계가 닫히고 승인한 건수가 지워진다",
      취소후.닫힘 === true && 취소후.수 === "" && 취소후.버튼열림 === true,
      JSON.stringify(취소후));

// ── 배선과 요청 본문 (진짜로 보내지 않고) ──────────────────────────────────
//
// 여기부터가 위험 구간이다. **가로채기가 걸렸는지 프로브로 먼저 확인한다.**
const 프로브 = await 평가(`(() => {
  window.__보낸것 = [];
  window.__원래fetch = window.fetch;
  window.fetch = function (u, o) {
    var url = String(u);
    window.__보낸것.push({ url: url, method: (o && o.method) || "GET", body: o && o.body });
    if ((o && o.method) === "POST") {
      // 접수를 흉내 내지 않는다 — 409 로 끊어 board.js 가 후속 폴링으로 가지 않게 한다.
      return Promise.resolve(new Response(JSON.stringify({detail:"CDP 하네스가 가로챘다"}),
        { status: 409, headers: {"Content-Type":"application/json"} }));
    }
    return window.__원래fetch.apply(window, arguments);
  };
  return true;
})()`);
await 평가(`fetch("/healthz")`);   // 프로브
await 잠깐(400);
const 걸렸나 = await 평가(`window.__보낸것.length`);
if (!프로브 || 걸렸나 < 1) {
  await 평가(`if (window.__원래fetch) { window.fetch = window.__원래fetch; }`);
  중단("fetch 가로채기가 안 걸렸다 — 진짜 요청이 나갈 수 있으므로 버튼을 누르지 않는다");
}
check("V-RVT-19", "fetch 가로채기가 걸렸다 (여기서부터 클릭이 안전하다)", 걸렸나 >= 1);

await 평가(`window.__보낸것 = []`);
await 평가(`document.getElementById("revert-job-btn").click()`);
await 잠깐(800);
const 작업분요청 = await 평가(`window.__보낸것.filter(x=>x.method==="POST")`);
check("V-RVT-20", "작업분 버튼이 /jobs/revert/job 으로 POST 한다",
      작업분요청.length === 1 && /\/jobs\/revert\/job$/.test(작업분요청[0].url),
      JSON.stringify(작업분요청.map(x=>x.url)));
if (작업분요청.length === 1) {
  const 본문 = JSON.parse(작업분요청[0].body || "{}");
  check("V-RVT-21", "본문은 실행 잡 id **하나뿐**이다 (대상 목록을 화면이 만들지 않는다)",
        Object.keys(본문).length === 1 && 본문.commit_job_id === 사전.실행잡,
        JSON.stringify(본문));
  check("V-RVT-22", "본문에 ad_ids 같은 대상 필드가 없다 (D-13 / T-1-06)",
        !("ad_ids" in 본문) && !("only_ads" in 본문));
}

// 회차 전체도 같은 방식으로 본문만 본다. 확인 단계를 다시 거친다.
await 평가(`window.__보낸것 = []`);
await 평가(`document.getElementById("revert-round-btn").click()`);
await 잠깐(1200);
await 평가(`document.getElementById("revert-round-ok").click()`);
await 잠깐(800);
const 전체요청 = await 평가(`window.__보낸것.filter(x=>x.method==="POST")`);
check("V-RVT-23", "회차 전체 버튼이 /jobs/revert/round 로 POST 한다",
      전체요청.length === 1 && /\/jobs\/revert\/round$/.test(전체요청[0].url),
      JSON.stringify(전체요청.map(x=>x.url)));
if (전체요청.length === 1) {
  const 본문 = JSON.parse(전체요청[0].body || "{}");
  check("V-RVT-24", "본문에 회차와 **사용자가 승인한 건수**가 실린다 (D-14)",
        본문.run_dir === runDir && 본문.confirmed_count === 서버건수,
        JSON.stringify(본문));
}

// 오류(409)를 받으면 사유를 화면에 보여준다 — 숫자만 띄우면 사람이 못 읽는다.
const 오류 = await 평가(`(() => { var b = document.getElementById("job-error");
  return { 보임: !b.hidden, 글: b.textContent.replace(/\\s+/g," ").trim() }; })()`);
check("V-RVT-25", "거부당하면 사유가 화면에 뜬다",
      오류.보임 && /가로챘다/.test(오류.글), 오류.글);

await 평가(`window.fetch = window.__원래fetch`);

// ── 사후 확인: 되돌리기 잡이 한 건도 안 생겼다 ──────────────────────────────
await 잠깐(500);
const 사후 = await 평가(`fetch("/jobs",{headers:{"Accept":"application/json"}}).then(r=>r.json())
  .then(${되돌리기id})`);
const 새로생긴것 = 사후.filter(id => 사전.되돌리기.indexOf(id) === -1);
check("V-RVT-26", "**되돌리기 잡이 한 건도 안 생겼다** (실제 광고 API 호출 0)",
      새로생긴것.length === 0,
      `전 ${사전.되돌리기.length}건 / 후 ${사후.length}건 · 새로 생긴 것 ${새로생긴것.length}건` +
      (새로생긴것.length ? ` [${새로생긴것.map(x=>x.slice(0,8)).join(" ")}]` : ""));

console.log("----");
console.log(실패 ? "되돌리기 CDP 검증 실패"
                : "되돌리기 CDP 검증 전량 PASS — 되돌리기 요청은 서버에 한 건도 안 나갔다");
process.exit(실패);
