// Aside REPL 드라이버 — 네이버 가격비교에서 카테고리 경로 + 확신도를 뽑는다.
// aside_category.py 가 __ITEMS__ / __OPTS__ 를 치환해 `aside repl` 로 실행한다.
// 단독 실행용이 아니다.
//
// 파일을 안 쓰는 이유: REPL 의 fs 는 세션 루트 밖을 막고, 그 세션 디렉터리는 CLI 가
// 끝나면 지워진다. 그래서 입력은 코드에 박고, 결과는 건마다 stdout 으로 흘린다
// (`__R__ {json}`). 중간에 죽어도 거기까지는 파이썬이 건진다.

const ITEMS = __ITEMS__;
const OPTS = __OPTS__;

// ── 캡챠 정착 대기 (2026-08-18 실측) ──────────────────────────────────────────
// 네이버 '보안 확인을 완료해 주세요' 화면은 **스스로 통과되는 중간 화면**일 때가 있다.
// 같은 URL 을 시점별로 찍은 실측: 1.2초엔 캡챠 입력창 2개(rcpt_answer/vcpt_answer),
// 5.2초엔 캡챠 흔적 0개 + 정상 검색결과. goto 직후 한 번만 보고 끊으면 멀쩡한 조회가
// 전건 `캡챠감지` 로 죽는다(1-3 그룹에서 15건이 이틀 동안 이것 때문에 못 넘어갔다).
// 그래서 캡챠로 보이면 즉시 중단하지 않고 아래 동안 다시 본다.
// 진짜 캡챠는 사람이 풀기 전엔 안 사라지므로 이 대기로 오판이 생기지 않는다.
const CAPTCHA_SETTLE_TRIES = 5;
const CAPTCHA_SETTLE_MS = 2000;   // 최대 10초 추가 대기

// ── 확장 패널(shadow DOM) 에서 '추출된 카테고리' 블록 텍스트를 꺼낸다 ────────────
// 불사자 확장은 Plasmo(PLASMO-CSUI) 라 shadow root 안에 있다. document.body.innerText
// 로는 절대 안 잡힌다 — shadow root 를 직접 훑어야 한다.
const PANEL = () => {
  const roots = [document];
  const walk = (root, d) => {
    if (d > 8) return;
    for (const el of root.querySelectorAll("*")) {
      if (el.shadowRoot) { roots.push(el.shadowRoot); walk(el.shadowRoot, d + 1); }
    }
  };
  walk(document, 0);
  for (const r of roots) {
    for (const el of r.querySelectorAll("*")) {
      if (el.children.length === 0 && (el.textContent || "").trim() === "추출된 카테고리") {
        let p = el;
        for (let i = 0; i < 4 && p.parentElement; i++) p = p.parentElement;
        return (p.innerText || "").replace(/\n+/g, "|");
      }
    }
  }
  return null;
};

// ── 페이지 상태 판정 ──────────────────────────────────────────────────────────
// 캡챠를 '정상'으로 흘리면 뒤에서 패널을 못 찾아 '파싱실패(확장 미검출)' 로 뭉개진다.
// 그러면 원인이 캡챠인데 확장·로그인을 뒤지게 되므로 별도 상태로 뺀다.
const PAGESTATE = () => {
  const t = document.body.innerText || "";
  const u = location.href;
  if (/자동입력 방지|보안문자|캡차|captcha/i.test(t) || /captcha/i.test(u)) return "캡챠";
  // ★ 실물 캡챠(2026-08-04 실측)는 '보안 확인을 완료해 주세요' 영수증 퀴즈형이라 본문에 captcha
  // 문자열이 없다. 위 텍스트 조건은 안 걸리고 아래 셀렉터만 잡았다 — 지우면 캡챠가 파싱실패로 뭉개진다.
  if (document.querySelector('img[src*="captcha" i], input[id*="captcha" i], input[name*="captcha" i]')) return "캡챠";
  if (/일시적으로 제한|접속이 제한|비정상적인 접근|비정상적인 검색/.test(t)) return "차단";
  if (/검색결과가 없습니다|검색 결과가 없습니다|와 일치하는 상품이 없습니다/.test(t)) return "없음";
  return "정상";
};

