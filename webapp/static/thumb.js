/*
 * 썸네일 트랙 JS (Phase 7 / THUMB-02) — **트랙 소유 파일이다. 배선은 07-04 가 한다.**
 *
 * 소유하는 요소 id:
 *   #thumb-estimate-btn  (board.html 선택 바 — disabled 로 그려진다. 배선하면서 켠다)
 *   #thumb-estimate · #thumb-estimate-body · #thumb-estimate-job
 *
 * 부르는 라우트:
 *   POST /jobs/thumb/estimate   { run_dir, keys }         — 견적 잡 접수(크레딧 0)
 *   POST /jobs/thumb/approve    { estimate_job_id }       — 몸통엔 잡 id 만
 *   GET  /thumb/{id}/result                               — 결과 조각
 *
 * board.js 가 노출한 window.관제탑 훅(선택키 · 회차 · 결과기다리기 · 요청)만 쓴다.
 * board.js 를 고치지 마라 — 공유 파일은 07-01 에서만 고친다(D-19).
 */
(function () {
  "use strict";

  var 훅 = window.관제탑;
  if (!훅) { return; }   // 보드가 안 그려졌으면(데이터 못 읽음) 조용히 빠진다
})();
