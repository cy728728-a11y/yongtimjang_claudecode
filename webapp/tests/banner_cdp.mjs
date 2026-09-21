/* 전장 노출 브라우저 회귀 — **D-03a 를 기계가 집행한다.**
 *
 * 무엇을 증명하는가:
 *   ① 페이지의 장(`figure`) 개수가 산출물 `집계.장` 과 같다.
 *      **배너 수(`집계.배너`)와 같으면 실패다** — 배너로 판정한 것만 깔린 화면은
 *      오탐만 잡고 미탐을 구조적으로 못 본다(D-03a). 이 화면이 미탐 0% 의 측정
 *      장치 그 자체이므로, 여기가 빨개지면 이 페이즈의 통과 조건이 근거를 잃는다.
 *   ② 스킵된 상품도 전장을 깐다. 스킵 **판단 자체가 틀렸을 수 있다**(D-09).
 *   ③ 장을 클릭하면 라벨이 **DB 에 실제로 들어간다**. 테두리 클래스만 바뀌고 DB 가
 *      비면 실패다 — 그게 "미탐 0%" 를 거짓말로 만드는 정확한 모양이다.
 *      (DB 확인은 `banner_cdp.sh` 가 `sqlite3` 로 한다. 여기서는 클릭과 화면 반영까지.)
 *   ④ `확인함` 은 확인 테이블에만 쓴다. 라벨 수를 늘리면 "뒤집었다" 와 "다 봤다" 가
 *      섞인 것이고, 안 본 상품이 동의로 세어진다(Pitfall 8).
 *
 * 왜 pytest 가 아닌가 (Phase 1 결정): 클릭 → htmx POST → `outerHTML` 조각 교체는
 * **브라우저 JS 동작**이다. TestClient 는 JS 를 한 줄도 안 돌린다 — pytest 로 흉내
 * 내면 "우리가 짠 가짜 htmx" 를 검증하게 되고, 그건 초록색만 주고 버그는 하나도
 * 못 잡는다. 그래서 `sse_cdp.sh` 와 **같은 계층**에 둔다.
 *
 * 판정 기준을 "썸네일이 보인다" 로 쓰지 않는다. 04-06 이 정확히 그 함정에 빠질 뻔했다 —
 * 한글 경로 파라미터 때문에 모든 썸네일이 404 인데 "막혔다" 만 보는 검증은 전부 초록이었다.
 * 여기서는 **정상 경로가 실제로 200 을 내는지**(V-BANNER-00)를 먼저 단언한다.
 *
 * 쓰는 법: webapp/tests/banner_cdp.sh 가 임시 서버·크롬·합성 산출물을 깔고 이걸 부른다.
 */

const [devport, base, token, runDir, 총장Arg, 배너Arg, 스킵iArg, 스킵장수Arg] =
  process.argv.slice(2);
if (!devport || !base || !token || !runDir) {
  console.error("사용법: node banner_cdp.mjs <cdp포트> <서버주소> <토큰> <회차> " +
    "<총장> <배너> <스킵상품순번> <스킵장수>");
  process.exit(2);
}
const 총장 = Number(총장Arg);
const 배너 = Number(배너Arg);
const 스킵i = Number(스킵iArg);
const 스킵장수 = Number(스킵장수Arg);

const 잠깐 = (ms) => new Promise((r) => setTimeout(r, ms));

let 실패 = 0;
function check(id, 설명, ok, 자세히) {
  console.log(`${ok ? "PASS" : "FAIL"} ${id}  ${설명}${자세히 ? "  " + 자세히 : ""}`);
  if (!ok) { 실패 = 1; }
}

/* ── CDP 세션 하나 (sse_cdp.mjs 와 같은 관용구) ───────────────────────────── */
function 세션(wsUrl) {
  const ws = new WebSocket(wsUrl);
  let seq = 0;
  const 대기중 = new Map();

  ws.addEventListener("message", (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && 대기중.has(msg.id)) {
      const { resolve, reject } = 대기중.get(msg.id);
      대기중.delete(msg.id);
      if (msg.error) { reject(new Error(JSON.stringify(msg.error))); }
      else { resolve(msg.result); }
    }
  });

  const 열림 = new Promise((res, rej) => {
    ws.addEventListener("open", res, { once: true });
    ws.addEventListener("error", rej, { once: true });
  });

  function send(method, params) {
    const id = ++seq;
    return new Promise((resolve, reject) => {
      대기중.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params: params || {} }));
    });
  }

  async function 평가(expr) {
    const r = await send("Runtime.evaluate", {
      expression: expr, returnByValue: true, awaitPromise: true,
    });
    if (r.exceptionDetails) {
      throw new Error("페이지 예외: " + JSON.stringify(r.exceptionDetails.exception));
    }
    return r.result.value;
  }

  return { ws, 열림, send, 평가, 닫기: () => ws.close() };
}

