// 네이버 로그인 여부 판정. ITEMS/OPTS 는 쓰지 않지만 치환 자리는 남긴다.
// 2026-10-01 실측: 로그인 상태에서도 숨은 'btn_login' 링크가 DOM 에 남아 있어 버튼 유무로는 판정 불가.
// 로그인했을 때만 생기는 내 정보 영역(MyView info_user) 또는 NID_SES 쿠키로 본다.
const ITEMS = __ITEMS__; const OPTS = __OPTS__;
await openTab("https://www.naver.com/");
await page.goto("https://www.naver.com/");
await sleep(2500);
const r = await page.evaluate(() => {
  const my = !!document.querySelector('[class*="MyView-module__info_user"], [class*="MyView-module__my_info"]');
  const ses = /(?:^|;\s*)NID_SES=/.test(document.cookie);
  return { loggedIn: my || ses, hint: `myinfo=${my} NID_SES=${ses}` };
});
console.log("__R__ " + JSON.stringify({ kind: "login", ...r }));
console.log("__DONE__");
