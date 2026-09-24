/* 지도 퀴즈 세계지도 렌더링 (d3-geo + topojson) */
(function (root) {
  "use strict";
  var W = 800, H = 500;
  var HIT_PX = 22;   // 작은 나라 터치 반지름 (화면 px)
  var PIN_PX = 5;    // 작은 나라 점 반지름 (화면 px)
  var LABEL_PX = 14; // 이름표 글자 크기 (화면 px)
  var SMALL_PX = 14; // 이보다 작게 보이는 나라는 점 추가
  var STAR_PX = 12;  // 마스터 ⭐ 크기 (화면 px, 점 크기 정도)
  var KEEP_RATIO = 0.5; // 땅 보정: 누른 나라 중심 거리 < 작은 나라 거리 × 이 값이면 누른 나라 유지
  var CONT_LABEL_PX = 16; // 대륙 이름표 글자 크기 (화면 px)

  // 세계지도에서 대륙 이름표를 붙일 자리 [경도, 위도]
  //   유럽·아시아 이름표가 폰 화면에서 겹치지 않게 서로 떨어뜨림
  var CONT_POINTS = {
    europe: [2, 56], africa: [20, 6], asia: [105, 32],
    oceania: [134, -25], namerica: [-102, 45], samerica: [-60, -12]
  };

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
    var gStars = layer.append("g"); // 내 세계지도 ⭐ (숙련도 3)
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
      gStars.selectAll("text").style("font-size", px(STAR_PX) + "px");
      gLabels.selectAll("text").style("font-size", function () {
        // 대륙 이름표는 나라 이름표보다 크게
        return px(this.classList.contains("mq-label-cont") ? CONT_LABEL_PX : LABEL_PX) + "px";
      }).style("stroke-width", px(3) + "px");
    }

    var zoom = root.d3.zoom()
      .scaleExtent([1, 8])
      .translateExtent([[0, 0], [W, H]])
      .on("zoom", function (ev) {
        k = ev.transform.k;
        layer.attr("transform", ev.transform);
        resize();
      });
    // 두 번 탭(더블클릭) 확대는 끔: 아이들이 빠르게 두 번 누르면 지도가 튀어서
    svg.call(zoom).on("dblclick.zoom", null);

    // tap(보정된 나라, 이벤트, 실제로 누른 나라) — 세 번째 인자는 추가분(기존 호출과 호환)
    function fire(ev, f, raw) { if (tap) tap(f, ev, raw || f); }

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
      fire(ev, s || f, f);
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

    // iso 문자열 또는 나라 모양(feature) → feature (iso 없는 땅도 모양으로 지정 가능)
    function featOf(target) {
      if (!target) return null;
      return typeof target === "string" ? (byIso[target] || null) : target;
    }

    // 나라의 모양 + 점
    function nodesFor(feat) {
      var match = function (f) { return f._i === feat._i; };
      return gLand.selectAll("path").filter(match).nodes()
        .concat(gDots.selectAll("g.mq-dot").filter(match).nodes())
        .concat(gHits.selectAll("g.mq-dot").filter(match).nodes());
    }

    function mark(target, cls) {
      var feat = featOf(target);
      if (!feat) return;
      nodesFor(feat).forEach(function (n) { n.classList.add(cls); });
    }

    function markContinent(key) {
      gLand.selectAll("path").filter(function (f) { return opts.contOf(f) === key; })
        .classed("mq-cont", true);
    }

    // 이름표 위치: 본토(가장 큰 조각) 중심. 화면 밖이면 그 나라가 보이는 부분 안으로 당김
    //   (프랑스는 기아나 때문에 스페인 쪽으로, 러시아는 유럽 화면 밖으로 가던 문제)
    var LM_X = 40, LM_Y = 18; // 이름표가 화면 가장자리에서 잘리지 않게 여백
    function labelPoint(f) {
      var c = mainCentroid(f);
      if (!isFinite(c[0])) return null;
      if (c[0] >= 0 && c[0] <= W && c[1] >= 0 && c[1] <= H) return c;
      var b = path.bounds(f);
      var x0 = Math.max(b[0][0], LM_X), x1 = Math.min(b[1][0], W - LM_X);
      var y0 = Math.max(b[0][1], LM_Y), y1 = Math.min(b[1][1], H - LM_Y);
      if (x0 > x1 || y0 > y1) return c; // 화면에 안 보이는 나라: 원래 자리
      return [Math.max(x0, Math.min(x1, c[0])), Math.max(y0, Math.min(y1, c[1]))];
    }

    function label(target, text, cls) {
      var f = featOf(target);
      if (!f || !path) return;
      var c = labelPoint(f);
      if (!c) return;
      var t = gLabels.append("text")
        .attr("class", "mq-label " + (cls || ""))
        .attr("x", c[0]).attr("y", c[1])
        .attr("dy", "-0.6em")
        .text(text);
      resize();
      // 글자가 지도 가장자리에서 잘리면 안쪽으로 밀기 (러시아처럼 화면 끝에 걸친 나라)
      try {
        var bb = t.node().getBBox();
        var shift = 0;
        if (bb.x < 2) shift = 2 - bb.x;
        else if (bb.x + bb.width > W - 2) shift = W - 2 - (bb.x + bb.width);
        if (shift) t.attr("x", c[0] + shift);
      } catch (e) { /* 화면에 없는 svg → 측정 불가, 그대로 */ }
    }

    // 대륙 이름표 (세계지도에서 정답·오답 대륙 알려주기)
    function labelContinent(key, text, cls) {
      var at = CONT_POINTS[key];
      if (!at || !path) return;
      var p = path.projection()(at);
      if (!p || !isFinite(p[0])) return;
      gLabels.append("text")
        .attr("class", "mq-label mq-label-cont " + (cls || ""))
        .attr("x", p[0]).attr("y", p[1])
        .text(text);
      resize();
    }

    function clearLabels() { gLabels.selectAll("*").remove(); }

    function clearAll() {
      gStars.selectAll("*").remove();
      svg.selectAll(".mq-target,.mq-correct,.mq-wrong,.mq-cont,.mq-m1,.mq-m2,.mq-m3")
        .classed("mq-target mq-correct mq-wrong mq-cont mq-m1 mq-m2 mq-m3", false);
      clearLabels();
    }

    function setMastery(m) {
      Object.keys(m || {}).forEach(function (iso) {
        var lv = m[iso];
        if (lv >= 1 && lv <= 3 && opts.isQuiz(iso)) mark(iso, "mq-m" + lv);
        // 마스터(3) 나라는 이름표 자리에 작은 ⭐
        if (lv === 3 && byIso[iso] && path) {
          var c = labelPoint(byIso[iso]);
          if (c) gStars.append("text").attr("class", "mq-star").attr("x", c[0]).attr("y", c[1]).text("⭐");
        }
      });
      resize();
    }

    // 본토(가장 큰 조각)의 지리 중심 [경도, 위도] — 섬나라 가까운 나라 찾기용, 한 번만 계산
    var geoC = {};
    function mainGeoCentroid(f) {
      if (geoC[f._i]) return geoC[f._i];
      var g = f.geometry, c = root.d3.geoCentroid(f);
      if (g && g.type === "MultiPolygon") {
        var bestA = -1;
        g.coordinates.forEach(function (poly) {
          var part = { type: "Polygon", coordinates: poly };
          var a = root.d3.geoArea(part);
          if (a > bestA) { bestA = a; c = root.d3.geoCentroid(part); }
        });
      }
      geoC[f._i] = c;
      return c;
    }

    // 이웃 나라 (문제 나라 먼저). 국경을 맞댄 나라가 2개 미만(섬나라 등)이면
    //   본토 중심이 가까운 문제 나라로 3개까지 채움
    function neighborsOf(iso) {
      var f = byIso[iso];
      if (!f) return [];
      var list = nb[f._i].map(function (i) { return features[i].properties.iso; })
        .filter(function (x) { return x && x !== iso; });
      list = list.filter(opts.isQuiz).concat(list.filter(function (x) { return !opts.isQuiz(x); }));
      if (list.length < 2) {
        var me = mainGeoCentroid(f);
        var near = features.filter(function (g) {
          var x = g.properties.iso;
          return x && x !== iso && opts.isQuiz(x) && list.indexOf(x) === -1;
        }).map(function (g) {
          return { iso: g.properties.iso, d: root.d3.geoDistance(me, mainGeoCentroid(g)) };
        }).sort(function (a, b) { return a.d - b.d; });
        for (var i = 0; list.length < 3 && i < near.length; i++) list.push(near[i].iso);
      }
      return list;
    }

    function nameOfIso(iso) { return byIso[iso] ? opts.nameOf(byIso[iso]) : iso; }

    return {
      show: show,
      onTap: function (fn) { tap = fn; },
      mark: mark,
      markContinent: markContinent,
      label: label,
      labelContinent: labelContinent,
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