async function 새탭(url) {
  const r = await fetch(`http://127.0.0.1:${devport}/json/new?url=about:blank`,
    { method: "PUT" });
  const t = await r.json();
  const s = 세션(t.webSocketDebuggerUrl);
  await s.열림;
  await s.send("Page.enable");
  await s.send("Runtime.enable");
  await s.send("Page.navigate", { url });
  return { 세션: s, id: t.id };
}

/* 페이지에서 읽는 값들. **정답은 화면이 아니라 산출물 숫자**(인자로 받은 총장/배너)다 —
 * 검증 대상의 내부 상태를 정답으로 쓰면 같이 틀린다(board_cdp.mjs 와 같은 규율). */
const 읽기 = `
  (function () {
    function 셈(sel) { return document.querySelectorAll(sel).length; }
    var 스킵줄 = document.querySelector('article.ct-row[data-스킵="1"]');
    return {
      // 전장 수. 기준 확인 섹션의 같은 장(sample)은 빼고 센다.
      스트립: 셈('figure[data-slot="strip"]'),
      // 한글 data-* 속성 셀렉터가 실제로 먹는지 같이 본다 — 04-06 에서 한글
      // 경로 파라미터가 조용히 404 였던 전례가 있다. 둘이 다르면 그것도 사실이다.
      한글속성: 셈("figure[data-장순번]"),
      전체figure: 셈("figure"),
      기준섹션: 셈('figure[data-slot="sample"]'),
      스킵줄있나: !!스킵줄,
      스킵줄장수: 스킵줄 ? 스킵줄.querySelectorAll("figure").length : -1,
      스킵줄클릭가능: 스킵줄 ? 스킵줄.querySelectorAll("figure[hx-post]").length : -1,
      사람찍은장: 셈("figure.ct-human"),
      확인배지: 셈("span.ct-confirmed"),
      확인버튼: 셈("button.ct-confirm-btn"),
      오류배너: (function () {
        var b = document.getElementById("label-error");
        return (b && !b.hidden) ? (b.textContent || "").trim() : "";
      })()
    };
  })();
`;

/** 첫 번째 스트립 장을 누른다. 눌린 장의 `data-i` 를 돌려준다. */
const 장클릭 = `
  (function () {
    var f = document.querySelector('.ct-strip figure[data-slot="strip"][hx-post]');
    if (!f) { return null; }
    f.click();
    return f.getAttribute("data-i");
  })();
`;

const 확인클릭 = `
  (function () {
    var b = document.querySelector("button.ct-confirm-btn");
    if (!b) { return null; }
    b.click();
    return b.getAttribute("data-p");
  })();
`;

/** 조건이 참이 될 때까지 최대 ms 만큼 기다린다. htmx 왕복은 로컬이라 금방이다. */
async function 기다리기(세션, 조건, ms = 8000) {
  const 한계 = Date.now() + ms;
  let 값 = await 세션.평가(읽기);
  while (Date.now() < 한계 && !조건(값)) {
    await 잠깐(200);
    값 = await 세션.평가(읽기);
  }
  return 값;
}

