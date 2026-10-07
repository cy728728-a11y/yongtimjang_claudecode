// 판매자 스토어 전체상품(리뷰 많은순 1페이지) 읽기 — common.js 뒤에 이어붙는다.
// ITEMS = [{url, base}], OPTS = {sleep, sleepMax, wallMs}
//
// 2026-10-08 실측 근거(evidence/probe-2026-10.md "2026-10-08 스토어 확장"):
//  - <base>/category/ALL?st=REVIEW&dt=BIG_IMAGE&page=1&size=80 → 리뷰 많은순 전체상품
//  - window.__PRELOADED_STATE__.categoryProducts.simpleProducts[] 에 상품 목록
//  - base 를 모르면(검색 결과 main/products/<id>) 상품을 열어 리다이렉트된 주소에서 슬러그를 얻는다
// 리뷰 내림차순이라 500 미만이 처음 나오는 곳에서 자른다. 판정·가격 계산은 Python(rules.store_*) 몫.

const MIN_REVIEW = OPTS.minReview || 500;
const WALL_MS = OPTS.wallMs || 105000;     // repl 120초 벽 아래. 넘기 전에 남은 스토어는 다음 호출로 미룬다
const T0 = Date.now();
const STORE_HOSTS = ["smartstore.naver.com", "brand.naver.com"];

// 주소 → 스토어 base. 슬러그가 없거나(main) 다른 호스트면 "".
const baseOf = (href) => {
  try {
    const u = new URL(href);
    const host = u.host.replace(/^m\./, "");
    const slug = u.pathname.split("/").filter(Boolean)[0] || "";
    if (!STORE_HOSTS.includes(host) || !slug || slug === "main") return "";
    return `https://${host}/${slug}`;
  } catch (e) { return ""; }
};

// 페이지 안에서 목록을 정규화한다. 데이터가 없으면 null.
const LIST = () => {
  const pre = window.__PRELOADED_STATE__ || {};
  const sp = (pre.categoryProducts || {}).simpleProducts;
  if (!Array.isArray(sp)) return null;
  return sp.map((p) => {
    const oa = p.originAreaInfo || p.originArea || null;
    const origin = typeof oa === "string" ? oa : (oa && (oa.content || oa.originAreaName || oa.name)) || "";
    return {
      id: p.id ?? null,
      productNo: p.productNo ?? null,
      name: p.name ?? p.productName ?? "",
      price: p.benefitsView?.discountedSalePrice ?? p.discountedSalePrice ?? p.salePrice ?? null,
      salePrice: p.salePrice ?? null,
      review: p.reviewAmount?.totalReviewCount ?? 0,
      category: p.category?.wholeCategoryName ?? "",
      display: p.channelProductDisplayStatusType ?? "",
      origin,
    };
  });
};

await openTab("https://www.naver.com/");
for (let i = 0; i < ITEMS.length; i++) {
  if (i > 0 && Date.now() - T0 > WALL_MS - 25000) break;
  const url = ITEMS[i].url || "";
  const started = Date.now();
  const r = { kind: "store", key: url || ITEMS[i].base, base: ITEMS[i].base || "", href: "", 상태: null,
              items: [], total: 0, error: null };
  let stop = false;
  try {
    let st = "정상";
    if (!r.base) {
      st = await settle(url);
      if (st !== "캡챠" && st !== "차단") {
        r.href = await page.evaluate(() => location.href);
        r.base = baseOf(r.href);
      }
    }
    if (st === "캡챠" || st === "차단") {
      r.상태 = st === "캡챠" ? "캡챠감지" : "차단감지"; r.error = "Aside 창에서 직접 확인 필요"; stop = true;
    } else if (!r.base) {
      r.상태 = "미지원"; r.error = `스토어 주소를 못 구함: ${r.href || url}`;
    } else {
      st = await settle(r.base + "/category/ALL?st=REVIEW&dt=BIG_IMAGE&page=1&size=80");
      if (st === "캡챠" || st === "차단") {
        r.상태 = st === "캡챠" ? "캡챠감지" : "차단감지"; r.error = "Aside 창에서 직접 확인 필요"; stop = true;
      } else {
        let list = await page.evaluate(LIST);
        for (let w = 0; !list && w < 6; w++) { await sleep(500); list = await page.evaluate(LIST); }
        if (!list) {
          const meta = await page.evaluate(() => ({ t: document.title, h: location.href }));
          r.상태 = "미지원"; r.error = `목록 데이터 없음: ${meta.t} ${meta.h}`;
        } else {
          r.total = list.length;
          const cut = list.findIndex((x) => (x.review || 0) < MIN_REVIEW);
          r.items = cut < 0 ? list : list.slice(0, cut);
          r.상태 = "성공";
        }
      }
    }
  } catch (e) {
    r.상태 = "파싱실패";
    r.error = String(e && e.message ? e.message : e);
    try {
      const st = await page.evaluate(PAGESTATE);
      if (st === "캡챠" || st === "차단") { r.상태 = st === "캡챠" ? "캡챠감지" : "차단감지"; stop = true; }
    } catch (e2) { /* 상태 확인 실패는 무시 — 파싱실패로 남긴다 */ }
  }
  r.초 = Math.round((Date.now() - started) / 100) / 10;
  emit(r);
  console.log(`[${i + 1}/${ITEMS.length}] ${r.상태} ${r.base} ${r.items.length}/${r.total} ${r.초}s`);
  if (stop) break;
  if (i < ITEMS.length - 1 && Date.now() - T0 < WALL_MS - 25000) await sleep(rand(OPTS.sleep, OPTS.sleepMax) * 1000);
}
console.log("__DONE__");
