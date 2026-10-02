const ITEMS = __ITEMS__; const OPTS = __OPTS__;
await openTab("https://www.naver.com/");
const SEC = `(() => {
  const h = [...document.querySelectorAll('*')].find(e => e.children.length===0 && /^옵션 선택/.test((e.textContent||"").trim()));
  if (!h) return null;
  let s = h.parentElement;
  for (let k=0; s && k<5; k++) { if (s.querySelectorAll('a,button').length) break; s = s.parentElement; }
  return s;
})()`;
for (const url of ITEMS) {
  await page.goto(url); await sleep(5000);
  const info = await page.evaluate((SEC) => {
    const s = eval(SEC); if (!s) return null;
    const btns = [...s.querySelectorAll('a,button')].filter(e=>e.offsetParent);
    return { html: s.outerHTML.slice(0,1500), btns: btns.map(b => ({tag:b.tagName, role:b.getAttribute('role'), hp:b.getAttribute('aria-haspopup'), exp:b.getAttribute('aria-expanded'), t:(b.innerText||"").trim()})) };
  }, SEC);
  const axes = [];
  const n = info ? info.btns.length : 0;
  for (let i = 0; i < n; i++) {
    await page.evaluate(({SEC,i}) => { const s = eval(SEC); const b=[...s.querySelectorAll('a,button')].filter(e=>e.offsetParent)[i]; b && b.click(); }, {SEC,i});
    await sleep(1200);
    const lst = await page.evaluate((SEC) => {
      const s = eval(SEC);
      const uls = [...(s ? s.querySelectorAll('ul,[role=listbox]') : [])].filter(u=>u.offsetParent);
      return uls.map(u => ({role:u.getAttribute('role'), items:[...u.querySelectorAll('li')].map(li=>(li.innerText||"").replace(/\s+/g," ").trim())}));
    }, SEC);
    axes.push({ i, lst });
    // 첫 항목 골라서 다음 축이 열리게
    await page.evaluate((SEC) => { const s = eval(SEC); const u=[...s.querySelectorAll('ul,[role=listbox]')].find(u=>u.offsetParent); const a=u && u.querySelector('li a, li button, li'); a && a.click(); }, SEC);
    await sleep(1000);
  }
  const after = await page.evaluate(() => { const t=document.body.innerText; const j=t.indexOf("구매하기"); return t.slice(Math.max(0,j-600), j); });
  console.log("__R__ " + JSON.stringify({ url, info, axes, after }));
  await sleep(3000 + Math.random()*3000);
}
console.log("__DONE__");
