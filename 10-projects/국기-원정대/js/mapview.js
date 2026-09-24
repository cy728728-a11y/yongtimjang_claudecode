/* 지도 퀴즈 세계지도 렌더링 (d3-geo + topojson) */
(function (root) {
  "use strict";
  var W = 800, H = 500;
  var HIT_PX = 22;   // 작은 나라 터치 반지름 (화면 px)
  var PIN_PX = 5;    // 작은 나라 점 반지름 (화면 px)
  var LABEL_PX = 14; // 이름표 글자 크기 (화면 px)
  var SMALL_PX = 14; // 이보다 작게 보이는 나라는 점 추가

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
    var gLand = layer.append("g");
    var gDots = layer.append("g");
    var gLabels = layer.append("g");
    var tap = null, path = null, k = 1;

    // viewBox 1단위가 화면에서 몇 px 인지
    function screenScale() {
      var w = svgEl.getBoundingClientRect().width;
      return w > 0 ? w / W : 1;
    }
    function px(v) { return v / (screenScale() * k); }

    function resize() {
      gDots.selectAll("circle.mq-hit").attr("r", px(HIT_PX));
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
        .on("click", fire);

      // 화면에서 너무 작은 문제 나라는 점 + 넓은 터치 영역
      var s = screenScale();
      var small = features.filter(function (f) {
        if (!opts.isQuiz(f.properties.iso)) return false;
        var b = path.bounds(f);
        if (!isFinite(b[0][0])) return false;
        var c = path.centroid(f);
        if (!(c[0] >= 0 && c[0] <= W && c[1] >= 0 && c[1] <= H)) return false;
        return (b[1][0] - b[0][0]) * s < SMALL_PX && (b[1][1] - b[0][1]) * s < SMALL_PX;
      });
      var dots = gDots.selectAll("g.mq-dot").data(small, function (f) { return f._i; });
      dots.exit().remove();
      var enter = dots.enter().append("g").attr("class", "mq-dot");
      enter.append("circle").attr("class", "mq-hit");
      enter.append("circle").attr("class", "mq-pin");
      gDots.selectAll("g.mq-dot")
        .attr("transform", function (f) { return "translate(" + path.centroid(f) + ")"; })
        .on("click", fire);
      resize();
    }

    // iso 에 해당하는 나라 모양 + 점
    function nodesFor(iso) {
      var match = function (f) { return f.properties.iso === iso; };
      return gLand.selectAll("path").filter(match).nodes()
        .concat(gDots.selectAll("g.mq-dot").filter(match).nodes());
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
