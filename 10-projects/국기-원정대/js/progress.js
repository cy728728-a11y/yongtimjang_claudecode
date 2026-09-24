/* 지도 퀴즈 숙련도 계산 (순수 함수) — m = {iso: 0..3} */
(function (root) {
  "use strict";
  var MAX = 3;

  // 나라 숙련도 (없으면 0)
  function level(m, iso) {
    var v = m && m[iso];
    return typeof v === "number" ? Math.max(0, Math.min(MAX, v)) : 0;
  }

  // 정답 +1, 오답 -1 반영한 새 객체
  function applyResult(m, iso, correct) {
    var next = Object.assign({}, m || {});
    next[iso] = Math.max(0, Math.min(MAX, level(m, iso) + (correct ? 1 : -1)));
    return next;
  }

  // 출제 가중치: 모르는 나라일수록 자주
  function weight(m, iso) {
    return MAX + 1 - level(m, iso);
  }

  // 대륙의 열린 단계: 현재 단계 나라 80% 이상이 숙련도 2+ 면 다음 단계
  function unlockedTier(m, tierLists) {
    var t = 1;
    while (t < 3) {
      var list = tierLists[t] || [];
      var ok = list.filter(function (iso) { return level(m, iso) >= 2; }).length;
      if (list.length === 0 || ok / list.length >= 0.8) t++;
      else break;
    }
    return t;
  }

  // 가중치 비례 랜덤 선택
  function weightedPick(items, weightFn, rng) {
    var total = 0;
    var ws = items.map(function (it) { var w = weightFn(it); total += w; return w; });
    var r = (rng || Math.random)() * total;
    for (var i = 0; i < items.length; i++) {
      r -= ws[i];
      if (r < 0) return items[i];
    }
    return items[items.length - 1];
  }

  var api = { MAX: MAX, level: level, applyResult: applyResult, weight: weight,
              unlockedTier: unlockedTier, weightedPick: weightedPick };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.MQProgress = api;
})(this);
