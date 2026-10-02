// 상세페이지 옵션 펼쳐 읽기 — common.js 뒤에 이어붙는다.
// ITEMS = [{url}], OPTS = {sleep, sleepMax, maxCombos}
//
// 2026-10-02 실측 근거(evidence/probe-2026-10.md):
//  - 옵션 섹션 = 리프 텍스트가 '옵션 선택' 으로 시작하는 요소의 조상(최대 5단계 올라가 a/button 을 가진 것)
//  - 축 버튼 = 섹션 안 a[role="button"][aria-haspopup="listbox"] (텍스트 = 축 이름)
//  - 목록 = 섹션 안 ul[role="listbox"] li (li 안 a[role="option"]). 1단 목록은 클릭 전에도 DOM 에 있다
//  - 다단은 앞 축 항목을 골라야 다음 축 목록이 열린다 → 재귀로 일반화
//  - 옵션 섹션 없음 + '수량' 선택만 있음 = 단품. 표준그룹상품(radiogroup)은 읽기실패 처리
//  - 캡챠 0회/6상품, 상품당 10~15초
// 가격 계산은 Python(rules.build_options)이 priceText·combos 로 한다. 여기서는 원문만 모은다.

const MAX_COMBOS = OPTS.maxCombos || 50;
const PER_ITEM_MS = 90000;                 // 상품당 상한 — 넘으면 읽기실패(시간초과)
const WALL_MS = OPTS.wallMs || 105000;     // repl 120초 벽 아래. 넘기 전에 남은 상품은 다음 호출로 미룬다
const T0 = Date.now();

// 페이지 안에서 eval 되는 조작 함수. op: info | open | list | pick
const H = `(op, k, j) => {
  const clean = (t) => (t || "").replace(/\\s+/g, " ").trim();
  const vis = (e) => !!(e && (e.offsetParent || e.getClientRects().length));
  const head = [...document.querySelectorAll("*")].find(
    (e) => e.children.length === 0 && /^옵션 선택/.test(clean(e.textContent)));
  let sec = null;
  if (head) {
    let s = head.parentElement;
    for (let n = 0; s && n < 5; n++) { if (s.querySelector("a,button")) break; s = s.parentElement; }
    sec = s;
  }
  const axes = sec ? [...sec.querySelectorAll('a[role="button"][aria-haspopup="listbox"]')].filter(vis) : [];
  const listOf = (i) => {
    const btn = axes[i], next = axes[i + 1];
    if (!btn) return null;
    const pool = [...(sec || document).querySelectorAll('ul[role="listbox"]')];
    const cand = pool.filter((l) => (btn.compareDocumentPosition(l) & Node.DOCUMENT_POSITION_FOLLOWING)
      && (!next || (l.compareDocumentPosition(next) & Node.DOCUMENT_POSITION_FOLLOWING)));
    return cand.find(vis) || cand[0] || null;
  };
  if (op === "info") {
    const t = document.body.innerText || "";
    const pi = t.indexOf("상품 가격");
    return {
      found: !!sec,
      axes: axes.map((a) => clean(a.innerText)),
      hasQty: /수량/.test(t),
      hasRadio: !!document.querySelector('div[role="radiogroup"]'),
      gone: /판매가 종료|판매 종료된|판매중지|존재하지 않는 상품|삭제된 상품/.test(t.slice(0, 4000)),
      ready: !!sec || pi >= 0 || /구매하기/.test(t),
      priceText: pi >= 0 ? t.slice(pi, pi + 200) : "",
    };
  }
  if (op === "open") {
    const l = listOf(k);
    if (l && vis(l) && l.querySelector("li")) return true;
    if (!axes[k]) return false;
    axes[k].click();
    return true;
  }
  const l = listOf(k);
  const lis = l ? [...l.querySelectorAll("li")] : [];
  if (op === "list") {
    return lis.map((li) => {
      const a = li.querySelector('a[role="option"]') || li;
      return { t: clean(li.innerText || li.textContent),
               dis: a.getAttribute("aria-disabled") === "true" || li.getAttribute("aria-disabled") === "true" };
    }).filter((x) => x.t);
  }
  if (op === "pick") {
    const li = lis[j];
    if (!li) return false;
    (li.querySelector('a[role="option"]') || li).click();
    return true;
  }
  return null;
}`;

async function q(op, k = 0, j = 0) {
  return await page.evaluate(({ H, op, k, j }) => eval(H)(op, k, j), { H, op, k, j });
}