// ── 1페이지 상품들의 카테고리 분포 집계 ────────────────────────────────────────
// 셀하 확신도와 같은 정의: 최빈 카테고리 상품수 / 전체 상품수.
// 상품 행의 카테고리는 '대분류>중분류>...' 처럼 공백 없이 붙어 나온다.
// 확장 패널의 'N순위 대분류 > 중분류' 는 공백이 있고 '순위'가 붙어 있어 함께 걸러진다.
const tally = (tree) => {
  const re = /text:\s*"([^"\n]*)"/g;
  const cnt = {};
  let m, total = 0;
  while ((m = re.exec(tree)) !== null) {
    const s = m[1];
    if (/순위/.test(s)) continue;
    const mm = s.match(/([가-힣][^\s">]{1,20}(?:>[^\s">]{1,25}){1,4})/);
    if (!mm) continue;
    cnt[mm[1]] = (cnt[mm[1]] || 0) + 1;
    total++;
  }
  return { total, top: Object.entries(cnt).sort((a, b) => b[1] - a[1]) };
};

// ── 패널 텍스트 → 순위별 경로 ────────────────────────────────────────────────
// 형태: ...|추출된 카테고리|1순위|경로|#코드|복사|2순위|경로|복사|...
// #코드는 1순위에만 붙는다(실측).
function parsePanel(txt) {
  const parts = txt.split("|").map((s) => s.trim()).filter(Boolean);
  const at = parts.findIndex((s) => s === "추출된 카테고리");
  if (at < 0) return { ranks: [], code: null };
  const ranks = [];
  let code = null;
  for (let i = at + 1; i < parts.length; i++) {
    if (/^\d+순위$/.test(parts[i])) {
      const path = (parts[i + 1] || "").trim();
      if (path.includes(">")) ranks.push(path.replace(/\s*>\s*/g, " > "));
    } else if (/^#\d+$/.test(parts[i]) && code === null) {
      code = parts[i].slice(1);
    }
  }
  return { ranks, code };
}

const rand = (a, b) => a + Math.random() * (b - a);

// ── 본체 ─────────────────────────────────────────────────────────────────────
const items = ITEMS;
const emit = (r) => console.log("__R__ " + JSON.stringify(r));

await openTab("https://search.shopping.naver.com/");

