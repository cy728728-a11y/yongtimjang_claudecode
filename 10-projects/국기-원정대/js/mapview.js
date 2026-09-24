/* 지도 퀴즈 세계지도 렌더링 (d3-geo + topojson) */
(function (root) {
  "use strict";
  var W = 800, H = 500;
  var HIT_PX = 22;   // 작은 나라 터치 반지름 (화면 px)
  var PIN_PX = 5;    // 작은 나라 점 반지름 (화면 px)
  var LABEL_PX = 14; // 이름표 글자 크기 (화면 px)
  var SMALL_PX = 14; // 이보다 작게 보이는 나라는 점 추가
  var KEEP_RATIO = 0.5; // 땅 보정: 누른 나라 중심 거리 < 작은 나라 거리 × 이 값이면 누른 나라 유지

  // 대륙별 확대 범위 [[서경, 남위], [동경, 북위]]
  var VIEWS = {
    europe:   { bounds: [[-25, 34], [45, 71]] },
    africa:   { bounds: [[-20, -36], [52, 38]] },
    asia:     { bounds: [[25, -11], [150, 55]] },
    oceania:  { bounds: [[110, -48], [-168, 2]], rotate: [-150, 0] },
    namerica: { bounds: [[-168, 7], [-52, 72]] },
    samerica: { bounds: [[-82, -56], [-34, 13]] }
  };

  // 경계 상자를 점 묶음으로 (fitExtent 용)
  function boxGeo(b) {
    var w = b[0][0], s = b[0][1], e = b[1][0], n = b[1][1];
    if (e < w) e += 360;
    var pts = [];
    for (var i = 0; i <= 4; i++) {
      var lon = w + (e - w) * i / 4;
      if (lon > 180) lon -= 360;
      pts.push([lon, s], [lon, n]);
    }
    return { type: "MultiPoint", coordinates: pts };
  }

  function create(svgEl, topo, opts) {
    var obj = topo.objects.countries;
    var features = root.topojson.feature(topo, obj).features;
    var nb = root.topojson.neighbors(obj.geometries);
    var byIso = {};
    features.forEach(function (f, i) {
      f._i = i;
      if (f.properties.iso) byIso[f.properties.iso] = f;
    });

    var svg = root.d3.select(svgEl).attr("viewBox", "0 0 " + W + " " + H);
    svg.selectAll("*").remove();
    var layer = svg.append("g").attr("class", "mq-layer");
    // 넓은 터치 원 (땅 아래)
    var gHits = layer.append("g");
    var gLand = layer.append("g");
    var gDots = layer.append("g");
    var gLabels = layer.append("g");
    var tap = null, path = null, k = 1;
    var smallNow = []; // 지금 화면의 작은 문제 나라 [{f, c:[x,y]}]

    // viewBox 1단위가 화면에서 몇 px 인지
    function screenScale() {
      var w = svgEl.getBoundingClientRect().width;
      return w > 0 ? w / W : 1;
    }
    function px(v) { return v / (screenScale() * k); }

    function resize() {
      gHits.selectAll("circle.mq-hit").attr("r", px(HIT_PX));
      gDots.selectAll("circle.mq-pin").attr("r", px(PIN_PX));
      gLabels.selectAll("text").style("font-size", px(LABEL_PX) + "px").style("stroke-width", px(3) + "px");
    }

    var zoom = root.d3.zoom()
      .scaleExtent([1, 8])
      .translateExtent([[0, 0], [W, H]])
      .on("zoom", function (ev) {
        k = ev.transform.k;
        layer.attr("transform", ev.transform);
        resize();
      });
    svg.call(zoom);

    function fire(ev, f) { if (tap) tap(f, ev); }

    function dist(a, b) { var dx = a[0] - b[0], dy = a[1] - b[1]; return Math.sqrt(dx * dx + dy * dy); }

    // 누른 지점에서 터치 반지름(화면 22px) 안의 가장 가까운 작은 나라 (없으면 null)
    function nearestSmall(ev) {
      if (!smallNow.length) return null;
      var pt = root.d3.pointer(ev, layer.node());
      var r = px(HIT_PX), best = null, bestD = Infinity;
      smallNow.forEach(function (d) {
        var dd = dist(d.c, pt);
        if (dd <= r && dd < bestD) { bestD = dd; best = d.f; }
      });
      return best;
    }

    // 나라의 대표 중심점: 가장 큰 조각의 중심 (프랑스처럼 먼 해외 영토가 있어도 본토 기준), 화면마다 캐시
    var mainC = {};
    function mainCentroid(f) {
      if (mainC[f._i]) return mainC[f._i];
      var g = f.geometry, c = path.centroid(f);
      if (g && g.type === "MultiPolygon") {
        var bestA = -1;
        g.coordinates.forEach(function (poly) {
          var part = { type: "Polygon", coordinates: poly };
          var a = path.area(part);
          if (a > bestA) { bestA = a; c = path.centroid(part); }
        });
      }
      mainC[f._i] = c;
      return c;
    }

    // 땅을 눌렀을 때: 그 나라가 작은 나라가 아니고 터치 반지름 안에 작은 나라가 있으면 작은 나라로 보정
    // (터치 원이 땅 아래라 이웃 땅에 가려지는 부분 보완)
    // 단, 누른 곳이 누른 나라 중심에 훨씬 가까우면(작은 나라까지 거리의 절반 미만) 그 나라 그대로
    //   → 점이 빽빽한 세계지도에서도 큰 나라 가운데는 항상 누를 수 있음
    function fireLand(ev, f) {
      var isSmall = smallNow.some(function (d) { return d.f === f; });
      var s = isSmall ? null : nearestSmall(ev);
      if (s) {
        var pt = root.d3.pointer(ev, layer.node());
        var sc = path.centroid(s), fc = mainCentroid(f);
        var dS = dist(sc, pt);
        var dF = isFinite(fc[0]) ? dist(fc, pt) : Infinity;
        if (dF < dS * KEEP_RATIO) s = null;
      }
      fire(ev, s || f);
    }

    // 바다 쪽 터치 원을 눌렀을 때: 원이 겹치면 가장 가까운 작은 나라
    function fireHit(ev, f) { fire(ev, nearestSmall(ev) || f); }

    function projectionFor(key) {
      var p;
      if (key === "world") {
        p = root.d3.geoNaturalEarth1().fitExtent([[8, 8], [W - 8, H - 8]], { type: "Sphere" });
      } else {
        var v = VIEWS[key];
        p = root.d3.geoMercator();
        if (v.rotate) p.rotate(v.rotate);
        p.fitExtent([[12, 12], [W - 12, H - 12]], boxGeo(v.bounds));
      }
      return p;
    }

    function show(key) {
      path = root.d3.geoPath(projectionFor(key));
      k = 1;
      svg.call(zoom.transform, root.d3.zoomIdentity);
      layer.attr("transform", null);
      clearAll();

      gLand.selectAll("path")
        .data(features, function (f) { return f._i; })
        .join("path")
        .attr("d", path)
        .attr("class", function (f) { return "mq-land" + (opts.isQuiz(f.properties.iso) ? " mq-quiz" : ""); })
        .on("click", fireLand);

      // 화면에서 너무 작은 문제 나라는 점 + 넓은 터치 영역
      var s = screenScale();
      var small = features.filter(function (f) {
        if (!opts.isQuiz(f.properties.iso)) return false;
        var b = path.bounds(f);
        if (!isFinite(b[0][0])) return false;
        var c = path.centroid(f);
        if (!(c[0] >= 0 && c[0] <= W && c[1] >= 0 && c[1] <= H)) return false;
        // 상자가 작거나, (대륙 확대 화면에서) 상자는 커도 땅 넓이가 작으면(바하마처럼 흩어진 섬) 점 추가
        //   세계지도는 이미 점이 빽빽해 넓이 기준은 빼고 확대(핀치)로 해결
        return ((b[1][0] - b[0][0]) * s < SMALL_PX && (b[1][1] - b[0][1]) * s < SMALL_PX) ||
          (key !== "world" && path.area(f) * s * s < SMALL_PX * SMALL_PX);
      });
      // 터치 원(gHits)은 땅 아래, 보이는 점(gDots)은 땅 위에 따로 그림
      //   점이 빽빽하면(세계지도·폰 화면) 터치 원이 이탈리아·튀르키예·케냐 같은 나라를 통째로 덮어 못 누르게 됨
      //   → 바다를 누르면 작은 나라, 땅을 누르면 그 땅 나라가 잡히게. 점(pin)은 보이기만 하고 터치는 안 받음
      [[gHits, "mq-hit"], [gDots, "mq-pin"]].forEach(function (pair) {
        var dots = pair[0].selectAll("g.mq-dot").data(small, function (f) { return f._i; });
        dots.exit().remove();
        dots.enter().append("g").attr("class", "mq-dot")
          .append("circle").attr("class", pair[1])
          .attr("pointer-events", pair[1] === "mq-pin" ? "none" : null);
        pair[0].selectAll("g.mq-dot")
          .attr("transform", function (f) { return "translate(" + path.centroid(f) + ")"; })
          .on("click", fireHit);
      });
      // 보정 대상: 세계지도는 모든 작은 나라, 대륙 확대 화면은 그 대륙의 작은 나라만
      //   (유럽 화면의 튀니지 점이 이탈리아 땅을 가져가지 않게)
      smallNow = small.filter(function (f) { return key === "world" || opts.contOf(f) === key; })
        .map(function (f) { return { f: f, c: path.centroid(f) }; });
      mainC = {};
      resize();
    }

    // iso 에 해당하는 나라 모양 + 점
    function nodesFor(iso) {
      var match = function (f) { return f.properties.iso === iso; };
      return gLand.selectAll("path").filter(match).nodes()
        .concat(gDots.selectAll("g.mq-dot").filter(match).nodes())
        .concat(gHits.selectAll("g.mq-dot").filter(match).nodes());
    }

    function mark(iso, cls) {
      if (!iso) return;
      nodesFor(iso).forEach(function (n) { n.classList.add(cls); });
    }

    function markContinent(key) {
      gLand.selectAll("path").filter(function (f) { return opts.contOf(f) === key; })
        .classed("mq-cont", true);
    }

    function label(iso, text, cls) {
      var f = byIso[iso];
      if (!f || !path) return;
      var c = path.centroid(f);
      if (!isFinite(c[0])) return;
      gLabels.append("text")
        .attr("class", "mq-label " + (cls || ""))
        .attr("x", c[0]).attr("y", c[1])
        .attr("dy", "-0.6em")
        .text(text);
      resize();
    }

    function clearLabels() { gLabels.selectAll("*").remove(); }

    function clearAll() {
      svg.selectAll(".mq-target,.mq-correct,.mq-wrong,.mq-cont,.mq-m1,.mq-m2,.mq-m3")
        .classed("mq-target mq-correct mq-wrong mq-cont mq-m1 mq-m2 mq-m3", false);
      clearLabels();
    }

    function setMastery(m) {
      Object.keys(m || {}).forEach(function (iso) {
        var lv = m[iso];
        if (lv >= 1 && lv <= 3 && opts.isQuiz(iso)) mark(iso, "mq-m" + lv);
      });
    }

    // 이웃 나라 (문제 나라 먼저)
    function neighborsOf(iso) {
      var f = byIso[iso];
      if (!f) return [];
      var list = nb[f._i].map(function (i) { return features[i].properties.iso; })
        .filter(function (x) { return x && x !== iso; });
      return list.filter(opts.isQuiz).concat(list.filter(function (x) { return !opts.isQuiz(x); }));
    }

    function nameOfIso(iso) { return byIso[iso] ? opts.nameOf(byIso[iso]) : iso; }

    return {
      show: show,
      onTap: function (fn) { tap = fn; },
      mark: mark,
      markContinent: markContinent,
      label: label,
      clearLabels: clearLabels,
      setMastery: setMastery,
      neighborsOf: neighborsOf,
      contOf: opts.contOf,
      nameOf: opts.nameOf,
      nameOfIso: nameOfIso
    };
  }

  root.MQMapView = { create: create, VIEWS: VIEWS };
})(this);
