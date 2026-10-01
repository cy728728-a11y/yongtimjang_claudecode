// 공통 조각 — scan/search 앞에 이어붙는다.
const ITEMS = __ITEMS__;
const OPTS = __OPTS__;
const CAPTCHA_SETTLE_TRIES = 5;   // aside-category 실측: 캡챠 화면이 5초 안에 스스로 풀리기도 한다
const CAPTCHA_SETTLE_MS = 2000;
const rand = (a, b) => a + Math.random() * (b - a);
const emit = (r) => console.log("__R__ " + JSON.stringify(r));

const PAGESTATE = () => {
  const t = document.body.innerText || "";
  if (/자동입력 방지|보안문자|캡차|captcha|보안 확인을 완료/i.test(t) || /captcha/i.test(location.href)) return "캡챠";
  if (document.querySelector('img[src*="captcha" i], input[id*="captcha" i], input[name*="captcha" i]')) return "캡챠";
  if (/일시적으로 제한|접속이 제한|비정상적인 접근|비정상적인 검색/.test(t)) return "차단";
  if (/검색결과가 없습니다|검색 결과가 없습니다|일치하는 상품이 없습니다/.test(t)) return "없음";
  return "정상";
};

// goto 후 캡챠 정착까지 기다린 최종 상태
async function settle(url) {
  await page.goto(url);
  await sleep(1500);
  let st = await page.evaluate(PAGESTATE);
  for (let k = 0; st === "캡챠" && k < CAPTCHA_SETTLE_TRIES; k++) {
    await sleep(CAPTCHA_SETTLE_MS);
    st = await page.evaluate(PAGESTATE);
  }
  return st;
}

// 목록 페이지 → 공용 상품 dict 배열.
// 2026-10-01 실측: __NEXT_DATA__ props.pageProps.compositeList.list[].{type,item}.
//   type "product" = 일반 노출, "supersaving" = 같은 상품을 반복 노출하는 판촉 칸 → 광고로 취급해 제외.
//   가격비교(카탈로그) 상품은 mallProductUrl 이 비어 있어 카탈로그 주소로 대신한다.
const EXTRACT = () => {
  const nd = document.querySelector("#__NEXT_DATA__");
  if (!nd) return null;
  const pp = ((JSON.parse(nd.textContent).props || {}).pageProps) || {};
  const list = (pp.compositeList || {}).list || [];
  let rank = 0;
  return list.map((x) => {
    const it = x.item || {};
    const organic = x.type === "product";
    if (organic) rank++;
    return {
      순위: organic ? rank : 0,
      상품명: it.productTitle || it.productName || "",
      url: it.mallProductUrl || (it.id ? `https://search.shopping.naver.com/catalog/${it.id}` : ""),
      마켓명: it.mallName || (it.mallCount ? `가격비교(${it.mallCount}개몰)` : ""),
      가격: it.lowPrice ?? it.price ?? null,
      리뷰수: it.reviewCountSum ?? it.reviewCount ?? null,
      광고: !organic,
      카테고리: [it.category1Name || "", it.category2Name || "", it.category3Name || "", it.category4Name || ""],
    };
  });
};

// 한 페이지 읽기. 캡챠/차단이면 true 를 돌려 호출부가 중단하게 한다.
async function readList(key, url) {
  const r = { kind: "page", key, 상태: null, error: null, products: [] };
  try {
    const st = await settle(url);
    if (st === "캡챠" || st === "차단") {
      r.상태 = st === "캡챠" ? "캡챠감지" : "차단감지";
      r.error = "Aside 창에서 직접 확인 필요";
      emit(r); return true;
    }
    if (st === "없음") { r.상태 = "조회실패"; r.error = "결과 없음"; emit(r); return false; }
    const ps = await page.evaluate(EXTRACT);
    if (!ps || !ps.length) { r.상태 = "파싱실패"; r.error = "상품 목록 데이터 없음"; emit(r); return false; }
    r.상태 = "성공"; r.products = ps; emit(r);
  } catch (e) {
    r.상태 = "파싱실패"; r.error = String(e && e.message ? e.message : e); emit(r);
  }
  return false;
}