async function main() {
  /* **토큰이 붙은 `/` 로 먼저 들어간다.** 서버가 303 으로 쿠키를 심고 깨끗한 주소로
     털어낸다 — 실제 사용자 동선과 같다(board_cdp.sh 주석). 검수 화면으로 바로 가면
     쿠키가 없어 403 이고, 그러면 figure 0 개를 "전장이 안 깔렸다" 로 오독하게 된다. */
  const 탭 = await 새탭(`${base}/?t=${encodeURIComponent(token)}`);
  await 잠깐(1500);
  await 탭.세션.send("Page.navigate", {
    url: `${base}/banner/review?run_dir=${encodeURIComponent(runDir)}`,
  });

  // 렌더를 기다린다. 전장이 아예 0이면 아래 단언들이 "왜" 를 말하지 못한다.
  let v = await 기다리기(탭.세션, (x) => x.전체figure > 0, 15000);
  if (v.전체figure === 0) {
    const 본문 = await 탭.세션.평가(
      "(document.body ? document.body.innerText : '').slice(0, 200)");
    console.error(`검수 화면에 figure 가 0개다. 화면 글자: ${JSON.stringify(본문)}`);
  }

  /* ── V-BANNER-00 — 정상 경로가 실제로 200 을 낸다 ────────────────────────
     이 줄이 없으면 썸네일이 통째로 깨진 서버에서도 아래 개수 단언이 전부 통과한다.
     04-06 의 한글 경로 파라미터 404 가 정확히 그 모양이었다. */
  const 썸상태 = await 탭.세션.평가(
    `fetch("/banner/thumb/${runDir}/0/0").then(function (r) { return r.status; })`);
  check("V-BANNER-00", "썸네일 정상 경로가 200 이다 (깨진 서버에서 초록이 나지 않게)",
    썸상태 === 200, `status ${썸상태}`);

  /* ── ① 전장 노출 (D-03a) ──────────────────────────────────────────────── */
  check("V-BANNER-01",
    "전장이 다 깔린다 (figure 수 == 산출물 집계.장)",
    v.스트립 === 총장 && 총장 !== 배너,
    v.스트립 === 총장
      ? `${v.스트립}장`
      : `전장 노출이 깨졌다 — figure ${v.스트립}개 / 산출물 장 ${총장}개. ` +
        `배너만 깔면 미탐을 구조적으로 못 본다(D-03a). (배너 ${배너}개)`);
  // 한글 data-* 셀렉터가 먹는지도 같이 본다. 기준 확인 섹션의 4장이 더해진 수와 같아야 한다.
  check("V-BANNER-01b",
    "한글 data-* 속성 셀렉터가 실제로 먹는다 (조용히 0을 세지 않는다)",
    v.한글속성 === v.스트립 + v.기준섹션 && v.한글속성 > 0,
    `data-장순번 ${v.한글속성} / strip ${v.스트립} + sample ${v.기준섹션}`);

  /* ── ② 스킵 상품도 전장을 깐다 (D-09) ─────────────────────────────────── */
  if (!v.스킵줄있나) {
    check("V-BANNER-02", "스킵 상품도 전장을 깐다", false,
      "픽스처에 스킵 상품이 없다 — 합성 산출물이 잘못 깔렸다");
  } else {
    check("V-BANNER-02",
      "스킵 상품도 전장을 깐다 (줄은 흐려지되 장은 그대로 · 클릭도 산다)",
      v.스킵줄장수 === 스킵장수 && v.스킵줄클릭가능 === 스킵장수,
      `스킵줄 figure ${v.스킵줄장수}/${스킵장수} · 클릭 가능 ${v.스킵줄클릭가능} ` +
      `(상품순번 ${스킵i})`);
  }

  /* ── ③ 장 클릭 — 화면 반영까지. DB 확인은 셸이 한다 ─────────────────── */
  const 누른순번 = await 탭.세션.평가(장클릭);
  if (누른순번 === null) {
    console.log("CLICK-LABEL none");
    check("V-BANNER-03-화면", "장을 누를 수 있다", false, "클릭 가능한 장이 없다");
  } else {
    v = await 기다리기(탭.세션, (x) => x.사람찍은장 >= 1 || x.오류배너);
    console.log(`CLICK-LABEL ${누른순번}`);
    check("V-BANNER-03-화면",
      "클릭한 장이 사람 판정으로 바뀐다 (서버 조각이 교체됐다는 뜻)",
      v.사람찍은장 === 1 && !v.오류배너,
      `사람찍은장 ${v.사람찍은장}${v.오류배너 ? " · 오류 " + v.오류배너 : ""}`);
  }

  /* ── ④ 확인함 — 라벨과 섞이지 않는다 ─────────────────────────────────── */
  const 누른상품 = await 탭.세션.평가(확인클릭);
  if (누른상품 === null) {
    console.log("CLICK-CONFIRM none");
    check("V-BANNER-04-화면", "확인함을 누를 수 있다", false, "확인 버튼이 없다");
  } else {
    v = await 기다리기(탭.세션, (x) => x.확인배지 >= 1 || x.오류배너);
    console.log(`CLICK-CONFIRM ${누른상품}`);
    check("V-BANNER-04-화면",
      "확인함이 배지로 바뀐다 (라벨 테두리는 그대로)",
      v.확인배지 >= 1 && v.사람찍은장 === 1 && !v.오류배너,
      `확인배지 ${v.확인배지} · 사람찍은장 ${v.사람찍은장}` +
      `${v.오류배너 ? " · 오류 " + v.오류배너 : ""}`);
  }

  탭.세션.닫기();
}

main()
  .then(() => {
    console.log("----");
    console.log(실패 === 0
      ? "배너 CDP 화면 검증 PASS — DB 확인은 셸이 이어서 한다"
      : "FAIL 이 있다 — 여기서 멈춰라");
    process.exit(실패);
  })
  .catch((e) => {
    console.error("검증 중 오류:", e.message);
    process.exit(2);
  });
