const test = require("node:test");
const assert = require("node:assert");
const D = require("../js/countries.js");
const L = require("../js/mapquiz-logic.js");

// 재현 가능한 난수
function seeded(seed) {
  return function () {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

test("처음엔 선택 대륙의 1단계 나라만 나온다", () => {
  const r = L.poolFor(D.COUNTRIES, {}, ["europe"]);
  assert.ok(r.pool.length > 0);
  assert.ok(r.pool.every((c) => c.continent === "europe" && c.tier === 1));
  assert.strictEqual(r.unlocked.europe, 1);
});

test("1단계 80% 숙련도 2+ 면 2단계 나라도 나온다", () => {
  const t1 = L.tierLists(D.COUNTRIES, "europe")[1];
  const m = {};
  t1.slice(0, Math.ceil(t1.length * 0.8)).forEach((iso) => (m[iso] = 2));
  const r = L.poolFor(D.COUNTRIES, m, ["europe"]);
  assert.strictEqual(r.unlocked.europe, 2);
  assert.ok(r.pool.some((c) => c.tier === 2));
  assert.ok(!r.pool.some((c) => c.tier === 3));
});

test("1단계에서는 바로 찍기가 안 나온다", () => {
  const rng = seeded(1);
  for (let i = 0; i < 200; i++) {
    const q = L.makeQuestion({ countries: D.COUNTRIES, m: {}, contKeys: ["asia", "africa"], rng });
    assert.notStrictEqual(q.type, "direct");
  }
});

test("2단계가 열린 대륙은 바로 찍기도 나온다", () => {
  const m = {};
  L.tierLists(D.COUNTRIES, "samerica")[1].forEach((iso) => (m[iso] = 2));
  const rng = seeded(2);
  const types = new Set();
  for (let i = 0; i < 200; i++) {
    types.add(L.makeQuestion({ countries: D.COUNTRIES, m, contKeys: ["samerica"], rng }).type);
  }
  assert.deepStrictEqual([...types].sort(), ["direct", "name", "stage"]);
});

test("색칠 맞히기 보기: 5개, 중복 없음, 정답 포함, 같은 대륙 우선", () => {
  const fr = D.COUNTRIES.find((c) => c.iso === "fr");
  const opts = L.nameOptions(fr, D.COUNTRIES, seeded(3));
  assert.strictEqual(opts.length, 5);
  assert.strictEqual(new Set(opts).size, 5);
  assert.ok(opts.includes("프랑스"));
  const europeNames = D.COUNTRIES.filter((c) => c.continent === "europe").map((c) => c.name);
  assert.ok(opts.every((n) => europeNames.includes(n)));
});

test("최근 나온 나라는 피한다 (풀이 충분할 때)", () => {
  const pool = L.poolFor(D.COUNTRIES, {}, ["europe"]).pool.map((c) => c.iso);
  const recent = pool.slice(0, pool.length - 1);
  const rng = seeded(4);
  for (let i = 0; i < 30; i++) {
    const q = L.makeQuestion({ countries: D.COUNTRIES, m: {}, contKeys: ["europe"], recent, rng });
    assert.strictEqual(q.country.iso, pool[pool.length - 1]);
  }
});
