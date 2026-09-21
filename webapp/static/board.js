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

  // 상세 상태 기호 (STATE-03). **판정값은 서버(state.py)가 내고 기호만 여기서 붙인다** —
  // 판정을 화면이 다시 계산하면 진실이 둘이 된다.
  //
  // 기호만 내지 않고 **글자를 같이** 낸다. ⚪🟡🔴 은 흑백 출력·색맹에서 구분이
  // 사라지고, 그 순간 "가공 완료" 와 "중국어 원본" 이 같은 회색 동그라미가 된다.
  // 이 화면의 존재 이유가 그 구분이다.
  var 상태기호 = { "AI가공완료": "⚪", "단순번역만": "🟡", "중국어원본": "🔴" };

  // 미해소 버킷 (join.py). 같은 칸 안에서도 두 부류가 갈려야 한다 —
  // 광고청소는 **사람이 고칠 것**, 시스템은 **기계가 더 돌면 될 것**이다.
  // 섞으면 용팀장이 멀쩡한 광고그룹을 지우러 간다(Pitfall 3).
  var 광고청소 = "광고청소";

  function 상태(cell) {
    var v = cell.getValue();
    // **미판정은 빈칸이다.** 🔴로 대체하지 마라 — 그건 판정처럼 보이는데 실제로는
    // 판정이 없는 것이고, Phase 5 가 그 줄에 크레딧을 태운다 (T-3-35).
    if (빈칸이면(v)) { return ""; }
    var 기호 = 상태기호[v];
    return (기호 ? 기호 + " " : "") + v;
  }

  function 태그(cell) {
    // 기작업 태그는 용팀장의 손자국이고 상태는 불사자의 기계 기록이다.
    // **한 값으로 합치지 마라** (Pitfall 8) — 합치면 D-08 의 "인지하고 직접 판단" 이 죽는다.
    var v = cell.getValue();
    if (빈칸이면(v)) { return ""; }
    return String(v);
  }

  function 해소(cell) {
    var d = cell.getRow().getData();
    if (d.해소) { return "해소"; }
    // 서버가 붙인 **화면용 이름**을 쓴다. 판정 코드(`사유코드`)를 그대로 띄우면
    // 인덱스를 한 번도 안 훑은 행까지 "그룹에 없음" 으로 읽힌다(03-05 숙제).
    var 말 = d.표시사유;
    if (빈칸이면(말)) { return ""; }
    // 🛠 = 사람이 고칠 것(광고) · ⚙ = 기계가 더 돌면 될 것(시스템).
    // **기호가 구분을 지고 있는 게 아니다** — 서버가 붙인 이름이 이미 `번호…` /
    // `인덱스…` 로 갈려 있다(routes/board.py 의 `_사유이름`). 기호는 훑을 때의 덤이고,
    // 흑백·색맹에서 기호가 죽어도 글자가 남는다.
    return (d.버킷 === 광고청소 ? "🛠 " : "⚙ ") + 말;
  }

  /** 미해소 사유 전문. 잘린 칸을 hover 로 읽는다 — 이름 그대로 광고 화면에서 찾는다. */
  function 사유전문(e, cell) {
    var d = cell.getRow().getData();
    return d.사유 || "";
  }

  // 숫자 정렬에서 빈칸은 항상 아래로. 안 그러면 노출 내림차순 첫 페이지가
  // 통계 없는 ① 행으로 덮인다.
  var 빈칸아래 = { alignEmptyValues: "bottom" };

  // 🔴 **`widthShrink` 를 쓰지 마라.** 이 표에서는 정확히 반대로 동작한다.
  //
  // Phase 3 가 컬럼 4개를 더하면서 고정폭 합이 컨테이너를 넘었고(실측 1,775 / 1,448),
  // "그럼 shrink 로 비율 축소를 시키면 되겠다" 가 자연스러운 수였다. 실측 결과는
  // **2,022 로 더 넓어졌다.** 벤더 소스의 `fitColumns` 를 읽어 이유를 확인했다:
  //   · 고정폭 합 n 이 컨테이너 o 보다 크면 잔여 r = o - n 이 **음수**가 된다
  //   · grow 컬럼(상품명)은 minWidth 아래로 못 내려가 그 음수를 못 흡수한다
  //   · 남은 음수 c 가 `h[h.length-1].width -= c` 로 **마지막 shrink 컬럼에 더해진다**
  //     — 상품ID 가 105 → 392 로 부풀었다
  // 즉 shrink 는 "고정폭 합이 이미 컨테이너 안" 일 때만 뜻이 있다.
  //
  // 방법은 하나다: **고정폭 합 + 상품명 minWidth ≤ 컨테이너.**
  // 아래 폭은 그 예산(1,270 + 130 = 1,400 ≤ 1,448)에 맞춰 깎은 값이다.
  // 컬럼을 더 붙일 사람에게: 숫자를 눈대중으로 늘리지 말고 `board_cdp.sh` 의
  // V-BOARD-07 을 돌려라. 그 검사가 이 예산을 지키는 유일한 장치다.

  // 컬럼 정의를 **데이터 구조로** 둔다 (sheets_out.py:28-48 의 COLS 관례).
  // 규칙마다 있는 필드가 다르다는 사실이 이 표에 그대로 드러나야, ①의 빈칸이
  // 버그가 아니라 설계상 정상값이라는 게 읽는 사람에게 보인다.
  //
  // 폭 배분에 대해: 상품명은 이 저장소의 Core Value 가 걸린 열이라 제일 넓게 가져간다.
  // 그래도 한국어 상품명은 60자를 넘는 게 보통이라 어떤 폭을 줘도 잘린다(실측 38/40).
  // 줄바꿈(variableHeight)으로 다 보여주는 선택지는 **버렸다** — 2,637행 보드에서
  // 행 높이가 2~3배가 되면 한 화면에 7~8줄밖에 안 들어와 훑는 용도가 죽는다.
  // 대신 `tooltip: true` 로 hover 시 전문을 띄우고, 나머지 열의 군더더기 폭을 깎아
  // 가로 스크롤을 없앴다(바로 위 예산 주석). Phase 3 에서 컬럼 4개가 붙으면서
  // 숫자 열을 한 번 더 깎았다 — 세 자리 콤마 숫자는 72px 에 들어간다.
  // 상품명 전문이 상시 필요해지는 건 상세페이지 작업이고, 그때는 목록이 아니라
  // 상세 패널이 맡을 일이다.
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
    { title: "계정", field: "acct", width: 70 },
    { title: "규칙", field: "rules", width: 58 },
    { title: "상품명", field: "title", minWidth: 130, widthGrow: 5, tooltip: true },
    { title: "노출", field: "imp", hozAlign: "right", width: 72,
      sorter: "number", sorterParams: 빈칸아래, formatter: 정수 },
    { title: "클릭", field: "clk", hozAlign: "right", width: 64,
      sorter: "number", sorterParams: 빈칸아래, formatter: 정수 },
    { title: "CTR %", field: "ctr", hozAlign: "right", width: 64,
      sorter: "number", sorterParams: 빈칸아래, formatter: 비율 },
    { title: "구매완료", field: "purCnt", hozAlign: "right", width: 74,
      sorter: "number", sorterParams: 빈칸아래, formatter: 정수 },
    { title: "구매금액", field: "purAmt", hozAlign: "right", width: 80,
      sorter: "number", sorterParams: 빈칸아래, formatter: 정수 },
    // `cost` 는 **광고비**다. 원본 필드가 salesAmt 라서 헷갈리기 쉬운데
    // 광고에 쓴 돈이지 벌어들인 돈이 아니다 (ads_rules._with_stat:50 주석).
    { title: "광고비", field: "cost", hozAlign: "right", width: 76,
      sorter: "number", sorterParams: 빈칸아래, formatter: 정수 },
    { title: "현재입찰", field: "bid", hozAlign: "right", width: 74,
      sorter: "number", sorterParams: 빈칸아래, formatter: 정수 },
    { title: "그룹입찰따름", field: "useGroupBid", hozAlign: "center", width: 78,
      formatter: 예아니오 },
    { title: "①소재수", field: "rule1_count", hozAlign: "right", width: 70,
      sorter: "number", sorterParams: 빈칸아래, formatter: 정수 },
    // ── 조인 · 상세 상태 (Phase 3) ─────────────────────────────────────────
    // **상품ID 앞**에 둔다. 이 네 칸이 이 화면의 목적이라 오른쪽 끝에서 잘리면
    // 안 된다 — 🔴 를 골라내는 게 Core Value 다.
    { title: "상세", field: "상세상태", width: 102, formatter: 상태 },
    { title: "기작업", field: "기작업태그", width: 88, formatter: 태그 },
    { title: "사본", field: "사본N", hozAlign: "right", width: 54,
      sorter: "number", sorterParams: 빈칸아래, formatter: 정수 },
    // ⚠️ field 가 `사유코드` 가 **아니라** `표시사유` 다. 판정 코드는 데이터에 그대로
    //    남아 있지만(기계의 기록 · 소스 보기로 되짚는 통로) 화면에 그리지 않는다 —
    //    `사유코드` 의 `미스` 는 인덱스를 한 번도 안 훑은 행에도 붙어서, 그대로 띄우면
    //    시스템 사정이 광고 쪽 오류로 읽힌다(03-05 가 넘긴 숙제 / Pitfall 3).
    //    정렬도 표시 이름 기준이 맞다 — 사람이 보는 순서와 어긋나면 안 된다.
    { title: "해소", field: "표시사유", width: 116,
      formatter: 해소, tooltip: 사유전문 },
    { title: "상품ID", field: "mallProductId", width: 90, tooltip: true }
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
    // 기작업 행 회색 처리 (D-08). **숨기는 게 아니다** — 목록에 남고 태그가 보이며
    // 직접 체크하면 대상이 된다. 숨기면 "왜 이 상품이 안 보이지" 를 코드에서 찾아야 한다.
    // 판단은 서버(`join.attach` 의 `기작업`)가 내고 화면은 따라갈 뿐이다.
    rowFormatter: function (row) {
      var el = row.getElement();
      if (!el) { return; }
      if (row.getData().기작업) { el.classList.add("ct-done"); }
      else { el.classList.remove("ct-done"); }
    },
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
  var 상태칸 = document.getElementById("f-state");
  var 해소칸 = document.getElementById("f-join");
  var 초기화 = document.getElementById("f-reset");
  var 건수 = document.getElementById("board-count");

  // 상태 필터의 "미판정" 센티널. 빈 문자열은 이미 "전체" 라 쓸 수 없다 —
  // 둘을 같은 값으로 두면 "판정이 없는 행만 보기" 가 영영 불가능해진다.
  var 미판정 = "__none__";
  var 해소됨 = "__done__";

  function 고른값(sel) {
    if (!sel) { return []; }
    return Array.prototype.filter.call(sel.options, function (o) { return o.selected; })
      .map(function (o) { return o.value; });
  }

  function 필터적용() {
    var 계정 = 고른값(계정칸);
    var 규칙 = 고른값(규칙칸);
    var 말 = (검색칸 && 검색칸.value ? 검색칸.value : "").trim().toLowerCase();
    var 상태값 = 상태칸 ? 상태칸.value : "";
    var 해소값 = 해소칸 ? 해소칸.value : "";

    // 다섯 조건을 함수 하나로 합친다. 필터를 따로 걸면 해제 순서에 따라
    // 하나가 남아 "왜 안 보이지" 가 된다.
    // **`table.setFilter` 호출이 이 파일에 하나뿐인 것이 그 규율의 증거다.**
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
      if (상태값) {
        // 미판정은 **값이 없는 것**이다. 기본값으로 대체하지 않는다.
        if (상태값 === 미판정) {
          if (!빈칸이면(d.상세상태)) { return false; }
        } else if (d.상세상태 !== 상태값) { return false; }
      }
      if (해소값) {
        if (해소값 === 해소됨) {
          if (!d.해소) { return false; }
        } else if (d.버킷 !== 해소값) { return false; }   // 광고청소 / 시스템
      }
      return true;
    });
  }

  [계정칸, 규칙칸, 상태칸, 해소칸].forEach(function (el) {
    if (el) { el.addEventListener("change", 필터적용); }
  });
  if (검색칸) { 검색칸.addEventListener("input", 필터적용); }
  if (초기화) {
    초기화.addEventListener("click", function () {
      [계정칸, 규칙칸].forEach(function (sel) {
        if (!sel) { return; }
        Array.prototype.forEach.call(sel.options, function (o) { o.selected = false; });
      });
      [상태칸, 해소칸].forEach(function (sel) { if (sel) { sel.value = ""; } });
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
  /** 기본 선택 대상 — 기작업이 아닌 행만 (D-08 / STATE-05 · `join.selectable` 과 같은 규약). */
  function 고를수있는(행들) {
    return 행들.filter(function (r) { return !r.기작업; });
  }

  function 요약갱신(활성데이터) {
    if (!요약칸) { return; }
    var 고른것 = table.getSelectedData();
    var 활성 = 활성데이터 || table.getData("active");
    var 대상 = 대상수(고른것);
    var 규칙1있는상품 = 고른것.filter(function (r) { return (r.rule1_count || 0) > 0; }).length;
    var 빨강 = 고른것.filter(function (r) { return 상태기호[r.상세상태] === "🔴"; }).length;
    var 제외됨 = 활성.length - 고를수있는(활성).length;

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
    // 🔴 개수는 이 화면의 목적이다 — Phase 5 가 크레딧을 태울 줄이 몇 개인지.
    if (빨강) { 말 += " · 🔴 " + 콤마(빨강) + "개"; }
    if (제외됨) { 말 += " · 기작업 " + 콤마(제외됨) + "건 제외"; }
    if (필터밖) { 말 += " · 그중 " + 콤마(필터밖) + "개는 지금 필터 밖이다"; }
    if (!고른것.length) { 말 += " — 먼저 상품을 골라라"; }
    else if (!대상) { 말 += " — 고른 상품에 규칙① 소재가 없다(②③⑤ 소재는 인상 대상이 아니다)"; }
    요약칸.textContent = 말;

    if (미리보기버튼) { 미리보기버튼.disabled = 고른것.length === 0; }

    // "필터 전체 N건 선택" 은 **더 고를 게 남았을 때만** 띄운다.
    //
    // ⚠️ 기준이 `활성.length` 가 아니라 **고를 수 있는 행 중 아직 안 고른 것**이다.
    //    기작업을 빼고 고르므로, 활성 전체와 비교하면 기작업 행이 남아 있는 한
    //    링크가 영영 안 사라지고 눌러도 아무 일이 안 생긴다.
    if (전체링크칸) {
      var 후보 = 고를수있는(활성);
      var 선택키 = {};
      고른것.forEach(function (r) { 선택키[r.key] = 1; });
      var 남은 = 후보.filter(function (r) { return !선택키[r.key]; }).length;
      전체링크칸.hidden = 남은 === 0;
      if (남은 && 전체수칸) { 전체수칸.textContent = 콤마(후보.length); }
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
      var 후보 = 고를수있는(활성);
      var 제외됨 = 활성.length - 후보.length;
      if (!배너 || !배너말) { return; }
      배너말.textContent =
        "지금 필터를 통과한 상품 " + 콤마(후보.length) + "개를 고른다 — 대상 소재 "
        + 콤마(대상수(후보)) + "건."
        + (제외됨 ? " 기작업 " + 콤마(제외됨) + "건은 빼고 고른다 (직접 체크하면 들어간다)." : "")
        + " 진행할래?";
      배너.hidden = false;
    });
  }
  if (배너취소) { 배너취소.addEventListener("click", 배너닫기); }
  if (배너확인) {
    배너확인.addEventListener("click", function () {
      배너닫기();
      // **기작업 행을 뺀다** (D-08 / STATE-05). 크레딧 재지불을 막는 마지막 자리다.
      // 헤더 체크박스(`rowRange: "visible"`)는 건드리지 않는다 — 눈으로 보고 직접
      // 고르는 경로는 그대로 열려 있어야 한다.
      // 행 객체를 통째로 넘긴다 — 한 번에 넘겨야 선택 변경 이벤트가 한 번만 돈다.
      table.selectRow(table.getRows("active").filter(function (row) {
        return !row.getData().기작업;
      }));
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

  /**
   * 작업이 끝날 때까지 상태를 물어본 뒤 결과 표를 갈아끼운다.
   *
   * `자리id`/`몸통id` 로 미리보기와 실행이 같은 함수를 쓴다 — FLOW-01 이
   * "모든 버튼이 3단을 **똑같은 모양으로** 지난다" 이므로 화면 흐름도 하나여야 한다.
   * `끝났을때` 는 미리보기일 때만 쓰는 후처리다(실행 버튼 열기).
   */
  function 결과기다리기(job_id, 남은, 자리id, 몸통id, 끝났을때) {
    fetch("/jobs/" + encodeURIComponent(job_id), { headers: { "Accept": "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.status === "running" && 남은 > 0) {
          setTimeout(function () {
            결과기다리기(job_id, 남은 - 1, 자리id, 몸통id, 끝났을때);
          }, 400);
          return;
        }
        var 자리 = document.getElementById(자리id);
        if (자리) { 자리.hidden = false; }
        // htmx 로 갈아끼운다 — 서버가 만든 조각을 그대로 쓴다(표를 JS 로 짓지 않는다).
        htmx.ajax("GET", "/jobs/" + encodeURIComponent(job_id) + "/result",
                  { target: "#" + 몸통id, swap: "innerHTML" });
        if (끝났을때) { 끝났을때(j); }
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
        // 새 미리보기를 접수하는 순간 지난 실행 결과와 실행 버튼을 닫는다.
        // 안 닫으면 새 표 밑에 **지난 실행의 결과**가 남아 지금 것으로 읽힌다.
        실행닫기();
        결과기다리기(job_id, 150, "preview", "preview-body", function (상태) {
          실행열기(job_id, 상태);
        });
      }).catch(function (e) {
        미리보기버튼.disabled = false;
        오류표시("미리보기 요청이 실패했다: " + e);
      });
    });
  }

  // ── 실행 (FLOW-01 / D-11) ─────────────────────────────────────────────────
  //
  // **실행 버튼은 끝난 미리보기 job_id 가 있어야만 열린다.** 그리고 요청에 실리는
  // 것은 그 job_id 하나뿐이다 — 대상 목록을 여기서 다시 만들지 않는다. 화면 상태로
  // 목록을 재구성하면, 미리보기를 본 뒤 필터를 바꾼 만큼 **본 것과 다른 게 실행된다**
  // (D-11 / FLOW-02 / T-1-06). 서버도 같은 것을 다시 검사한다 — 화면만 믿지 않는다.
  var 실행칸 = document.getElementById("commit-wrap");
  var 실행버튼 = document.getElementById("commit-btn");
  var 실행요약 = document.getElementById("commit-summary");
  var 실행예상 = document.getElementById("commit-eta");
  var 실행잡칸 = document.getElementById("commit-preview-job");

  // CLI 의 페이싱. `bids.py` 가 항목마다 잠깐 쉰다 — 초당 12건이 그 결과다.
  // 진행률이 없는 작업이라(OQ-3) 이 수로 "얼마나 걸릴지" 를 미리 말해 준다.
  var 초당건수 = 12;

  function 실행닫기() {
    if (실행칸) { 실행칸.hidden = true; }
    if (실행버튼) { 실행버튼.disabled = true; }
    if (실행잡칸) { 실행잡칸.value = ""; }
    var 결과자리 = document.getElementById("result");
    if (결과자리) { 결과자리.hidden = true; }
  }

  /** 미리보기가 끝났다 → 실행 버튼을 연다. 산출물 집계는 서버에서 받아 넣는다. */
  function 실행열기(job_id, 상태) {
    if (!실행칸 || !실행버튼) { return; }
    if (!상태 || 상태.status !== "done") {
      // 미리보기가 실패했으면 실행을 열지 않는다 — 본 것이 없는데 실행할 수는 없다.
      실행닫기();
      return;
    }
    if (실행잡칸) { 실행잡칸.value = job_id; }
    실행칸.hidden = false;
    실행버튼.disabled = false;

    // 요약 숫자는 **서버가 CLI 산출물에서 낸 값**이다. 여기서 세지도 계산하지도 않는다.
    fetch("/jobs/" + encodeURIComponent(job_id) + "/result?format=json",
          { headers: { "Accept": "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        var 인상 = (j.counts && j.counts["인상"]) || 0;
        if (실행요약) {
          실행요약.textContent = "대상 " + 콤마(j.total || 0) + "건 · 인상 "
            + 콤마(인상) + "건 · 예상 인상액 합계 +" + 콤마(j.raise_total || 0) + "원";
        }
        if (실행예상) {
          var 초 = Math.ceil((j.total || 0) / 초당건수);
          실행예상.textContent = "멈춘 게 아니다 — 초당 " + 초당건수
            + "건씩 돈다. " + 콤마(j.total || 0) + "건이면 약 " + 콤마(초)
            + "초. 그동안 로그에는 실패 줄 말고 아무것도 안 찍힌다.";
        }
        // 인상이 0건이면 누를 이유가 없다 — 쿨다운으로 전부 빠진 상태다.
        if (!인상) { 실행버튼.disabled = true; }
      })
      .catch(function (e) { 오류표시("미리보기 집계를 못 읽었다: " + e); });
  }

  if (실행버튼) {
    실행버튼.addEventListener("click", function () {
      var 부모 = 실행잡칸 ? 실행잡칸.value : "";
      if (!부모) { 오류표시("미리보기부터 해라 — 실행할 대상이 없다"); return; }
      if (작업오류) { 작업오류.hidden = true; }
      실행버튼.disabled = true;

      fetch("/jobs/bids/commit", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CT-Token": 토큰() },
        body: JSON.stringify({ preview_job_id: 부모 })
      }).then(function (r) {
        return r.text().then(function (본문) { return { ok: r.ok, code: r.status, 본문: 본문 }; });
      }).then(function (res) {
        if (!res.ok) {
          실행버튼.disabled = false;
          var 사유 = res.본문;
          try { 사유 = JSON.parse(res.본문).detail || res.본문; } catch (e) { /* 원문 그대로 */ }
          오류표시("실행을 못 만들었다 (" + res.code + ") — " + 사유);
          return;
        }
        var job_id = JSON.parse(res.본문).job_id;
        htmx.ajax("GET", "/jobs/" + encodeURIComponent(job_id) + "/panel",
                  { target: "#job-panel", swap: "outerHTML" });
        // 실행은 1,200건이면 100초쯤 걸린다 — 폴링 한도를 넉넉히 준다(0.4초 × 3000).
        // **종료코드로 성공을 판단하지 않는다.** 결과 표가 항목별 result 를 읽어 그린다.
        결과기다리기(job_id, 3000, "result", "result-body", null);
      }).catch(function (e) {
        실행버튼.disabled = false;
        오류표시("실행 요청이 실패했다: " + e);
      });
    });
  }

  // ── 되돌리기 (BID-04 / D-13 / D-14) ───────────────────────────────────────
  //
  // 두 버튼은 **서로 다른 라우트**다. 여기서 플래그 하나로 갈리게 만들지 마라 —
  // 그러면 "회차 전체" 가 되는 경로가 한 글자 차이로 열린다.
  //   · 이 작업분만  → POST /jobs/revert/job   { commit_job_id }
  //   · 이 회차 전체 → POST /jobs/revert/round { run_dir, confirmed_count }
  //
  // 대상 목록은 **어느 쪽도 화면이 만들지 않는다.** 앞쪽은 서버가 실행 잡의 산출물에서
  // 성공 adId 를 추리고, 뒤쪽은 CLI 가 백업 전량을 고른다.

  /** 되돌리기 잡을 접수하고 결과 표까지 이어 붙인다. 두 버튼이 같은 뒤처리를 쓴다. */
  function 되돌리기접수(경로, 몸통, 버튼) {
    if (작업오류) { 작업오류.hidden = true; }
    if (버튼) { 버튼.disabled = true; }

    fetch(경로, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CT-Token": 토큰() },
      body: JSON.stringify(몸통)
    }).then(function (r) {
      return r.text().then(function (본문) { return { ok: r.ok, code: r.status, 본문: 본문 }; });
    }).then(function (res) {
      if (!res.ok) {
        if (버튼) { 버튼.disabled = false; }
        // 409 는 두 종류다 — "이미 도는 쓰기 작업" 과 **"범위가 안 맞아서 막았다"**.
        // 후자가 이 화면에서 제일 중요한 메시지라 사유를 통째로 보여준다.
        var 사유 = res.본문;
        try { 사유 = JSON.parse(res.본문).detail || res.본문; } catch (e) { /* 원문 그대로 */ }
        오류표시("되돌리기를 못 만들었다 (" + res.code + ") — " + 사유);
        return;
      }
      var job_id = JSON.parse(res.본문).job_id;
      htmx.ajax("GET", "/jobs/" + encodeURIComponent(job_id) + "/panel",
                { target: "#job-panel", swap: "outerHTML" });
      결과기다리기(job_id, 3000, "result", "result-body", null);
    }).catch(function (e) {
      if (버튼) { 버튼.disabled = false; }
      오류표시("되돌리기 요청이 실패했다: " + e);
    });
  }

  // "이 작업분만 되돌리기" 는 결과 표 **조각 안**에 있다. 조각은 htmx 가 갈아끼우므로
  // 버튼을 직접 집으면 첫 렌더 뒤로는 못 잡는다 — 위임으로 듣는다.
  document.addEventListener("click", function (ev) {
    var 버튼 = ev.target.closest ? ev.target.closest("#revert-job-btn") : null;
    if (!버튼 || 버튼.disabled) { return; }
    되돌리기접수("/jobs/revert/job", { commit_job_id: 버튼.dataset.job }, 버튼);
  });

  // "이 회차 전체 되돌리기" — 건수 확인 단계를 반드시 거친다 (D-14).
  var 전체버튼 = document.getElementById("revert-round-btn");
  var 전체확인 = document.getElementById("revert-round-confirm");
  var 전체문구 = document.getElementById("revert-round-msg");
  var 전체건수칸 = document.getElementById("revert-round-count");
  var 전체확인ok = document.getElementById("revert-round-ok");
  var 전체취소 = document.getElementById("revert-round-cancel");

  function 전체확인닫기() {
    if (전체확인) { 전체확인.hidden = true; }
    if (전체건수칸) { 전체건수칸.value = ""; }
    if (전체버튼) { 전체버튼.disabled = false; }
  }

  if (전체버튼) {
    전체버튼.addEventListener("click", function () {
      if (작업오류) { 작업오류.hidden = true; }
      전체버튼.disabled = true;
      // **건수는 누르는 순간 서버에 물어본다.** 페이지를 연 뒤에 다른 작업이 인상을
      // 더했으면 승인하는 규모가 달라진다. 이 수가 그대로 confirmed_count 로 돌아가고,
      // 서버가 접수 시점에 다시 세서 다르면 409 다.
      fetch("/jobs/revert/round/count?run_dir=" + encodeURIComponent(회차칸값 ? 회차칸값.value : ""),
            { headers: { "Accept": "application/json" } })
        .then(function (r) { return r.json(); })
        .then(function (j) {
          var n = j.total || 0;
          if (전체건수칸) { 전체건수칸.value = String(n); }
          if (전체문구) {
            전체문구.textContent = (회차칸값 ? 회차칸값.value : "") + " 회차의 인상분 "
              + 콤마(n) + "건을 전부 되돌린다. 방금 누른 작업만이 아니다.";
          }
          if (전체확인) { 전체확인.hidden = false; }
          // 0건이면 승인할 게 없다 — 확인 버튼을 열지 않는다.
          if (전체확인ok) { 전체확인ok.disabled = !n; }
        })
        .catch(function (e) {
          전체버튼.disabled = false;
          오류표시("되돌릴 건수를 못 읽었다: " + e);
        });
    });
  }

  if (전체취소) {
    // 취소는 **아무 요청도 보내지 않는다.** 닫기만 한다.
    전체취소.addEventListener("click", 전체확인닫기);
  }

  if (전체확인ok) {
    전체확인ok.addEventListener("click", function () {
      var n = parseInt(전체건수칸 ? 전체건수칸.value : "", 10);
      if (!n) { 오류표시("되돌릴 건수를 확인하지 못했다 — 다시 눌러라"); return; }
      전체확인ok.disabled = true;
      되돌리기접수("/jobs/revert/round",
                 { run_dir: 회차칸값 ? 회차칸값.value : "", confirmed_count: n },
                 전체확인ok);
      전체확인닫기();
    });
  }

  // 회차 드롭다운은 고르는 즉시 이동한다. GET 폼이라 서버 상태를 바꾸지 않는다.
  var 회차칸 = document.getElementById("rundir-select");
  if (회차칸 && 회차칸.form) {
    회차칸.addEventListener("change", function () { 회차칸.form.submit(); });
  }
})();
