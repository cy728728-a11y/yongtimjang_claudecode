const test = require("node:test");
const assert = require("node:assert");
const S = require("../js/store.js");

function fakeDb() {
  const docs = {};
  const log = [];
  return {
    docs, log,
    doc(p) {
      return {
        get: async () => ({ exists: p in docs, data: () => docs[p] }),
        set: async (d) => {
          log.push("start " + p);
          await new Promise((r) => setTimeout(r, 5));
          docs[p] = JSON.parse(JSON.stringify(d));
          log.push("end " + p);
        }
      };
    }
  };
}
function fakeStorage() {
  const s = {};
  return { getItem: (k) => (k in s ? s[k] : null), setItem: (k, v) => { s[k] = String(v); } };
}

test("db: 없는 문서는 빈 기록, 저장 후 새 저장소에서 다시 읽힌다", async () => {
  const db = fakeDb();
  const a = S.createStore({ db, storage: null });
  await a.load(["seoi"]);
  assert.deepStrictEqual(a.get("seoi"), {});
  await a.save("seoi", { fr: 2 });
  assert.deepStrictEqual(db.docs["progress/seoi"].m, { fr: 2 });
  const b = S.createStore({ db, storage: null });
  await b.load(["seoi"]);
  assert.deepStrictEqual(b.get("seoi"), { fr: 2 });
});

test("db: 같은 문서 쓰기는 하나씩 순서대로", async () => {
  const db = fakeDb();
  const s = S.createStore({ db, storage: null });
  await s.load(["dad"]);
  s.save("dad", { fr: 1 });
  await s.save("dad", { fr: 2 });
  assert.deepStrictEqual(db.log, ["start progress/dad", "end progress/dad", "start progress/dad", "end progress/dad"]);
  assert.deepStrictEqual(db.docs["progress/dad"].m, { fr: 2 });
});

test("db 없으면 localStorage 로 저장·복원", async () => {
  const storage = fakeStorage();
  const a = S.createStore({ db: null, storage });
  assert.strictEqual(a.mode, "local");
  await a.load(["mom"]);
  await a.save("mom", { jp: 3 });
  const b = S.createStore({ db: null, storage });
  await b.load(["mom"]);
  assert.deepStrictEqual(b.get("mom"), { jp: 3 });
});

test("db 읽기 실패해도 localStorage 사본으로 시작", async () => {
  const storage = fakeStorage();
  storage.setItem("mq-progress-v1", JSON.stringify({ seoha: { kr: 1 } }));
  const db = { doc: () => ({ get: async () => { throw { code: "unavailable" }; }, set: async () => {} }) };
  const s = S.createStore({ db, storage });
  await s.load(["seoha"]);
  assert.deepStrictEqual(s.get("seoha"), { kr: 1 });
});
