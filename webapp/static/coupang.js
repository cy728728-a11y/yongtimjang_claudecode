/*
 * 쿠팡 트랙 JS (Phase 7 / CP-01~04) — **트랙 소유 파일이다. 배선은 07-05 가 한다.**
 *
 * 소유하는 요소 id:
 *   #coupang · #coupang-preview-btn (disabled 로 그려진다. 배선하면서 켠다)
 *   #coupang-body · #coupang-preview-job
 *
 * 부르는 라우트:
 *   POST /jobs/coupang/preview  {}                                 — 후보 뽑기(쓰기 0)
 *   POST /jobs/coupang/commit   { preview_job_id, typed_count }    — 몸통엔 잡 id(+건수)만
 *
 * 기준값·상한·대상을 요청에 싣지 마라 — 서버가 정한다(L-04 · D-13 · D-15).
 * board.js 가 노출한 window.관제탑 훅만 쓴다. board.js 를 고치지 마라(D-19).
 */
(function () {
  "use strict";

  var 훅 = window.관제탑;
  if (!훅) { return; }   // 보드가 안 그려졌으면(데이터 못 읽음) 조용히 빠진다
})();