for (let i = 0; i < items.length; i++) {
  const it = items[i];
  const kw = (it.name || "").trim();
  const url = "https://search.shopping.naver.com/search/all?query=" + encodeURIComponent(kw);
  const r = {
    검색어: kw, productId: it.productId || null,
    카테고리경로: null, 최종차수: null, 확신도: null, 카테고리코드: null,
    후보목록: [], 표본수: null, 마켓: "네이버", url, 상태: null, error: null,
  };

  if (!kw) {
    r.상태 = "파싱실패"; r.error = "상품명 없음";
    emit(r); continue;
  }

  try {
    await page.goto(url);
    await sleep(1200);

    // 차단·캡챠는 계속 두드릴수록 악화된다. 남은 건은 손대지 않고 즉시 멈춘다.
    // 단, 캡챠는 스스로 통과되는 중간 화면일 수 있어 정착을 기다린다(위 상수 주석).
    let st0 = await page.evaluate(PAGESTATE);
    if (st0 === "캡챠") {
      for (let k = 0; k < CAPTCHA_SETTLE_TRIES; k++) {
        await sleep(CAPTCHA_SETTLE_MS);
        st0 = await page.evaluate(PAGESTATE);
        if (st0 !== "캡챠") break;
      }
    }
    if (st0 === "차단" || st0 === "캡챠") {
      r.상태 = st0 === "캡챠" ? "캡챠감지" : "차단감지";
      r.error = st0 === "캡챠"
        ? "네이버 캡챠 — Aside 창에서 직접 풀어야 한다"
        : "네이버 접속 제한";
      emit(r);
      console.log(`[${i + 1}/${items.length}] ${kw} → ${r.상태} · 중단 (남은 ${items.length - i - 1}건 미조회)`);
      break;
    }

    // 패널이 그려질 때까지 대기. 직전 키워드 잔상 방어 = 패널에 박힌 키워드 대조.
    let txt = null;
    for (let k = 0; k < OPTS.panelTries; k++) {
      txt = await page.evaluate(PANEL);
      if (txt && txt.includes("‘" + kw + "’")) break;
      txt = null;
      await sleep(500);
    }

    if (!txt) {
      // 패널 대기 도중에 캡챠·차단으로 넘어갔을 수 있으므로 다시 본다.
      const st = await page.evaluate(PAGESTATE);
      if (st === "없음") { r.상태 = "조회실패"; r.error = "검색 결과 없음"; }
      else if (st === "캡챠") { r.상태 = "캡챠감지"; r.error = "네이버 캡챠 — Aside 창에서 직접 풀어야 한다"; }
      else if (st === "차단") { r.상태 = "차단감지"; r.error = "네이버 접속 제한"; }
      else { r.상태 = "파싱실패"; r.error = "확장 패널 미검출 — 불사자 확장/네이버 로그인 점검"; }
      emit(r);
      console.log(`[${i + 1}/${items.length}] ${kw} → ${r.상태} (${r.error})`);
      if (r.상태 === "캡챠감지" || r.상태 === "차단감지") {
        console.log(`  ↳ 중단 (남은 ${items.length - i - 1}건 미조회)`);
        break;
      }
      continue;
    }

    const { ranks, code } = parsePanel(txt);
    if (!ranks.length) {
      r.상태 = "파싱실패"; r.error = "추출된 카테고리 블록에 순위 없음";
      emit(r); continue;
    }

    r.카테고리경로 = ranks[0];
    r.최종차수 = ranks[0].split(">").pop().trim();
    r.카테고리코드 = code;
    r.후보목록 = ranks;

    // 확신도 = 1페이지 상품 카테고리 몰림 비율. 지연 로딩이라 스크롤로 다 채운 뒤 센다.
    if (OPTS.count) {
      let last = 0;
      for (let k = 0; k < OPTS.scrollRounds; k++) {
        await page.keyboard.press("End");
        await sleep(OPTS.scrollWait);
        const t = tally((await snapshot(page)).tree);
        if (t.total === last && k > 2) break;
        last = t.total;
      }
      const t = tally((await snapshot(page)).tree);
      if (t.total) {
        r.표본수 = t.total;
        // 최빈 카테고리가 아니라 '1순위 경로'의 점유율을 쓴다. 확장 1순위와 실측 최빈이
        // 어긋나면 그 사실 자체가 신호이므로 임의로 맞추지 않는다.
        const norm = (s) => s.replace(/\s*>\s*/g, ">").trim();
        const hit = t.top.find(([c]) => norm(c) === norm(ranks[0]));
        const n = hit ? hit[1] : 0;
        r.확신도 = ((n / t.total) * 100).toFixed(1);
        if (!hit) r.error = `1순위 경로가 1페이지 표본에 없음(최빈: ${t.top[0] ? t.top[0][0] : "-"})`;
      }
    }

    r.상태 = "성공";
    emit(r);
    console.log(
      `[${i + 1}/${items.length}] ${kw} → ${r.카테고리경로}` +
      (r.확신도 !== null ? `  (${r.확신도}% / ${r.표본수}건)` : "") +
      (ranks.length > 1 ? `  [후보 ${ranks.length}]` : "")
    );
  } catch (e) {
    r.상태 = "파싱실패"; r.error = String(e && e.message ? e.message : e);
    emit(r);
    console.log(`[${i + 1}/${items.length}] ${kw} → 예외: ${r.error}`);
  }

  if (i < items.length - 1) await sleep(rand(OPTS.sleep, OPTS.sleepMax) * 1000);
}

console.log("__DONE__");
