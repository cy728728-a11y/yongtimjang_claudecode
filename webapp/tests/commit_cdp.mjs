/* 실행 버튼(FLOW-01) 브라우저 검증 — 진짜 크롬에서 "언제 열리는가" 만 본다.
 *
 * **이 스크립트는 실행 버튼을 절대 누르지 않는다.** 누르는 순간 진짜 광고비가 나간다.
 * 여기서 확인하는 것은 게이트뿐이다: 미리보기 전에는 잠겨 있고, 미리보기가 끝나야
 * 열리고, 새로고침하면 다시 잠긴다. 미리보기는 dry-run 이라 크레딧 0 · 광고비 0 이다.
 *
 * 왜 pytest 가 아닌가: 버튼을 여는 판단이 board.js 안에서만 산다. TestClient 는 JS 를
 * 한 줄도 실행하지 않아 "미리보기 없이 눌리는가" 를 못 본다 — 그런데 그게 이 화면에서
 * 제일 비싼 사고다(미리보기 없이 실행 = 본 적 없는 대상에 PUT).
 *
 * 판정 기준을 "버튼이 보인다" 로 쓰지 않는다(01-04·01-06·01-07 의 교훈). 요약 숫자는
 * **서버 산출물에서 직접 받아** 대조한다 — 그럴듯한 다른 수가 같은 자리에 들어가도
 * 육안으로는 안 잡히기 때문이다.
 *
 * 쓰는 법: webapp/tests/commit_cdp.sh 가 크롬을 띄우고 이걸 부른다.
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

await new Promise(r => ws.addEventListener("open", r));
await send("Page.enable"); await send("Runtime.enable");
await send("Page.navigate", {url: `${base}/?run_dir=${runDir}`});
await 잠깐(3500);

// ── 미리보기 전 ──────────────────────────────────────────────────────────
const 전 = await 평가(`(() => {
  var w = document.getElementById("commit-wrap"), b = document.getElementById("commit-btn");
  return { 있나: !!w, 숨김: w ? w.hidden : null, 잠김: b ? b.disabled : null,
           부모칸: (document.getElementById("commit-preview-job")||{}).value,
           미리보기자리숨김: document.getElementById("preview").hidden };
})()`);
check("V-CMT-01", "미리보기 전에는 실행 블록이 숨겨져 있다", 전.있나 && 전.숨김 === true, JSON.stringify(전));
check("V-CMT-02", "미리보기 전에는 실행 버튼이 잠겨 있다", 전.잠김 === true);
check("V-CMT-03", "미리보기 전에는 부모 job_id 가 비어 있다", !전.부모칸);

// 경고 배너 두 줄이 **DOM 에 실제로** 있다 (숨겨져 있어도 내용은 있어야 한다)
const 배너 = await 평가(`document.getElementById("commit-wrap").textContent.replace(/\\s+/g," ")`);
check("V-CMT-04", "경고 1 — 진짜 바꾼다", /진짜 입찰가를 바꾼다/.test(배너));
check("V-CMT-05", "경고 2 — 되돌리기는 당일 (Pitfall 4)",
      /되돌리기는 인상한 당일/.test(배너) && /쿨다운 6일/.test(배너));

// ── 한 상품만 골라 미리보기 ─────────────────────────────────────────────
const 고름 = await 평가(`(() => {
  var t = Tabulator.findTable("#board")[0];
  var 행 = t.getRows("active").find(r => (r.getData().rule1_count||0) > 0);
  if (!행) return null;
  행.select();
  var d = 행.getData();
  return { acct: d.acct, 대상: d.rule1_count, ads: d.rule1_ads.length };
})()`);
check("V-CMT-06", "①소재가 있는 상품 한 줄을 골랐다", !!고름, JSON.stringify(고름));

await 평가(`document.getElementById("preview-btn").click()`);
for (let i = 0; i < 40; i++) {
  await 잠깐(500);
  const 끝 = await 평가(`!document.getElementById("preview").hidden
    && document.getElementById("preview-body").textContent.indexOf("대상") >= 0`);
  if (끝) break;
}
await 잠깐(1200);

const 후 = await 평가(`(() => {
  var w = document.getElementById("commit-wrap"), b = document.getElementById("commit-btn");
  return { 숨김: w.hidden, 잠김: b.disabled,
           부모: document.getElementById("commit-preview-job").value,
           요약: document.getElementById("commit-summary").textContent.replace(/\\s+/g," ").trim(),
           예상: document.getElementById("commit-eta").textContent.replace(/\\s+/g," ").trim(),
           문구: b.textContent.trim(),
           결과자리: document.getElementById("result").hidden };
})()`);
check("V-CMT-07", "미리보기가 끝나면 실행 블록이 열린다", 후.숨김 === false, JSON.stringify(후.요약));
check("V-CMT-08", "미리보기가 끝나면 실행 버튼이 열린다", 후.잠김 === false, `문구 "${후.문구}"`);
check("V-CMT-09", "실행이 가리키는 부모는 방금 그 미리보기 job_id 다",
      /^[0-9a-f-]{36}$/.test(후.부모), 후.부모);
check("V-CMT-10", "실행 결과 자리는 아직 닫혀 있다", 후.결과자리 === true);

// 요약 숫자를 **서버 산출물에서 직접 세어** 대조한다 (라이브러리·화면을 믿지 않는다)
const 정답 = await 평가(`fetch("/jobs/" + document.getElementById("commit-preview-job").value
  + "/result?format=json", {headers:{"Accept":"application/json"}}).then(r=>r.json())
  .then(j => ({ total: j.total, 인상: (j.counts||{})["인상"]||0, 인상액: j.raise_total }))`);
const 요약수 = (후.요약.match(/[\d,]+/g) || []).map(s => Number(s.replace(/,/g,"")));
check("V-CMT-11", "요약의 대상 건수가 산출물과 같다", 요약수[0] === 정답.total,
      `화면 ${요약수[0]} / 산출물 ${정답.total}`);
check("V-CMT-12", "요약의 인상 건수가 산출물과 같다", 요약수[1] === 정답.인상,
      `화면 ${요약수[1]} / 산출물 ${정답.인상}`);
check("V-CMT-13", "요약의 인상액 합계가 산출물과 같다", 요약수[2] === 정답.인상액,
      `화면 ${요약수[2]} / 산출물 ${정답.인상액}`);
check("V-CMT-14", "예상 소요시간 문구가 붙는다 (OQ-3 — 진행률이 없다)",
      /초당 12건/.test(후.예상) && /약 \d/.test(후.예상), 후.예상);

// ── 페이지를 새로 열면 다시 잠긴다 (지난 미리보기를 되살리지 않는다) ────
await send("Page.navigate", {url: `${base}/?run_dir=${runDir}`});
await 잠깐(3000);
const 다시 = await 평가(`(() => {
  var w = document.getElementById("commit-wrap"), b = document.getElementById("commit-btn");
  return { 숨김: w.hidden, 잠김: b.disabled };
})()`);
check("V-CMT-15", "새로고침하면 실행 버튼이 다시 잠긴다 (FLOW-01)",
      다시.숨김 === true && 다시.잠김 === true, JSON.stringify(다시));

console.log("----");
console.log(실패 ? "실행 버튼 CDP 검증 실패" : "실행 버튼 CDP 검증 전량 PASS — 버튼은 누르지 않았다");
process.exit(실패);
