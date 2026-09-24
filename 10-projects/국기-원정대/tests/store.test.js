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
        },
        // 실제 db 처럼: 문서 없으면 invalid_argument, 중첩 객체는 재귀 병합
        update: async (d) => {
          log.push("update " + p);
          await new Promise((r) => setTimeout(r, 5));
          if (!(p in docs)) throw { code: "invalid_argument" };
          docs[p] = deepMerge(docs[p], JSON.parse(JSON.stringify(d)));
        }
      };
    }
  };
}
function deepMerge(a, b) {
  const out = Object.assign({}, a);
  for (const k of Object.keys(b)) {
    const v = b[k];
    out[k] = v && typeof v === "object" && !Array.isArray(v) && out[k] && typeof out[k] === "object"
      ? deepMerge(out[k], v) : v;
  }
  return out;
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

test("db: 나라 하나만 update 로 병합 (다른 기기 기록을 덮어쓰지 않음)", async () => {
  const db = fakeDb();
  db.docs["progress/dad"] = { m: { fr: 2, jp: 1 }, updatedAt: 1 };
  const s = S.createStore({ db, storage: null });
  await s.load(["dad"]);
  // 다른 기기가 그 사이 de 를 기록
  db.docs["progress/dad"] = { m: { fr: 2, jp: 1, de: 3 }, updatedAt: 2 };
  await s.save("dad", { fr: 2, jp: 2 }, "jp");
  assert.deepStrictEqual(db.docs["progress/dad"].m, { fr: 2, jp: 2, de: 3 });
  assert.deepStrictEqual(db.log, ["update progress/dad"]);
  assert.strictEqual(s.mode, "db");
});

test("db: 문서가 없으면 update 실패 → 전체 set 으로 생성", async () => {
  const db = fakeDb();
  const s = S.createStore({ db, storage: null });
  await s.load(["mom"]);
  await s.save("mom", { kr: 1 }, "kr");
  assert.deepStrictEqual(db.docs["progress/mom"].m, { kr: 1 });
  assert.deepStrictEqual(db.log, ["update progress/mom", "start progress/mom", "end progress/mom"]);
  assert.strictEqual(s.mode, "db");
});

test("불러오기: localStorage 사본이 db 보다 새것이면 사본 사용", async () => {
  const storage = fakeStorage();
  storage.setItem("mq-progress-v1", JSON.stringify({ seoi: { m: { kr: 3 }, updatedAt: 2000 } }));
  const db = fakeDb();
  db.docs["progress/seoi"] = { m: { kr: 1 }, updatedAt: 1000 };
  const s = S.createStore({ db, storage });
  await s.load(["seoi"]);
  assert.deepStrictEqual(s.get("seoi"), { kr: 3 });
});

test("불러오기: db 가 더 새것이면 db 사용 (옛 형식 사본도 읽음)", async () => {
  const storage = fakeStorage();
  storage.setItem("mq-progress-v1", JSON.stringify({ seoi: { m: { kr: 3 }, updatedAt: 1000 }, dad: { jp: 2 } }));
  const db = fakeDb();
  db.docs["progress/seoi"] = { m: { kr: 1 }, updatedAt: 2000 };
  const s = S.createStore({ db, storage });
  await s.load(["seoi", "dad"]);
  assert.deepStrictEqual(s.get("seoi"), { kr: 1 });
  assert.deepStrictEqual(s.get("dad"), { jp: 2 });
});

test("쓰기 권한 없음(set 도 invalid_argument) → 이번 방문은 로컬 모드, 사본은 유지", async () => {
  const storage = fakeStorage();
  let writes = 0;
  const db = {
    doc: () => ({
      get: async () => ({ exists: false, data: () => undefined }),
      set: async () => { writes++; throw { code: "invalid_argument" }; },
      update: async () => { writes++; throw { code: "invalid_argument" }; }
    })
  };
  const s = S.createStore({ db, storage });
  await s.load(["seoha"]);
  await s.save("seoha", { cn: 1 }, "cn");
  assert.strictEqual(s.mode, "local");
  assert.strictEqual(writes, 2);
  await s.save("seoha", { cn: 2 }, "cn");
  assert.strictEqual(writes, 2); // 더는 db 에 쓰지 않음
  // 새로고침: db 는 비어 있어도 사본으로 이어감
  const s2 = S.createStore({ db, storage });
  await s2.load(["seoha"]);
  assert.deepStrictEqual(s2.get("seoha"), { cn: 2 });
});

test("다시 불러오기: 저장 중인 쓰기가 끝난 뒤 db 최신 기록을 읽음", async () => {
  const db = fakeDb();
  db.docs["progress/dad"] = { m: { fr: 1 }, updatedAt: 1 };
  const s = S.createStore({ db, storage: null });
  await s.load(["dad"]);
  db.docs["progress/dad"] = { m: { fr: 1, it: 3 }, updatedAt: 5 }; // 다른 기기
  s.save("dad", { fr: 2 }, "fr");
  await s.load(["dad"]);
  assert.deepStrictEqual(s.get("dad"), { fr: 2, it: 3 });
});
