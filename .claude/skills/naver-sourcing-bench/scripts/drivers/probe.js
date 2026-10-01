// 실측 전용. 검색·카테고리·상세 페이지의 내장 JSON 키 구조를 덤프한다.
const ITEMS = __ITEMS__; const OPTS = __OPTS__;
const keysOf = (o, d = 0) => (o && typeof o === "object" && d < 6)
  ? Object.fromEntries(Object.keys(o).slice(0, 40).map(k => [k, keysOf(o[k], d + 1)])) : typeof o;
await openTab("https://search.shopping.naver.com/");
for (const url of ITEMS) {
  await page.goto(url); await sleep(4000);
  const r = await page.evaluate(() => {
    const nd = document.querySelector("#__NEXT_DATA__");
    const pre = window.__PRELOADED_STATE__;
    return { href: location.href,
             next: nd ? JSON.parse(nd.textContent) : null,
             pre: pre ? JSON.parse(JSON.stringify(pre)) : null,
             text: (document.body.innerText || "").slice(0, 1500) };
  });
  console.log("__R__ " + JSON.stringify({ kind: "probe", url, href: r.href,
    nextKeys: keysOf(r.next), preKeys: keysOf(r.pre), text: r.text,
    sample: JSON.stringify(r.next || r.pre).slice(0, 20000) }));
}
console.log("__DONE__");
