/* 지도 퀴즈 출제 로직 (순수 함수) */
(function (root) {
  "use strict";
  var P = (typeof module !== "undefined" && module.exports) ? require("./progress.js") : root.MQProgress;

  var POINTS = { stageContinent: 3, stageCountry: 7, direct: 10, name: 10 };

  function shuffle(arr, rng) {
    var a = arr.slice();
    for (var i = a.length - 1; i > 0; i--) {
      var j = Math.floor(rng() * (i + 1));
      var t = a[i]; a[i] = a[j]; a[j] = t;
    }
    return a;
  }

  // 대륙의 단계별 나라 목록
  function tierLists(countries, contKey) {
    var t = { 1: [], 2: [], 3: [] };
    countries.forEach(function (c) { if (c.continent === contKey) t[c.tier].push(c.iso); });
    return t;
  }

  function unlockedByContinent(countries, m, contKeys) {
    var out = {};
    contKeys.forEach(function (k) { out[k] = P.unlockedTier(m, tierLists(countries, k)); });
    return out;
  }

  // 출제 풀 = 선택 대륙 중 열린 단계 이하 나라
  function poolFor(countries, m, contKeys) {
    var unlocked = unlockedByContinent(countries, m, contKeys);
    var pool = countries.filter(function (c) {
      return contKeys.indexOf(c.continent) > -1 && c.tier <= unlocked[c.continent];
    });
    return { pool: pool, unlocked: unlocked };
  }

  // 색칠 맞히기 보기 5개 (같은 대륙 나라 우선)
  function nameOptions(target, countries, rng) {
    rng = rng || Math.random;
    var same = shuffle(countries.filter(function (c) {
      return c.continent === target.continent && c.iso !== target.iso;
    }), rng);
    var others = shuffle(countries.filter(function (c) { return c.continent !== target.continent; }), rng);
    var picks = same.concat(others).slice(0, 4).map(function (c) { return c.name; });
    return shuffle([target.name].concat(picks), rng);
  }

  // 문제 하나 생성
  function makeQuestion(opts) {
    var rng = opts.rng || Math.random;
    var recent = opts.recent || [];
    var r = poolFor(opts.countries, opts.m, opts.contKeys);
    var fresh = r.pool.filter(function (c) { return recent.indexOf(c.iso) === -1; });
    var candidates = fresh.length ? fresh : r.pool;
    var target = P.weightedPick(candidates, function (c) { return P.weight(opts.m, c.iso); }, rng);

    var types = ["stage", "name"];
    if (r.unlocked[target.continent] >= 2) types.push("direct");
    var type = types[Math.floor(rng() * types.length)];

    var q = { country: target, type: type };
    if (type === "name") q.options = nameOptions(target, opts.countries, rng);
    return q;
  }

  var api = { POINTS: POINTS, tierLists: tierLists, unlockedByContinent: unlockedByContinent,
              poolFor: poolFor, nameOptions: nameOptions, makeQuestion: makeQuestion };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.MQLogic = api;
})(this);
