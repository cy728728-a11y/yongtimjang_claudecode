// 세부 카테고리 페이지를 리뷰 많은 순으로 연다.
// 2026-10-01 실측: /search/category/<코드> 는 /search/category?catId= 로 리다이렉트되며 sort 가 빠진다 → 처음부터 catId 형식.
await openTab("https://search.shopping.naver.com/");
for (let i = 0; i < ITEMS.length; i++) {
  const code = ITEMS[i].코드;
  const url = `https://search.shopping.naver.com/search/category?catId=${code}&sort=review&pagingSize=40`;
  const stop = await readList(code, url);
  console.log(`[${i + 1}/${ITEMS.length}] ${code}`);
  if (stop) { console.log(`  ↳ 중단 (남은 ${ITEMS.length - i - 1}건)`); break; }
  if (i < ITEMS.length - 1) await sleep(rand(OPTS.sleep, OPTS.sleepMax) * 1000);
}
console.log("__DONE__");
