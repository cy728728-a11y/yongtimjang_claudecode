// 키워드 검색 랭킹순 상위 40.
await openTab("https://search.shopping.naver.com/");
for (let i = 0; i < ITEMS.length; i++) {
  const kw = ITEMS[i].키워드;
  const url = "https://search.shopping.naver.com/search/all?query=" + encodeURIComponent(kw) + "&sort=rel&pagingSize=40";
  const stop = await readList(kw, url);
  console.log(`[${i + 1}/${ITEMS.length}] ${kw}`);
  if (stop) break;
  if (i < ITEMS.length - 1) await sleep(rand(OPTS.sleep, OPTS.sleepMax) * 1000);
}
console.log("__DONE__");
