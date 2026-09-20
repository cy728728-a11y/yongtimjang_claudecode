/* 상품 보드 — Tabulator 6.5.3 초기화.
 *
 * 서버가 <script type="application/json" id="board-rows"> 에 넣어 준 데이터를
 * JSON.parse 로 읽는다. 여기서 데이터를 다시 만들거나 계산하지 않는다 —
 * 입찰가·판정값의 정본은 CLI 산출물이고, 화면이 그걸 다시 계산하면 진실이 둘이 된다.
 *
 * 클라이언트 사이드 정렬·필터·검색만 쓴다. 서버사이드 페이징(filterMode/sortMode:"remote")
 * 을 켜지 마라 — 2,637행은 Tabulator 클라이언트 사이드 한계(약 5,000행) 안이고,
 * 켜는 순간 필터 조작마다 서버 왕복이 생겨 즉시 반응이 사라진다(Out of Scope).
 *
 * 선택(체크박스) 컬럼은 Plan 01-07 이 "보이는 것만 vs 필터 전체"(BOARD-03/D-07)
 * 확인 배너와 **같이** 붙였다. 둘은 한 쌍이다 — 체크박스만 먼저 넣으면 확인 없는
 * 전체 선택이 생긴다.
 *
 * **건수 타이핑 확인 입력칸을 만들지 마라** (FLOW-04 / D-07). 입찰가 인상은
 * 되돌릴 수 있는 작업이라 배너 한 번이면 충분하다. 글자를 받아 대조하는 확인은
 * Phase 2 의 **삭제** 버튼 몫이다 — 삭제는 되돌릴 수 없다. 되돌릴 수 있는 것과
 * 없는 것에 같은 마찰을 걸면 사람이 양쪽 다 기계적으로 통과시킨다.
 *
 * 계정 alias 를 이 파일에 박지 마라 — 계정은 설정에 항목을 더하는 것만으로 늘어난다.
 * 필터 옵션은 서버가 그린 <select> 에서만 온다 (BOARD-02).
 */
