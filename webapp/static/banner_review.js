/* 배너 검수 화면 — 👁·↩ 표식 장만 보기 토글 (quick 260925-2d8).
 *
 * **화면 전용이다.** 서버에 아무것도 보내지 않고, 라벨·확인함 동작을 건드리지 않는다.
 * 숨기기는 body 클래스 하나로 CSS 가 한다(banner_review.html 의 규칙) — 요소를 지우지
 * 않으므로 끄면 전장이 그대로 돌아온다(D-03a).
 *
 * 표식 여부는 서버가 정한 `data-mark` 속성의 **있고 없음**만 본다. 출처 문자열을
 * 여기서 비교하지 않는다 — 그러면 판정의 정본이 둘이 된다(S-1).
 *
 * 개수 글귀는 "화면 표식 기준" 이다. 04-GATE §16-6 재검수 목록(사람이 안 본 바뀐 판정)
 * 과는 다르다 — 이미 라벨 찍은 장도 여기 들어간다.
 */
(function () {
  "use strict";

  var 주소키 = "only";
  var 주소값 = "marks";
  var 켜짐클래스 = "ct-only-marks";

  var 토글 = document.getElementById("mark-filter");
  var 글귀 = document.getElementById("mark-filter-count");
  // 집계 없음 분기(스캔 전·회차 없음)에는 토글이 없다 — 아무것도 안 한다.
  if (!토글) { return; }

  // DOM 의 서버 속성에서만 센다. 화면 내부 상태를 새로 만들지 않는다.
  function 개수() {
    var 표식장 = document.querySelectorAll('.ct-row figure[data-slot="strip"][data-mark]');
    var 안본장 = 0;
    var 줄 = 0;
    for (var i = 0; i < 표식장.length; i++) {
      if (!표식장[i].classList.contains("ct-human")) { 안본장 += 1; }
    }
    var 줄들 = document.querySelectorAll(".ct-row");
    for (var j = 0; j < 줄들.length; j++) {
      if (줄들[j].querySelector('figure[data-slot="strip"][data-mark]')) { 줄 += 1; }
    }
    return { 장: 표식장.length, 상품: 줄, 안본장: 안본장 };
  }

  function 그리기() {
    try {
      var 켬 = !!토글.checked;
      document.body.classList.toggle(켜짐클래스, 켬);
      if (!글귀) { return; }
      if (!켬) { 글귀.textContent = ""; return; }
      var n = 개수();
      if (n.장 === 0) {
        // 조용히 빈 화면을 만들지 않는다 — 왜 비었는지 말한다.
        글귀.textContent = "이 회차에는 👁·↩ 표식 장이 없다 (2차 판정 꺼짐 또는 옛 회차)";
        return;
      }
      글귀.textContent = "표식 " + n.장 + "장 / " + n.상품 + "상품 · 그중 ✋ 없는 장 " + n.안본장
        + " — 화면 표식(👁·↩) 기준이다. 04-GATE 재검수 목록(사람이 안 본 바뀐 판정 128장)과"
        + " 수가 다르다: 이미 라벨 찍은 장도 여기 들어간다";
    } catch (e) {
      // 필터가 고장나도 검수 화면 자체는 막지 않는다 — 필터만 끈다.
      document.body.classList.remove(켜짐클래스);
      console.warn("표식 필터를 그리지 못했다 — 필터만 끈다", e);
    }
  }

  function 주소반영() {
    try {
      var u = new URL(window.location.href);
      if (토글.checked) { u.searchParams.set(주소키, 주소값); }
      else { u.searchParams.delete(주소키); }
      // run_dir 등 다른 파라미터는 그대로 둔다.
      window.history.replaceState(null, "", u.pathname + u.search + u.hash);
    } catch (e) {
      console.warn("표식 필터 상태를 주소에 남기지 못했다", e);
    }
  }

  // 로드 시 주소에서 복원. 값이 정확히 marks 일 때만 켠다 — 그 값을 DOM 에 쓰지 않는다.
  try {
    var 쿼리 = new URLSearchParams(window.location.search);
    토글.checked = 쿼리.get(주소키) === 주소값;
  } catch (e) {
    토글.checked = false;
    console.warn("주소에서 표식 필터 상태를 읽지 못했다 — 끈 채로 둔다", e);
  }

  토글.addEventListener("change", function () { 주소반영(); 그리기(); });
  // 라벨 클릭 뒤 figure 가 교체되면 ✋ 없는 장 수를 다시 센다.
  document.body.addEventListener("htmx:afterSettle", 그리기);
  그리기();
})();
