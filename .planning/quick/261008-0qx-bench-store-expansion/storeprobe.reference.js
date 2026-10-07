const ITEMS = __ITEMS__; const OPTS = __OPTS__;
await openTab("https://www.naver.com/");
for (const url of ITEMS) {
  await page.goto(url); await sleep(6000);
  const r = await page.evaluate(() => {
    const pre = window.__PRELOADED_STATE__ || {};
    const s = JSON.stringify(pre);
    const keys = Object.keys(pre);
    // 상품 목록 후보 키 찾기
    const hits = [];
    for (const k of ["simpleProducts","categoryProducts","products","reviewCount","totalReviewCount","reviewAmount","totalCount"]) {
      let i = s.indexOf('"'+k+'"'); hits.push([k, i<0?null:s.slice(i, i+300)]);
    }
    const t = document.body.innerText || "";
    return { href: location.href, title: document.title, keys, len: s.length, hits, text: t.slice(0, 1200) };
  });
  console.log("__R__ " + JSON.stringify({ url, ...r }));
  await sleep(3000);
}
console.log("__DONE__");
