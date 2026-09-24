/* 지도 퀴즈 진행 기록 저장소: 아티팩트 db (여러 기기 공유) + localStorage 사본 */
(function (root) {
  "use strict";
  var LS_KEY = "mq-progress-v1";

  function createStore(opts) {
    var db = opts.db || null;
    var storage = opts.storage || null;
    var cache = {};
    var chains = {};

    function lsRead() {
      if (!storage) return {};
      try { return JSON.parse(storage.getItem(LS_KEY)) || {}; } catch (e) { return {}; }
    }
    function lsWrite() {
      if (!storage) return;
      try { storage.setItem(LS_KEY, JSON.stringify(cache)); } catch (e) { /* 저장 공간 없음 → 무시 */ }
    }

    return {
      mode: db ? "db" : "local",

      // 플레이어 기록 불러오기 (db 우선, 실패하면 localStorage 사본)
      load: function (keys) {
        var local = lsRead();
        if (!db) {
          keys.forEach(function (k) { cache[k] = local[k] || {}; });
          return Promise.resolve();
        }
        return Promise.all(keys.map(function (k) {
          return db.doc("progress/" + k).get().then(function (snap) {
            var body = snap.exists ? snap.data() : null;
            cache[k] = body && body.m ? Object.assign({}, body.m) : (local[k] || {});
          }).catch(function (e) {
            console.warn("[MQStore] 불러오기 실패", k, e && e.code);
            cache[k] = local[k] || {};
          });
        }));
      },

      get: function (key) { return cache[key] || {}; },

      // 저장: 캐시·localStorage 즉시, db 는 문서별로 하나씩
      save: function (key, m) {
        cache[key] = m;
        lsWrite();
        if (!db) return Promise.resolve();
        var prev = chains[key] || Promise.resolve();
        chains[key] = prev.then(function () {
          return db.doc("progress/" + key).set({ m: m, updatedAt: Date.now() });
        }).catch(function (e) {
          console.warn("[MQStore] 저장 실패", key, e && e.code);
        });
        return chains[key];
      }
    };
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
