/* 지도 퀴즈 진행 기록 저장소: 아티팩트 db (여러 기기 공유) + localStorage 사본 */
(function (root) {
  "use strict";
  var LS_KEY = "mq-progress-v1";

  // localStorage 사본 한 칸 읽기: 새 형식 {m, updatedAt} / 옛 형식 {iso: 숙련도}
  function lsEntry(v) {
    if (v && typeof v.m === "object" && v.m) return { m: v.m, t: v.updatedAt || 0 };
    return { m: v || {}, t: 0 };
  }

  function isDenied(e) { return e && e.code === "invalid_argument"; }

  function createStore(opts) {
    var db = opts.db || null;
    var storage = opts.storage || null;
    var now = opts.now || function () { return Date.now(); };
    var cache = {};
    var times = {};   // 플레이어별 기록 시각 (사본·db 중 더 새것 고르기용)
    var chains = {};

    function lsRead() {
      if (!storage) return {};
      try { return JSON.parse(storage.getItem(LS_KEY)) || {}; } catch (e) { return {}; }
    }
    // 불러온 플레이어 칸만 새 형식으로 갱신 (다른 칸은 그대로)
    function lsWrite() {
      if (!storage) return;
      try {
        var all = lsRead();
        Object.keys(cache).forEach(function (k) { all[k] = { m: cache[k], updatedAt: times[k] || 0 }; });
        storage.setItem(LS_KEY, JSON.stringify(all));
      } catch (e) { /* 저장 공간 없음 → 무시 */ }
    }

    var store = {
      mode: db ? "db" : "local",

      // 플레이어 기록 불러오기: db 와 localStorage 사본 중 더 새것 (다시 불러오기에도 사용)
      load: function (keys) {
        var local = lsRead();
        return Promise.all(keys.map(function (k) {
          var lc = lsEntry(local[k]);
          function useLocal() { cache[k] = Object.assign({}, lc.m); times[k] = lc.t; }
          if (!db || store.mode === "local") { useLocal(); return Promise.resolve(); }
          // 저장 중인 쓰기가 끝난 뒤 읽어야 방금 기록이 사라지지 않음
          return (chains[k] || Promise.resolve()).then(function () {
            return db.doc("progress/" + k).get();
          }).then(function (snap) {
            var body = snap.exists ? snap.data() : null;
            if (body && body.m && (body.updatedAt || 0) >= lc.t) {
              cache[k] = Object.assign({}, body.m);
              times[k] = body.updatedAt || 0;
            } else {
              useLocal();
            }
          }).catch(function (e) {
            console.warn("[MQStore] 불러오기 실패", k, e && e.code);
            useLocal();
          });
        })).then(lsWrite);
      },

      get: function (key) { return cache[key] || {}; },

      // 저장: 캐시·localStorage 즉시, db 는 문서별로 하나씩
      //   iso 가 있으면 그 나라만 update (다른 기기 기록 보존), 문서가 없으면 전체 set
      //   set 까지 invalid_argument 면 쓰기 권한 없음 → 이번 방문은 로컬 모드
      save: function (key, m, iso) {
        var t = now();
        cache[key] = m;
        times[key] = t;
        lsWrite();
        if (!db || store.mode === "local") return Promise.resolve();
        var ref = db.doc("progress/" + key);
        function fullSet() { return ref.set({ m: m, updatedAt: t }); }
        var prev = chains[key] || Promise.resolve();
        chains[key] = prev.then(function () {
          if (store.mode === "local") return null;
          if (!iso) return fullSet();
          var patch = {};
          patch[iso] = m[iso];
          return ref.update({ m: patch, updatedAt: t }).catch(function (e) {
            if (isDenied(e)) return fullSet();
            throw e;
          });
        }).catch(function (e) {
          if (isDenied(e)) {
            store.mode = "local";
            console.warn("[MQStore] db 쓰기 권한 없음 → 이 기기에만 저장");
          } else {
            console.warn("[MQStore] 저장 실패", key, e && e.code);
          }
        });
        return chains[key];
      }
    };
    return store;
  }

  // 브라우저용: db 가능하면 db, 아니면 localStorage 만
  function connect() {
    var storage = null;
    try { storage = root.localStorage; storage.getItem(LS_KEY); } catch (e) { storage = null; }
    var use = root.claude && typeof root.claude.use === "function"
      ? root.claude.use("db") : Promise.resolve(null);
    return Promise.resolve(use).catch(function () { return null; }).then(function (db) {
      return createStore({ db: db, storage: storage });
    });
  }

  var api = { createStore: createStore, connect: connect, LS_KEY: LS_KEY };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.MQStore = api;
})(this);
