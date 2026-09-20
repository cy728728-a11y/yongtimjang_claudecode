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
 * 선택(체크박스) 컬럼은 여기 없다. Plan 01-06/01-07 이 "보이는 것만 vs 필터 전체"
 * (BOARD-03/D-07) 확인 배너와 **같이** 붙인다. 지금 넣으면 확인 없는 전체 선택이
 * 먼저 생긴다.
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
    { title: "구매금액", field: "purAmt", hozAlign: "right", width: 105,
      sorter: "number", sorterParams: 빈칸아래, formatter: 정수 },
    // `cost` 는 **광고비**다. 원본 필드가 salesAmt 라서 헷갈리기 쉬운데
    // 광고에 쓴 돈이지 벌어들인 돈이 아니다 (ads_rules._with_stat:50 주석).
    { title: "광고비", field: "cost", hozAlign: "right", width: 100,
      sorter: "number", sorterParams: 빈칸아래, formatter: 정수 },
    { title: "현재입찰", field: "bid", hozAlign: "right", width: 90,
      sorter: "number", sorterParams: 빈칸아래, formatter: 정수 },
    { title: "그룹입찰따름", field: "useGroupBid", hozAlign: "center", width: 110,
      formatter: 예아니오 },
    { title: "①소재수", field: "rule1_count", hozAlign: "right", width: 90,
      sorter: "number", sorterParams: 빈칸아래, formatter: 정수 },
    { title: "상품ID", field: "mallProductId", width: 130, tooltip: true }
  ];

  var table = new Tabulator("#board", {
    data: rows,
    columns: columns,
    index: "key",
    layout: "fitColumns",
    // 높이를 고정해야 가상 DOM 이 켜진다. 안 켜지면 2,637행을 전부 그리느라 멈춘다.
    height: "60vh",
    placeholder: "조건에 맞는 상품이 없다",
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

  // 회차 드롭다운은 고르는 즉시 이동한다. GET 폼이라 서버 상태를 바꾸지 않는다.
  var 회차칸 = document.getElementById("rundir-select");
  if (회차칸 && 회차칸.form) {
    회차칸.addEventListener("change", function () { 회차칸.form.submit(); });
  }
})();
