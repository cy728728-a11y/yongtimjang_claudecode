/* 지도 퀴즈 화면: 문제 3종 + 내 세계지도 */
(function (root) {
  "use strict";
  var D = root.MQData, L = root.MQLogic, P = root.MQProgress;
  var CONT_NAMES = {};
  D.CONTINENTS.forEach(function (c) { CONT_NAMES[c.key] = c.name; });
  var byIso = {};
  D.COUNTRIES.forEach(function (c) { byIso[c.iso] = c; });

  var topo = null, store = null, readyP = null, recent = [];

  // 받침 있으면 a, 없으면 b (예: 영국은 / 프랑스는)
  function josa(word, a, b) {
    var code = word.charCodeAt(word.length - 1) - 0xAC00;
    if (code < 0 || code > 11171) return b;
    return code % 28 ? a : b;
  }

  // 지도 파일 + 저장소 준비 (한 번만)
  function ready(playerKeys) {
    // 지도 라이브러리(d3·topojson)를 못 불러왔으면 바로 안내
    if (!root.d3 || !root.topojson) {
      return Promise.reject(new Error("지도 도구를 불러오지 못했어요. 인터넷 연결을 확인하고 새로고침해 주세요"));
    }
    if (!readyP) {
      readyP = Promise.all([
        fetch("data/world.json").then(function (r) {
          if (!r.ok) throw new Error("지도 파일을 못 불러왔어요 (" + r.status + ")");
          return r.json();
        }),
        root.MQStore.connect()
      ]).then(function (res) {
        topo = res[0];
        store = res[1];
        return store.load(playerKeys);
      }).catch(function (e) {
        readyP = null;
        throw e;
      });
    }
    return readyP;
  }

  function makeView(svgEl) {
    return root.MQMapView.create(svgEl, topo, {
      isQuiz: function (iso) { return !!byIso[iso]; },
      contOf: function (f) {
        var c = byIso[f.properties.iso];
        return (c ? c.continent : f.properties.cont) || null;
      },
      nameOf: function (f) {
        var c = byIso[f.properties.iso];
        return c ? c.name : (f.properties.ko || "이름 없는 땅");
      }
    });
  }

  function renderQuestion(card, ctx) {
    var q = L.makeQuestion({ countries: D.COUNTRIES, m: store.get(ctx.playerKey), contKeys: ctx.contKeys, recent: recent });
    recent.push(q.country.iso);
    if (recent.length > 6) recent.shift();
    var c = q.country;
    var tag = { stage: "지도에서 찾기", direct: "바로 찍기", name: "색칠된 나라" }[q.type];

    card.innerHTML =
      '<div class="mode-tag">' + tag + '</div>' +
      '<div class="turn-banner"><span class="picon">' + ctx.player.icon + '</span>' + ctx.player.name + '의 차례!</div>' +
      '<div class="mq-prompt" id="mqPrompt"></div>' +
      '<div class="mq-map"><svg id="mqSvg" role="img" aria-label="세계지도"></svg></div>' +
      '<div class="choices" id="choices"></div>' +
      '<div class="feedback" id="feedback"></div>' +
      '<div class="mq-review" id="mqReview" hidden></div>' +
      '<div class="score-board" id="scoreBoard"></div>';

    var view = makeView(card.querySelector("#mqSvg"));
    var promptEl = card.querySelector("#mqPrompt");
    var fb = card.querySelector("#feedback");
    var flagImg = '<img class="mq-flag" src="flags/' + c.iso + '.svg" alt="국기">';
    var nameEul = c.name + josa(c.name, "을", "를");
    var nameEun = c.name + josa(c.name, "은", "는");
    var points = 0, done = false, wrongIso = null;

    // 문제 끝: 점수·숙련도 반영 + 복습 표시
    function result(correct, userAnswer) {
      if (done) return;
      done = true;
      view.onTap(null);
      store.save(ctx.playerKey, P.applyResult(store.get(ctx.playerKey), c.iso, correct));

      fb.textContent = correct
        ? ctx.player.name + " 정답이에요! (+" + points + "pt)"
        : (points ? "대륙은 맞았어요! (+" + points + "pt) " : "아쉬워요. ") + "정답은 " + c.name + josa(c.name, "이에요", "예요") + ".";
      fb.className = "feedback " + (correct ? "correct" : "wrong");

      view.mark(c.iso, correct ? "mq-correct" : "mq-target");
      var nbs = view.neighborsOf(c.iso).slice(0, 3);
      // 틀리게 누른 나라는 "여긴 …" 이름표가 이미 있으니 겹치지 않게 건너뜀
      nbs.forEach(function (iso) { if (iso !== wrongIso) view.label(iso, view.nameOfIso(iso), "mq-label-soft"); });
      view.label(c.iso, c.name, "mq-label-main");

      var rv = card.querySelector("#mqReview");
      rv.innerHTML =
        '<div class="mq-review-title">📍 ' + c.name + ' · ' + CONT_NAMES[c.continent] + '</div>' +
        '<div>' + c.hint + '</div>' +
        (nbs.length ? '<div class="mq-nb">이웃 나라: ' + nbs.map(view.nameOfIso).join(" · ") + '</div>' : '');
      rv.hidden = false;

      ctx.onDone({ points: points, correct: correct, userAnswer: userAnswer, correctAnswer: c.name, country: c });
    }

    // 틀리게 누른 나라 표시
    function showWrongTap(f) {
      var iso = f.properties.iso;
      wrongIso = iso;
      view.mark(iso, "mq-wrong");
      view.label(iso, "여긴 " + view.nameOf(f), "mq-label-wrong");
    }

    if (q.type === "stage") {
      promptEl.innerHTML = flagImg + '<span><b>' + nameEun + '</b> 어느 대륙에 있을까요?<small>지도에서 대륙을 눌러보세요</small></span>';
      view.show("world");
      var step = "continent";
      view.onTap(function (f) {
        if (step === "continent") {
          var k = view.contOf(f);
          if (!k) return;
          step = "wait";
          var ok = k === c.continent;
          if (ok) points += L.POINTS.stageContinent;
          view.markContinent(c.continent);
          fb.textContent = ok
            ? "맞았어요! " + CONT_NAMES[k] + josa(CONT_NAMES[k], "이에요", "예요") + " (+" + L.POINTS.stageContinent + ")"
            : "아쉬워요. " + nameEun + " " + CONT_NAMES[c.continent] + "에 있어요";
          fb.className = "feedback " + (ok ? "correct" : "wrong");
          setTimeout(function () {
            view.show(c.continent);
            step = "country";
            promptEl.innerHTML = flagImg + '<span>이제 <b>' + nameEul + '</b> 찾아보세요!</span>';
            fb.textContent = "";
            fb.className = "feedback";
          }, 1200);
        } else if (step === "country") {
          var hit = f.properties.iso === c.iso;
          if (hit) points += L.POINTS.stageCountry;
          else showWrongTap(f);
          result(hit, hit ? c.name : view.nameOf(f));
        }
      });
    } else if (q.type === "direct") {
      promptEl.innerHTML = flagImg + '<span>세계지도에서 <b>' + nameEul + '</b> 바로 찾아보세요!<small>두 손가락(또는 마우스 휠)으로 확대할 수 있어요</small></span>';
      view.show("world");
      view.onTap(function (f) {
        var hit = f.properties.iso === c.iso;
        if (hit) points += L.POINTS.direct;
        else showWrongTap(f);
        result(hit, hit ? c.name : view.nameOf(f));
      });
    } else {
      promptEl.innerHTML = '<span>반짝이는 나라는 어디일까요?</span>';
      view.show(c.continent);
      view.mark(c.iso, "mq-target");
      var choicesEl = card.querySelector("#choices");
      q.options.forEach(function (opt, i) {
        var b = document.createElement("button");
        b.className = "choice";
        b.innerHTML = '<span class="letter">' + "ABCDE"[i] + '</span><span>' + opt + '</span>';
        b.addEventListener("click", function () {
          if (done) return;
          var hit = opt === c.name;
          if (hit) points += L.POINTS.name;
          choicesEl.querySelectorAll(".choice").forEach(function (x) {
            x.disabled = true;
            var t = x.querySelector("span:last-child").textContent;
            if (t === c.name) x.classList.add("correct");
            else if (x === b) x.classList.add("wrong");
            else x.classList.add("dim");
          });
          result(hit, opt);
        });
        choicesEl.appendChild(b);
      });
    }
  }

  // 내 세계지도: 숙련도만큼 색칠
  function renderAtlas(card, player, onBack) {
    var m = store.get(player.key);
    var counts = [0, 0, 0, 0];
    D.COUNTRIES.forEach(function (c) { counts[P.level(m, c.iso)]++; });
    var unlocked = L.unlockedByContinent(D.COUNTRIES, m, D.CONTINENTS.map(function (x) { return x.key; }));

    card.innerHTML =
      '<div class="mode-tag">' + player.icon + ' ' + player.name + '의 세계지도</div>' +
      '<div class="mq-atlas-stats">⭐ 마스터 <b>' + counts[3] + '</b> · 익히는 중 <b>' + (counts[1] + counts[2]) + '</b> · 아직 <b>' + counts[0] + '</b> <span>/ ' + D.COUNTRIES.length + '</span></div>' +
      '<div class="mq-map"><svg id="mqSvg" role="img" aria-label="내 세계지도"></svg></div>' +
      '<div class="mq-legend"><span><i class="lg0"></i>아직</span><span><i class="lg1"></i>1번</span><span><i class="lg2"></i>2번</span><span><i class="lg3"></i>⭐ 마스터</span></div>' +
      '<div class="score-board">' + D.CONTINENTS.map(function (ct) {
        return '<span class="score-chip">' + ct.icon + ' ' + ct.name + ' <span class="pts">' + unlocked[ct.key] + '단계</span></span>';
      }).join("") + '</div>' +
      '<div class="hint">나라를 누르면 이름이 보여요</div>' +
      '<button class="next-btn" id="mqBack">돌아가기</button>';

    var view = makeView(card.querySelector("#mqSvg"));
    view.show("world");
    view.setMastery(m);
    view.onTap(function (f) {
      view.clearLabels();
      view.label(f.properties.iso, view.nameOf(f), "mq-label-main");
    });
    card.querySelector("#mqBack").addEventListener("click", onBack);
  }

  root.MQMapQuiz = {
    ready: ready,
    renderQuestion: renderQuestion,
    renderAtlas: renderAtlas,
    storeMode: function () { return store ? store.mode : null; }
  };
})(this);
