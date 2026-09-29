/*
 * 썸네일 트랙 JS (Phase 7 / THUMB-01·02·03) — **트랙 소유 파일이다.**
 *
 * 소유하는 요소 id:
 *   #thumb-estimate-btn  (board.html 선택 바 — disabled 로 그려진다. 여기서 켠다)
 *   #thumb-estimate · #thumb-estimate-body · #thumb-estimate-job · #thumb-result(여기서 만든다)
 *
 * 부르는 라우트:
 *   POST /jobs/thumb/estimate   { run_dir, keys }         — 견적 잡 접수(크레딧 0)
 *   POST /jobs/thumb/approve    { estimate_job_id }       — 몸통엔 잡 id 만. 잡이 아니다(승인 파일만)
 *   GET  /thumb/{id}/result                               — 결과 조각(읽기)
 *
 * board.js 가 노출한 window.관제탑 훅(선택키 · 회차 · 결과기다리기 · 오류표시 · 요청)만 쓴다.
 * board.js 를 고치지 마라 — 공유 파일은 07-01 에서만 고친다(D-19).
 *
 * **몸통에 싣는 것은 보드 키와 잡 id 뿐이다.** 그룹명·상한·크레딧 숫자를 보내지 않는다 —
 * 서버가 조인 산출물과 summary.json 에서 다시 읽는다(T-07-20 · T-07-21).
 */
(function () {
  "use strict";

  var 훅 = window.관제탑;
  if (!훅) { return; }   // 보드가 안 그려졌으면(데이터 못 읽음) 조용히 빠진다

  var 버튼 = document.getElementById("thumb-estimate-btn");
  var 자리 = document.getElementById("thumb-estimate");
  var 몸통 = document.getElementById("thumb-estimate-body");
  var 잡칸 = document.getElementById("thumb-estimate-job");

  // 견적 잡은 그룹마다 prep 을 차례로 돈다 — 수 분이 걸린다. 400ms 간격으로 10분까지 붙잡는다.
  // 그 뒤에도 도는 중이면 조각이 "만드는 중" 을 그대로 보여 준다(없는 결과를 0건으로 읽지 않게).
  var 기다림한도 = (10 * 60 * 1000) / 400;   // 결과기다리기 폴링 간격이 400ms 다

  function 사유뽑기(res) {
    var 사유 = res.본문;
    try {
      var d = JSON.parse(res.본문).detail;
      사유 = typeof d === "string" ? d : JSON.stringify(d);
    } catch (e) { /* 원문 그대로 */ }
    return 사유;
  }

  // 선택 변화는 board.js 의 Tabulator `rowSelectionChanged` 로 받는다(아래 선택구독).
  // Tabulator 의 행 체크박스 클릭은 document 까지 버블링되지 않아 click/keyup 만으론
  // 버튼이 안 켜졌다(07-uat P1). click/keyup 은 보조로만 남긴다. 클릭 시점에도 한 번 더 검사한다.
  function 버튼갱신() {
    if (!버튼) { return; }
    var 있음 = 훅.회차() && 훅.선택키().length > 0;
    버튼.disabled = !있음;
  }

  function 결과자리() {
    var 칸 = document.getElementById("thumb-result");
    if (!칸 && 자리) {
      칸 = document.createElement("div");
      칸.id = "thumb-result";
      자리.appendChild(칸);
    }
    return 칸;
  }

  if (버튼) {
    // board.js 를 안 고치고(D-19) 같은 Tabulator 인스턴스를 찾아 선택 변화에 붙는다.
    // Tabulator.findTable 은 생성자에서 등록된 표를 돌려준다 — board.js 가 먼저 로드된다.
    try {
      var 표들 = (window.Tabulator && Tabulator.findTable) ? Tabulator.findTable("#board") : [];
      if (표들 && 표들[0]) {
        표들[0].on("rowSelectionChanged", function () { 버튼갱신(); });
      }
    } catch (e) { /* 못 찾으면 아래 click/keyup 보조로 버틴다 */ }
    document.addEventListener("click", function () { setTimeout(버튼갱신, 0); });
    document.addEventListener("keyup", function () { setTimeout(버튼갱신, 0); });
    버튼갱신();

    버튼.addEventListener("click", function () {
      var 키들 = 훅.선택키();
      if (!훅.회차()) { 훅.오류표시("회차를 먼저 골라라"); return; }
      if (!키들.length) { 훅.오류표시("먼저 규칙② 상품을 골라라"); return; }
      버튼.disabled = true;

      훅.요청("/jobs/thumb/estimate", { run_dir: 훅.회차(), keys: 키들 }).then(function (res) {
        버튼갱신();
        if (!res.ok) {
          // 400 = 규칙② 대상 0건(상품별 사유) · 모르는 상품 · 409 = 조인 스캔 먼저 · 계정 불일치 · 같은 견적 도는 중
          훅.오류표시("썸네일 견적을 못 만들었다 (" + res.code + ") — " + 사유뽑기(res));
          return;
        }
        var job_id = JSON.parse(res.본문).job_id;
        if (잡칸) { 잡칸.value = job_id; }
        if (몸통) { 몸통.textContent = ""; }
        var 결과칸 = document.getElementById("thumb-result");
        if (결과칸) { 결과칸.textContent = ""; }
        if (자리) { 자리.hidden = false; }
        htmx.ajax("GET", "/jobs/" + encodeURIComponent(job_id) + "/panel",
                  { target: "#job-panel", swap: "outerHTML" });
        훅.결과기다리기(job_id, 기다림한도, "thumb-estimate", "thumb-estimate-body");
      }).catch(function (e) {
        버튼갱신();
        훅.오류표시("썸네일 견적 요청이 실패했다: " + e);
      });
    });
  }

  // 견적 조각 안의 버튼은 htmx 로 갈아끼워지므로 위임으로 받는다.
  if (자리) {
    자리.addEventListener("click", function (ev) {
      var 승인 = ev.target.closest("[data-thumb-approve]");
      if (승인) {
        var id = 승인.getAttribute("data-thumb-approve");
        승인.disabled = true;
        훅.요청("/jobs/thumb/approve", { estimate_job_id: id }).then(function (res) {
          if (!res.ok) {
            승인.disabled = false;
            훅.오류표시("실행 승인을 못 했다 (" + res.code + ") — " + 사유뽑기(res));
            return;
          }
          // 승인 파일이 생겼다 — 견적 조각을 다시 그리면 인계 명령과 '결과 보기' 가 뜬다.
          htmx.ajax("GET", "/jobs/" + encodeURIComponent(id) + "/result",
                    { target: "#thumb-estimate-body", swap: "innerHTML" });
        }).catch(function (e) {
          승인.disabled = false;
          훅.오류표시("실행 승인 요청이 실패했다: " + e);
        });
        return;
      }
      var 결과 = ev.target.closest("[data-thumb-result]");
      if (결과) {
        var rid = 결과.getAttribute("data-thumb-result");
        결과자리();
        htmx.ajax("GET", "/thumb/" + encodeURIComponent(rid) + "/result",
                  { target: "#thumb-result", swap: "innerHTML" });
      }
    });
  }
})();