(function () {
  "use strict";

  var 판 = document.getElementById("board");
  var 원본 = document.getElementById("board-rows");
  if (!판 || !원본) { return; }

  var rows;
  try {
    rows = JSON.parse(원본.textContent || "[]");
  } catch (e) {
    판.textContent = "보드 데이터를 못 읽었다: " + e;
    return;
  }

  // Tabulator 의 index 는 필드명 하나만 받는다. 접기 키가 (계정, 상품) 이므로
  // 합친 키를 여기서 만들어 준다 — 계정이 다른 같은 상품이 두 줄로 남아야 한다(D-05).
  rows.forEach(function (r) {
    r.key = r.acct + "|" + r.mallProductId;
  });

  // ── formatter ─────────────────────────────────────────────────────────────
  // 값이 없는 칸은 **빈칸**이다. ①·⑥ 행에는 imp/clk/ctr/cost 키가 아예 없어서
  // (7일 통계에 행이 없는 것이 그 규칙의 정의다) 접힌 줄의 값이 null 로 온다.
  // 여기서 방어하지 않으면 실데이터 2,261줄에 undefined / NaN 이 찍힌다.
  // 0 으로 대체하지도 않는다 — "노출 0 이었다" 는 판정처럼 보이는데, 실제로는
  // 숫자가 존재하지 않는다.
  function 빈칸이면(v) { return v === null || v === void 0 || v === ""; }

  function 정수(cell) {
    var v = cell.getValue();
    if (빈칸이면(v)) { return ""; }
    return Number(v).toLocaleString("ko-KR");
  }

  function 비율(cell) {
    var v = cell.getValue();
    if (빈칸이면(v)) { return ""; }
    return Number(v).toFixed(2);
  }

  function 예아니오(cell) {
    var v = cell.getValue();
    // **bool 을 먼저 분기한다.** 파이썬에서 bool 은 int 의 하위 타입이라 순서를
    // 바꾸면 1/0 으로 찍혀 사람이 못 읽는다(report_md.py:17-40 의 함정).
    // JS 로 넘어와도 같은 실수를 하지 마라 — true 를 숫자 서식에 태우면 1 이 된다.
    if (typeof v === "boolean") { return v ? "예" : "아니오"; }
    if (빈칸이면(v)) { return ""; }
    return String(v);
  }

  // 숫자 정렬에서 빈칸은 항상 아래로. 안 그러면 노출 내림차순 첫 페이지가
  // 통계 없는 ① 행으로 덮인다.
  var 빈칸아래 = { alignEmptyValues: "bottom" };

  // 컬럼 정의를 **데이터 구조로** 둔다 (sheets_out.py:28-48 의 COLS 관례).
  // 규칙마다 있는 필드가 다르다는 사실이 이 표에 그대로 드러나야, ①의 빈칸이
  // 버그가 아니라 설계상 정상값이라는 게 읽는 사람에게 보인다.
  //
  // 폭 배분에 대해: 상품명은 이 저장소의 Core Value 가 걸린 열이라 제일 넓게 가져간다.
  // 그래도 한국어 상품명은 60자를 넘는 게 보통이라 어떤 폭을 줘도 잘린다(실측 38/40).
  // 줄바꿈(variableHeight)으로 다 보여주는 선택지는 **버렸다** — 2,637행 보드에서
  // 행 높이가 2~3배가 되면 한 화면에 7~8줄밖에 안 들어와 훑는 용도가 죽는다.
  // 대신 `tooltip: true` 로 hover 시 전문을 띄우고, 숫자 열의 군더더기 폭을 깎아
  // 가로 스크롤을 없앴다(실측 1,520 → 컨테이너 안). 상품명 전문이 상시 필요해지는 건
  // 상세페이지 판정(Phase 3)이고, 그때는 목록이 아니라 상세 패널이 맡을 일이다.
  var columns = [
    // 선택 체크박스. **`titleFormatterParams.rowRange` 를 비워 두지 마라** —
    // 헤더 체크박스 핸들러는 `table.selectRow(params.rowRange)` 를 부르고,
    // `selectRows(undefined)` 는 `rowManager.rows`, 즉 **필터를 무시한 전체 행**을
    // 고른다(벤더 소스 실측: `case "undefined": t=this.table.rowManager.rows`).
    // 계정을 하나로 좁혀 놓고 헤더를 누르면 화면엔 그 계정만 보이는데 실제로는
    // 다른 계정까지 전부 선택된다 — 화면상 증상이 전혀 없고, 고른 적 없는 소재의
    // 입찰가가 올라간다. "visible" 은 **지금 뷰포트에 그려진 행**이다(D-07 의 '보이는 것').
    // 필터 통과 전체는 아래 `필터 전체 N건 선택` 배너가 따로 맡는다.
    { title: "", width: 40, hozAlign: "center", headerSort: false,
      formatter: "rowSelection", titleFormatter: "rowSelection",
      titleFormatterParams: { rowRange: "visible" },
      cellClick: function (e, cell) { cell.getRow().toggleSelect(); } },
    { title: "계정", field: "acct", width: 95 },
    { title: "규칙", field: "rules", width: 85 },
    { title: "상품명", field: "title", minWidth: 200, widthGrow: 5, tooltip: true },
    { title: "노출", field: "imp", hozAlign: "right", width: 90,
      sorter: "number", sorterParams: 빈칸아래, formatter: 정수 },
    { title: "클릭", field: "clk", hozAlign: "right", width: 80,
      sorter: "number", sorterParams: 빈칸아래, formatter: 정수 },
    { title: "CTR %", field: "ctr", hozAlign: "right", width: 85,
      sorter: "number", sorterParams: 빈칸아래, formatter: 비율 },
    { title: "구매완료", field: "purCnt", hozAlign: "right", width: 90,
      sorter: "number", sorterParams: 빈칸아래, formatter: 정수 },
    { title: "구매금액", field: "purAmt", hozAlign: "right", width: 95,
      sorter: "number", sorterParams: 빈칸아래, formatter: 정수 },
    // `cost` 는 **광고비**다. 원본 필드가 salesAmt 라서 헷갈리기 쉬운데
    // 광고에 쓴 돈이지 벌어들인 돈이 아니다 (ads_rules._with_stat:50 주석).
    { title: "광고비", field: "cost", hozAlign: "right", width: 95,
      sorter: "number", sorterParams: 빈칸아래, formatter: 정수 },
    { title: "현재입찰", field: "bid", hozAlign: "right", width: 90,
      sorter: "number", sorterParams: 빈칸아래, formatter: 정수 },
    { title: "그룹입찰따름", field: "useGroupBid", hozAlign: "center", width: 110,
      formatter: 예아니오 },
    { title: "①소재수", field: "rule1_count", hozAlign: "right", width: 90,
      sorter: "number", sorterParams: 빈칸아래, formatter: 정수 },
    { title: "상품ID", field: "mallProductId", width: 105, tooltip: true }
  ];

  var table = new Tabulator("#board", {
    data: rows,
    columns: columns,
    index: "key",
    layout: "fitColumns",
    // 높이를 고정해야 가상 DOM 이 켜진다. 안 켜지면 2,637행을 전부 그리느라 멈춘다.
    height: "60vh",
    placeholder: "조건에 맞는 상품이 없다",
    // 행 선택을 켠다. **기본값은 "highlight" 라 선택 자체가 안 된다** — 이 한 줄이
    // 없으면 체크박스 컬럼이 그려지긴 해도 눌러도 아무 일이 없다(증상이 조용하다).
    // 숫자(상한)를 주지 않는다: 상한은 화면이 아니라 서버 `flow.check_limits` 가
    // 설정값으로 건다(D-08). 여기 숫자를 박으면 설정을 고쳐도 화면이 안 따라온다.
    selectableRows: true,
    // 기본 정렬: 규칙 → 노출 내림차순. 배열의 첫 항목이 1차 정렬키다.
    initialSort: [
      { column: "rules", dir: "asc" },
      { column: "imp", dir: "desc" }
    ]
  });

  // ── 필터 ──────────────────────────────────────────────────────────────────
  var 계정칸 = document.getElementById("f-acct");
  var 규칙칸 = document.getElementById("f-rule");
  var 검색칸 = document.getElementById("f-title");
  var 초기화 = document.getElementById("f-reset");
  var 건수 = document.getElementById("board-count");

  function 고른값(sel) {
    if (!sel) { return []; }
    return Array.prototype.filter.call(sel.options, function (o) { return o.selected; })
      .map(function (o) { return o.value; });
  }

  function 필터적용() {
    var 계정 = 고른값(계정칸);
    var 규칙 = 고른값(규칙칸);
    var 말 = (검색칸 && 검색칸.value ? 검색칸.value : "").trim().toLowerCase();

    // 세 조건을 함수 하나로 합친다. 필터를 따로 걸면 해제 순서에 따라
    // 하나가 남아 "왜 안 보이지" 가 된다.
    table.setFilter(function (d) {
      if (계정.length && 계정.indexOf(d.acct) === -1) { return false; }
      if (규칙.length) {
        var 걸림 = 규칙.some(function (기호) {
          return (d.rules || "").indexOf(기호) !== -1;
        });
        if (!걸림) { return false; }
      }
      if (말) {
        var t = (d.title || "").toLowerCase();
        if (t.indexOf(말) === -1) { return false; }   // like 매칭
      }
      return true;
    });
  }

  [계정칸, 규칙칸].forEach(function (el) {
    if (el) { el.addEventListener("change", 필터적용); }
  });
  if (검색칸) { 검색칸.addEventListener("input", 필터적용); }
  if (초기화) {
    초기화.addEventListener("click", function () {
      [계정칸, 규칙칸].forEach(function (sel) {
        if (!sel) { return; }
        Array.prototype.forEach.call(sel.options, function (o) { o.selected = false; });
      });
      if (검색칸) { 검색칸.value = ""; }
      필터적용();
    });
  }

  // 보이는 줄 수를 항상 띄운다. 이 숫자가 Plan 01-07 의 "보이는 선택 vs 필터 전체"
  // 배너가 올라탈 자리다 — 지금부터 사람이 그 수를 눈으로 익혀 둬야 한다.
  //
  // **`dataFiltered` 안에서 `table.getDataCount("active")` 를 읽지 마라.**
  // Tabulator 의 `Filter.filter()` 는 필터링 결과를 만든 뒤 **먼저 이 이벤트를 쏘고,
  // 그 다음에** 호출자(RowManager.refreshActiveData)가 `activeRows` 를 갈아끼운다.
  // 그래서 핸들러 시점의 `activeRows` 는 아직 **직전 필터의 집합**이고, 배지가
  // 정확히 한 스텝 뒤처진다: 전체 2,637 에서 계정 하나를 걸어도 2,637 이 남고,
  // 다음 계정으로 바꿔야 그제야 앞 계정의 수가 뜬다.
  // 육안으론 안 잡힌다 — 숫자가 *움직이긴* 하기 때문이다. 두 번 연속 바꿔
  // 직전 값과 대조해야만 드러난다 (webapp/tests/board_cdp.sh 가 그걸 기계로 한다).
  //
  // 이벤트가 2번째 인자로 갓 계산된 행 목록을 넘겨주는 이유가 바로 이것이다.
  // 그 값만 믿는다 — 커밋 안 된 내부 상태를 뒤지지 않는다.
  function 건수표시(n) {
    if (!건수) { return; }
    건수.textContent = Number(n).toLocaleString("ko-KR");
  }
  table.on("dataFiltered", function (filters, 걸린행) {
    건수표시(걸린행 ? 걸린행.length : 0);
  });
  // 최초 1회. 이 시점엔 필터가 진행 중이 아니라 activeRows 가 이미 확정돼 있다.
  table.on("tableBuilt", function () {
    건수표시(table.getDataCount("active"));
  });

  // ── 선택 → 대상 (BOARD-03 / BOARD-04 / D-06 / D-07) ───────────────────────
  //
  // 두 수를 **갈라서** 보여주는 게 이 블록의 전부다:
  //   · `table.getSelectedData()` — 지금 실제로 고른 행
  //   · `table.getData("active")` — 지금 필터를 통과한 전체(페이지 무관)
  // 둘이 다를 때 D-07 이 발동한다. 헤더 체크박스는 뷰포트에 그려진 행만 잡으므로
  // ①행 1,195건짜리 계정에서는 이 둘이 반드시 다른 수가 된다(BOARD-03).
  //
  // 숫자를 여기서 **만들지 않는다.** `rule1_count`·`rule1_ads` 는 서버(`board.fold_products`)가
  // 이미 접어서 넘긴 값이고, 예상 인상액 합계는 CLI 산출물에서 서버가 낸다
  // (`flow.raise_total`). 화면은 더하기만 한다 — 입찰가 산술은 한 줄도 없다(T-1-07).
  var 요약칸 = document.getElementById("sel-summary");
  var 전체링크칸 = document.getElementById("sel-all-wrap");
  var 전체링크 = document.getElementById("sel-all");
  var 전체수칸 = document.getElementById("sel-all-n");
  var 배너 = document.getElementById("sel-banner");
  var 배너말 = document.getElementById("sel-banner-msg");
  var 배너확인 = document.getElementById("sel-banner-ok");
  var 배너취소 = document.getElementById("sel-banner-cancel");
  var 미리보기버튼 = document.getElementById("preview-btn");
  var 회차칸값 = document.getElementById("job-run-dir");
  var 작업오류 = document.getElementById("job-error");

  function 콤마(n) { return Number(n).toLocaleString("ko-KR"); }

  /** 행 목록의 ①소재 수 합. 대상 정의는 규칙①뿐이다 (D-06 / BID-01). */
  function 대상수(행들) {
    var n = 0;
    행들.forEach(function (r) { n += (r.rule1_count || 0); });
    return n;
  }

  /**
   * 선택 요약을 다시 그린다.
   *
   * **`활성데이터` 인자가 있는 이유가 이 파일의 제일 비싼 교훈이다.**
   * `dataFiltered` 핸들러 안에서 `table.getData("active")` 를 읽으면 **직전 필터의
   * 집합**이 나온다 — Tabulator 의 `Filter.filter()` 가 결과를 만든 뒤 먼저 이벤트를
   * 쏘고, 그 다음에 `RowManager` 가 `activeRows` 를 갈아끼우기 때문이다(건수 배지가
   * 같은 이유로 01-04 에서 한 스텝 뒤처졌다).
   *
   * 여기서 그 랙이 나면 증상이 더 고약하다: 계정을 바꿔도 "필터 밖에 89개 골라 뒀다"
   * 가 **안 뜬다.** 화면엔 새 계정만 보이는데 선택은 옛 계정에 남아 있는 상태가
   * 조용히 유지된다. 그래서 이벤트가 넘겨주는 **갓 계산된 행 목록만** 믿는다.
   * (2026-09-20 preview_cdp.sh 의 V-PRE-07 이 실제로 이걸 잡았다.)
   */
  function 요약갱신(활성데이터) {
    if (!요약칸) { return; }
    var 고른것 = table.getSelectedData();
    var 활성 = 활성데이터 || table.getData("active");
    var 대상 = 대상수(고른것);
    var 규칙1있는상품 = 고른것.filter(function (r) { return (r.rule1_count || 0) > 0; }).length;

    // 필터를 바꿔도 선택은 남는다(Tabulator 기본 selectableRowsPersistence).
    // 그래서 "지금 화면 밖에 고른 게 몇 개 있다" 를 **반드시 말해야** 한다 —
    // 안 말하면 계정을 바꿔 놓고 미리보기를 눌러 안 보이던 계정의 소재가 딸려간다.
    // 저장소 관례: 스킵도 은폐도 조용히 하지 않는다.
    var 활성키 = {};
    활성.forEach(function (r) { 활성키[r.key] = 1; });
    var 필터밖 = 고른것.filter(function (r) { return !활성키[r.key]; }).length;

    var 말 = "상품 " + 콤마(고른것.length) + "개 선택";
    if (고른것.length && 규칙1있는상품 !== 고른것.length) {
      말 += " · 그중 규칙① 소재가 있는 건 " + 콤마(규칙1있는상품) + "개";
    }
    말 += " · 대상 " + 콤마(대상) + "건";
    if (필터밖) { 말 += " · 그중 " + 콤마(필터밖) + "개는 지금 필터 밖이다"; }
    if (!고른것.length) { 말 += " — 먼저 상품을 골라라"; }
    else if (!대상) { 말 += " — 고른 상품에 규칙① 소재가 없다(②③⑤ 소재는 인상 대상이 아니다)"; }
    요약칸.textContent = 말;

    if (미리보기버튼) { 미리보기버튼.disabled = 고른것.length === 0; }

    // "필터 전체 N건 선택" 은 **더 고를 게 남았을 때만** 띄운다.
    if (전체링크칸) {
      var 더있나 = 활성.length > 고른것.length;
      전체링크칸.hidden = !더있나;
      if (더있나 && 전체수칸) { 전체수칸.textContent = 콤마(활성.length); }
    }
  }

  // **핸들러를 그대로 넘기지 마라.** `rowSelectionChanged` 의 첫 인자는 *선택된*
  // 데이터라, 그걸 `활성데이터` 자리에 받으면 "필터 통과 전체" 가 "지금 고른 것" 이
  // 되어 `필터 전체 N건` 이 항상 선택 수와 같아진다 — 링크가 영영 안 뜬다.
  table.on("rowSelectionChanged", function () { 요약갱신(); });
  table.on("dataFiltered", function (filters, 걸린행) {
    배너닫기();
    요약갱신((걸린행 || []).map(function (r) { return r.getData(); }));
  });
  table.on("tableBuilt", function () { 요약갱신(); });

  function 배너닫기() { if (배너) { 배너.hidden = true; } }

  // 필터 전체 선택은 **배너를 한 번 더 거친다** (D-07 / FLOW-04 / T-1-29).
  // 취소하면 선택이 안 넘어간다 — 배너를 띄우는 시점에 아무것도 고르지 않는다.
  if (전체링크) {
    전체링크.addEventListener("click", function () {
      var 활성 = table.getData("active");
      if (!배너 || !배너말) { return; }
      배너말.textContent =
        "지금 필터를 통과한 상품 " + 콤마(활성.length) + "개 전부를 고른다 — 대상 소재 "
        + 콤마(대상수(활성)) + "건. 진행할래?";
      배너.hidden = false;
    });
  }
  if (배너취소) { 배너취소.addEventListener("click", 배너닫기); }
  if (배너확인) {
    배너확인.addEventListener("click", function () {
      배너닫기();
      // 행 객체를 통째로 넘긴다 — 한 번에 넘겨야 선택 변경 이벤트가 한 번만 돈다.
      table.selectRow(table.getRows("active"));
      요약갱신();
    });
  }

  // ── 미리보기 접수 ─────────────────────────────────────────────────────────
  //
  // **`fetch` 에는 토큰이 자동으로 안 붙는다.** `<body hx-headers>` 는 htmx 가 보내는
  // 요청에만 헤더를 얹는다. 여기서 헤더를 빠뜨리면 `security.guard` 가 403 을 주고,
  // 증상은 "버튼을 눌러도 아무 일이 없다" 로만 보인다. 토큰의 출처를 두 곳으로
  // 늘리지 않으려고 body 속성에서 **읽어 온다** — 템플릿에 또 박지 않는다.
  function 토큰() {
    try { return JSON.parse(document.body.getAttribute("hx-headers"))["X-CT-Token"]; }
    catch (e) { return ""; }
  }

  function 오류표시(말) {
    if (!작업오류) { return; }
    작업오류.textContent = 말;
    작업오류.hidden = false;
  }

  /** 작업이 끝날 때까지 상태를 물어본 뒤 결과 표를 갈아끼운다. */
  function 결과기다리기(job_id, 남은) {
    fetch("/jobs/" + encodeURIComponent(job_id), { headers: { "Accept": "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.status === "running" && 남은 > 0) {
          setTimeout(function () { 결과기다리기(job_id, 남은 - 1); }, 400);
          return;
        }
        var 자리 = document.getElementById("preview");
        if (자리) { 자리.hidden = false; }
        // htmx 로 갈아끼운다 — 서버가 만든 조각을 그대로 쓴다(표를 JS 로 짓지 않는다).
        htmx.ajax("GET", "/jobs/" + encodeURIComponent(job_id) + "/result",
                  { target: "#preview-body", swap: "innerHTML" });
      })
      .catch(function (e) { 오류표시("작업 상태를 못 읽었다: " + e); });
  }

  if (미리보기버튼) {
    미리보기버튼.addEventListener("click", function () {
      var 고른것 = table.getSelectedData();
      var ids = [];
      고른것.forEach(function (r) {
        (r.rule1_ads || []).forEach(function (a) { ids.push(a); });
      });
      if (작업오류) { 작업오류.hidden = true; }
      미리보기버튼.disabled = true;

      fetch("/jobs/bids/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CT-Token": 토큰() },
        body: JSON.stringify({
          run_dir: 회차칸값 ? 회차칸값.value : "",
          ad_ids: ids
        })
      }).then(function (r) {
        return r.text().then(function (본문) { return { ok: r.ok, code: r.status, 본문: 본문 }; });
      }).then(function (res) {
        미리보기버튼.disabled = false;
        if (!res.ok) {
          // 사유를 그대로 보여준다. 400 은 상한 초과·대상 오염처럼 **사람이 읽어야 하는**
          // 거부고, 409 는 "지금은 안 된다" 다. 숫자만 띄우면 둘을 구분 못 한다.
          var 사유 = res.본문;
          try { 사유 = JSON.parse(res.본문).detail || res.본문; } catch (e) { /* 원문 그대로 */ }
          오류표시("미리보기를 못 만들었다 (" + res.code + ") — " + 사유);
          return;
        }
        var job_id = JSON.parse(res.본문).job_id;
        htmx.ajax("GET", "/jobs/" + encodeURIComponent(job_id) + "/panel",
                  { target: "#job-panel", swap: "outerHTML" });
        결과기다리기(job_id, 150);
      }).catch(function (e) {
        미리보기버튼.disabled = false;
        오류표시("미리보기 요청이 실패했다: " + e);
      });
    });
  }

  // 회차 드롭다운은 고르는 즉시 이동한다. GET 폼이라 서버 상태를 바꾸지 않는다.
  var 회차칸 = document.getElementById("rundir-select");
  if (회차칸 && 회차칸.form) {
    회차칸.addEventListener("change", function () { 회차칸.form.submit(); });
  }
})();