async function readAxis(k) {
  await q("open", k);
  await sleep(800);
  let items = await q("list", k);
  if (!items.length) { await sleep(1200); await q("open", k); await sleep(800); items = await q("list", k); }
  return items;
}

// 축 k 를 펼쳐 combos 에 조합을 쌓는다. 50 초과가 확정되면 true(옵션초과)를 돌려 즉시 멈춘다.
async function walk(k, prefix, nAxes, combos, deadline) {
  if (Date.now() > deadline) throw new Error("시간초과");
  const items = await readAxis(k);
  if (!items.length) throw new Error(`${k + 1}번째 옵션 목록이 비어 있음`);
  if (k === nAxes - 1) {
    for (const it of items) {
      combos.push([...prefix, it.t]);
      if (combos.length > MAX_COMBOS) return true;
    }
    return false;
  }
  if (k === 0 && items.length > MAX_COMBOS) return true;   // 1축 항목 수만으로 초과 확정
  for (let j = 0; j < items.length; j++) {
    const it = items[j];
    if (it.dis) {
      // 고를 수 없는(품절) 앞 축 값 — 하위 축을 못 열므로 품절 조합 하나로 센다
      combos.push([...prefix, it.t + " (품절)"]);
      if (combos.length > MAX_COMBOS) return true;
      continue;
    }
    await q("open", k);
    await sleep(600);
    if (!(await q("pick", k, j))) throw new Error(`${k + 1}번째 축 ${j + 1}번 항목 선택 실패`);
    await sleep(1000);
    if (await walk(k + 1, [...prefix, it.t], nAxes, combos, deadline)) return true;
  }
  return false;
}

await openTab("https://www.naver.com/");
for (let i = 0; i < ITEMS.length; i++) {
  // repl 벽에 걸리기 전에 멈춘다 — 받지 못한 상품은 Python 이 다음 호출에 다시 넣는다
  if (i > 0 && Date.now() - T0 > WALL_MS - 30000) break;
  const url = ITEMS[i].url;
  const started = Date.now();
  const r = { kind: "options", key: url, 상태: null, axes: [], priceText: "", combos: [], error: null };
  let stop = false;
  try {
    const st = await settle(url);
    if (st === "캡챠" || st === "차단") {
      r.상태 = st === "캡챠" ? "캡챠감지" : "차단감지";
      r.error = "Aside 창에서 직접 확인 필요";
      stop = true;
    } else {
      let info = await q("info");
      for (let w = 0; !info.ready && w < 16; w++) { await sleep(500); info = await q("info"); }
      await sleep(800);
      info = await q("info");
      r.axes = info.axes;
      r.priceText = info.priceText;
      if (info.gone) {
        r.상태 = "읽기실패"; r.error = "판매 종료/삭제 상품";
      } else if (!info.found) {
        if (info.hasQty && !info.hasRadio && info.priceText) r.상태 = "단품";
        else { r.상태 = "읽기실패"; r.error = info.hasRadio ? "표준그룹상품(radiogroup)" : "옵션 섹션 없음"; }
      } else if (!info.axes.length) {
        r.상태 = "읽기실패"; r.error = "옵션 축 버튼 없음";
      } else {
        const deadline = Math.min(started + PER_ITEM_MS, T0 + WALL_MS);
        const over = await walk(0, [], info.axes.length, r.combos, deadline);
        r.상태 = over ? "옵션초과" : "성공";
      }
    }
  } catch (e) {
    r.상태 = "읽기실패";
    r.error = String(e && e.message ? e.message : e);
    try {
      const st = await page.evaluate(PAGESTATE);
      if (st === "캡챠" || st === "차단") { r.상태 = st === "캡챠" ? "캡챠감지" : "차단감지"; stop = true; }
    } catch (e2) { /* 상태 확인 실패는 무시 — 읽기실패로 남긴다 */ }
  }
  r.초 = Math.round((Date.now() - started) / 100) / 10;
  if (r.상태 === "옵션초과") r.combos = r.combos.slice(0, MAX_COMBOS + 1);
  emit(r);
  console.log(`[${i + 1}/${ITEMS.length}] ${r.상태} ${r.combos.length}조합 ${r.초}s`);
  if (stop) break;
  if (i < ITEMS.length - 1 && Date.now() - T0 < WALL_MS - 30000) await sleep(rand(OPTS.sleep, OPTS.sleepMax) * 1000);
}
console.log("__DONE__");
