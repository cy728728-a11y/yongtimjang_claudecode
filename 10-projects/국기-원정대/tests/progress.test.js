const test = require("node:test");
const assert = require("node:assert");
const P = require("../js/progress.js");

test("정답 +1, 오답 -1, 0~3 범위", () => {
  let m = {};
  m = P.applyResult(m, "fr", true);
  assert.strictEqual(P.level(m, "fr"), 1);
  m = P.applyResult(P.applyResult(P.applyResult(m, "fr", true), "fr", true), "fr", true);
  assert.strictEqual(P.level(m, "fr"), 3);
  m = P.applyResult({}, "de", false);
  assert.strictEqual(P.level(m, "de"), 0);
});

test("applyResult 는 원본을 바꾸지 않는다", () => {
  const m = { fr: 1 };
  P.applyResult(m, "fr", true);
  assert.deepStrictEqual(m, { fr: 1 });
});

test("가중치 = 4 - 숙련도", () => {
  assert.strictEqual(P.weight({}, "fr"), 4);
  assert.strictEqual(P.weight({ fr: 3 }, "fr"), 1);
});

test("단계 해금: 80% 이상이 숙련도 2+ 이면 다음 단계", () => {
  const tiers = { 1: ["a", "b", "c", "d", "e"], 2: ["f", "g"], 3: ["h"] };
  assert.strictEqual(P.unlockedTier({}, tiers), 1);
  assert.strictEqual(P.unlockedTier({ a: 2, b: 2, c: 2, d: 1 }, tiers), 1); // 3/5 = 60%
  assert.strictEqual(P.unlockedTier({ a: 2, b: 2, c: 3, d: 2 }, tiers), 2); // 4/5 = 80%
  assert.strictEqual(P.unlockedTier({ a: 2, b: 2, c: 3, d: 2, f: 2, g: 2 }, tiers), 3);
});

test("weightedPick 은 가중치 비율대로 뽑는다", () => {
  let seq = [0.1, 0.9];
  const rng = () => seq.shift();
  const items = ["x", "y"];
  const w = (it) => (it === "x" ? 1 : 3); // x: [0,0.25), y: [0.25,1)
  assert.strictEqual(P.weightedPick(items, w, rng), "x");
  assert.strictEqual(P.weightedPick(items, w, rng), "y");
});
