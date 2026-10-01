/*
 * 꺼진 소재 정리 트랙 JS (Phase 2 / PRUNE-01~03 · 02-03) — **트랙 소유 파일이다.**
 *
 * 소유하는 요소 id:
 *   #prune · #prune-preview-btn (disabled 로 그려진다. 여기서 켠다) · input[name=prune-account]
 *   #prune-body · #prune-preview-job
 *   (조각 안) #prune-preview-grid · #prune-preview-rows
 *             #prune-commit-details · #prune-typed-count · #prune-commit-btn · #prune-result(여기서 만든다)
 *
 * 부르는 라우트:
 *   POST /jobs/prune/preview  { run_dir, accounts }              — 광고 쓰기 0
 *   POST /jobs/prune/commit   { preview_job_id, typed_count }    — 몸통엔 잡 id + 건수만
 *
 * 대상 소재 목록·상한을 요청에 싣지 마라 — 서버가 CLI 산출물에서 정한다(SAFE-06 · D-02).
 * board.js 가 노출한 window.관제탑 훅만 쓴다. board.js 를 고치지 마라.
 */
(function () {
  "use strict";

  var 훅 = window.관제탑;
  if (!훅) { return; }   // 보드가 안 그려졌으면(데이터 못 읽음) 조용히 빠진다

  var 자리 = document.getElementById("prune");
  var 버튼 = document.getElementById("prune-preview-btn");
  var 몸통 = document.getElementById("prune-body");
  var 잡칸 = document.getElementById("prune-preview-job");

  // 미리보기는 계정당 ads.json 판정 + 백업 — 수십 초. 400ms 간격으로 5분까지 붙잡는다.
  var 미리보기한도 = (5 * 60 * 1000) / 400;
  // 삭제는 백업 → 재조회 → DELETE(수천 건이면 수십 분). 60분까지.
  var 커밋한도 = (60 * 60 * 1000) / 400;

  function 사유뽑기(res) {
    var 사유 = res.본문;
    try {
      var d = JSON.parse(res.본문).detail;
      사유 = typeof d === "string" ? d : JSON.stringify(d);
    } catch (e) { /* 원문 그대로 */ }
    return 사유;
  }

  function 패널열기(job_id) {
    htmx.ajax("GET", "/jobs/" + encodeURIComponent(job_id) + "/panel",
              { target: "#job-panel", swap: "outerHTML" });
  }

  // board.js 의 결과기다리기는 status === "running" 만 붙잡는다 — starting 이면 1초 뒤 다시(최대 30회).
  function 기다리기(job_id, 한도, 몸통id, 재시도) {
    훅.결과기다리기(job_id, 한도, "prune", 몸통id, function (j) {
      if (j && j.status === "starting" && (재시도 || 0) < 30) {
        setTimeout(function () { 기다리기(job_id, 한도, 몸통id, (재시도 || 0) + 1); }, 1000);
      }
    });
  }

  function 결과자리() {
    var 칸 = document.getElementById("prune-result");
    if (!칸 && 자리) {
      칸 = document.createElement("div");
      칸.id = "prune-result";
      자리.appendChild(칸);
    }
    return 칸;
  }

  function 고른계정() {
    var 칸들 = document.querySelectorAll('input[name="prune-account"]:checked');
    var 값 = [];
    for (var i = 0; i < 칸들.length; i++) { 값.push(칸들[i].value); }
    return 값;   // 빈 배열 = 전 계정 (서버가 그렇게 읽는다)
  }

  // 미리보기 조각이 들어오면 데이터 블록(JSON)으로 Tabulator 를 마운트한다.
  // 표를 JS 문자열로 짓지 않는다 — 셀은 Tabulator 가 텍스트로 넣는다(이스케이프 걱정 없음).
  function 표붙이기() {
    var 데이터칸 = document.getElementById("prune-preview-rows");
    var 표칸 = document.getElementById("prune-preview-grid");
    if (!데이터칸 || !표칸 || 표칸.getAttribute("data-mounted")) { return; }
    var 행;
    try { 행 = JSON.parse(데이터칸.textContent || "[]"); } catch (e) { 행 = []; }
    if (!행.length || typeof Tabulator === "undefined") { return; }
    var 열 = Object.keys(행[0]).map(function (k) {
      return { title: k, field: k, headerFilter: k === "계정" ? false : "input" };
    });
    표칸.setAttribute("data-mounted", "1");
    new Tabulator(표칸, {
      data: 행,
      columns: 열,
      height: "480px",          // 고정 높이 = 가상 렌더링(수천 행)
      layout: "fitDataStretch",
      groupBy: "계정",
      groupStartOpen: false,    // 계정별로 접어 둔다 — 펼쳐서 본다
      groupHeader: function (값, 개수) { return 값 + " — " + 개수 + "건"; }
    });
  }

  document.body.addEventListener("htmx:afterSwap", function (ev) {
    var t = ev.detail && ev.detail.target;
    if (t && t.id === "prune-body") { 표붙이기(); }
  });

  if (버튼) {
    버튼.disabled = false;
    버튼.addEventListener("click", function () {
      버튼.disabled = true;
      훅.요청("/jobs/prune/preview", { run_dir: 훅.회차(), accounts: 고른계정() }).then(function (res) {
        버튼.disabled = false;
        if (!res.ok) {
          // 409 = 같은 미리보기가 도는 중 · 같은 회차 수집 중 / 400 = 모르는 회차
          훅.오류표시("꺼진 소재 미리보기를 못 띄웠다 (" + res.code + ") — " + 사유뽑기(res));
          return;
        }
        var job_id = JSON.parse(res.본문).job_id;
        if (잡칸) { 잡칸.value = job_id; }
        if (몸통) { 몸통.textContent = ""; }
        var 결과칸 = document.getElementById("prune-result");
        if (결과칸) { 결과칸.textContent = ""; }
        패널열기(job_id);
        기다리기(job_id, 미리보기한도, "prune-body");
      }).catch(function (e) {
        버튼.disabled = false;
        훅.오류표시("꺼진 소재 미리보기 요청이 실패했다: " + e);
      });
    });
  }

  // 조각 안 버튼(삭제·재시도)은 htmx 로 갈아끼워지므로 위임으로 받는다.
  // 정수가 아니면 요청을 보내지 않는다 — 빈칸·소수·음수는 확인이 아니다.
  // 요청 직후 입력을 비운다 — 다시 누르려면 다시 타이핑해야 한다(T-02-19).
  function 타이핑실행(입력id, 버튼, url, 몸통키, 잡속성, 이름) {
    var 입력 = document.getElementById(입력id);
    var 글 = 입력 ? String(입력.value || "").trim() : "";
    if (!/^[0-9]+$/.test(글)) {
      훅.오류표시("지울 건수를 숫자로 직접 입력해라 — 입력 없이는 지우지 않는다");
      return;
    }
    var 몸 = { typed_count: parseInt(글, 10) };
    몸[몸통키] = 버튼.getAttribute(잡속성);
    버튼.disabled = true;
    if (입력) { 입력.value = ""; }
    훅.요청(url, 몸).then(function (res) {
      if (!res.ok) {
        버튼.disabled = false;
        // 409 = 건수 불일치 · 이미 삭제 · 도는 중 · 다른 쓰기 작업 / 400 = 24시간 · 상한 · 산출물 깨짐.
        // detail 을 그대로 보인다 — 다시 누르라고 유도하지 않는다.
        훅.오류표시(이름 + " 작업을 못 띄웠다 (" + res.code + ") — " + 사유뽑기(res));
        return;
      }
      var job_id = JSON.parse(res.본문).job_id;
      var 칸 = 결과자리();
      if (칸) { 칸.textContent = ""; }
      패널열기(job_id);
      기다리기(job_id, 커밋한도, "prune-result");
    }).catch(function (e) {
      버튼.disabled = false;
      훅.오류표시(이름 + " 요청이 실패했다: " + e);
    });
  }

  if (자리) {
    자리.addEventListener("click", function (ev) {
      var 삭제 = ev.target.closest("#prune-commit-btn");
      if (삭제) {
        타이핑실행("prune-typed-count", 삭제, "/jobs/prune/commit",
                   "preview_job_id", "data-preview-job", "꺼진 소재 삭제");
      }
    });
  }
})();
