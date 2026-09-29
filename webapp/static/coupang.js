/*
 * 쿠팡 트랙 JS (Phase 7 / CP-01~04) — **트랙 소유 파일이다.**
 *
 * 소유하는 요소 id:
 *   #coupang · #coupang-preview-btn (disabled 로 그려진다. 여기서 켠다)
 *   #coupang-body · #coupang-preview-job
 *   (조각 안) #coupang-commit-details · #coupang-typed-count · #coupang-commit-btn · #coupang-result(여기서 만든다)
 *
 * 부르는 라우트:
 *   POST /jobs/coupang/preview  {}                                 — 후보 뽑기(쓰기 0)
 *   POST /jobs/coupang/commit   { preview_job_id, typed_count }    — 몸통엔 잡 id + 건수만
 *
 * 기준값·상한·대상을 요청에 싣지 마라 — 서버가 정한다(L-04 · D-13 · D-15).
 * board.js 가 노출한 window.관제탑 훅만 쓴다. board.js 를 고치지 마라(D-19).
 */
(function () {
  "use strict";

  var 훅 = window.관제탑;
  if (!훅) { return; }   // 보드가 안 그려졌으면(데이터 못 읽음) 조용히 빠진다

  var 자리 = document.getElementById("coupang");
  var 버튼 = document.getElementById("coupang-preview-btn");
  var 몸통 = document.getElementById("coupang-body");
  var 잡칸 = document.getElementById("coupang-preview-job");

  // 후보 뽑기는 6단계(ship 배송비 대조가 수 분)다. 400ms 간격으로 20분까지 붙잡는다.
  // 그 뒤에도 도는 중이면 조각이 "뽑는 중" 을 그대로 보여 준다(없는 결과를 0건으로 읽지 않게).
  var 후보한도 = (20 * 60 * 1000) / 400;
  // 복사는 재조회(gate) + 복사 + verify — 상한 20건이면 수십 분이 될 수 있다. 60분까지.
  var 복사한도 = (60 * 60 * 1000) / 400;

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

  // board.js 의 결과기다리기는 status === "running" 만 붙잡는다. 막 띄운 잡은 잠깐 "starting" 이라
  // 그 순간 폴링이 끝나 "도는 중" 조각에 멈춘다 — starting 이면 1초 뒤 한 번 더 붙잡는다(최대 30회).
  function 기다리기(job_id, 한도, 몸통id, 재시도) {
    훅.결과기다리기(job_id, 한도, "coupang", 몸통id, function (j) {
      if (j && j.status === "starting" && (재시도 || 0) < 30) {
        setTimeout(function () { 기다리기(job_id, 한도, 몸통id, (재시도 || 0) + 1); }, 1000);
      }
    });
  }

  function 결과자리() {
    var 칸 = document.getElementById("coupang-result");
    if (!칸 && 자리) {
      칸 = document.createElement("div");
      칸.id = "coupang-result";
      자리.appendChild(칸);
    }
    return 칸;
  }

  if (버튼) {
    버튼.disabled = false;
    버튼.addEventListener("click", function () {
      버튼.disabled = true;
      // 몸통은 비어 있다 — 기준 필드를 실으면 서버가 422 로 거부한다(L-04).
      훅.요청("/jobs/coupang/preview", {}).then(function (res) {
        버튼.disabled = false;
        if (!res.ok) {
          // 409 = 같은 후보 뽑기가 도는 중 · 계정 불일치 · 다른 쓰기 작업
          훅.오류표시("쿠팡 후보 뽑기를 못 띄웠다 (" + res.code + ") — " + 사유뽑기(res));
          return;
        }
        var job_id = JSON.parse(res.본문).job_id;
        if (잡칸) { 잡칸.value = job_id; }
        if (몸통) { 몸통.textContent = ""; }
        var 결과칸 = document.getElementById("coupang-result");
        if (결과칸) { 결과칸.textContent = ""; }
        패널열기(job_id);
        기다리기(job_id, 후보한도, "coupang-body");
      }).catch(function (e) {
        버튼.disabled = false;
        훅.오류표시("쿠팡 후보 뽑기 요청이 실패했다: " + e);
      });
    });
  }

  // 후보 조각은 htmx 로 갈아끼워지므로 복사 버튼은 위임으로 받는다.
  if (자리) {
    자리.addEventListener("click", function (ev) {
      var 복사 = ev.target.closest("#coupang-commit-btn");
      if (!복사) { return; }
      var 입력 = document.getElementById("coupang-typed-count");
      var 글 = 입력 ? String(입력.value || "").trim() : "";
      // 정수가 아니면 요청을 보내지 않는다 — 빈칸·소수·음수는 확인이 아니다.
      if (!/^[0-9]+$/.test(글)) {
        훅.오류표시("복사할 건수를 숫자로 직접 입력해라 — 입력 없이는 복사하지 않는다");
        return;
      }
      var 건수 = parseInt(글, 10);
      var id = 복사.getAttribute("data-preview-job");
      복사.disabled = true;
      if (입력) { 입력.value = ""; }   // 요청 뒤 다시 누르려면 다시 타이핑해야 한다
      훅.요청("/jobs/coupang/commit", { preview_job_id: id, typed_count: 건수 }).then(function (res) {
        if (!res.ok) {
          복사.disabled = false;
          // 409 는 두 종류다: ① 건수 불일치(화면이 본 수 ≠ 서버가 지금 센 수)
          //                   ② 다른 쓰기 작업·같은 복사·후보 뽑기가 도는 중 / 계정 불일치.
          // 400 = 미리보기 실패·24시간 초과·이미 복사함 → 새 미리보기부터. detail 을 그대로 보인다.
          훅.오류표시("쿠팡 복사를 못 띄웠다 (" + res.code + ") — " + 사유뽑기(res));
          return;
        }
        var job_id = JSON.parse(res.본문).job_id;
        var 칸 = 결과자리();
        if (칸) { 칸.textContent = ""; }
        패널열기(job_id);
        기다리기(job_id, 복사한도, "coupang-result");
      }).catch(function (e) {
        복사.disabled = false;
        훅.오류표시("쿠팡 복사 요청이 실패했다: " + e);
      });
    });
  }
})();
