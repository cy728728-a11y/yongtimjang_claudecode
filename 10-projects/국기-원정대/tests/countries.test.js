const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const D = require("../js/countries.js");

const ROOT = path.join(__dirname, "..");

test("대륙별 나라 수가 CONTINENTS.count 와 같다", () => {
  assert.strictEqual(D.COUNTRIES.length, 105);
  D.CONTINENTS.forEach((c) => {
    const n = D.COUNTRIES.filter((x) => x.continent === c.key).length;
    assert.strictEqual(n, c.count, c.key);
  });
});

test("모든 나라에 iso·tier·hint 가 있다", () => {
  const seen = new Set();
  D.COUNTRIES.forEach((c) => {
    assert.match(c.iso, /^[a-z]{2}$/, c.name);
    assert.ok(!seen.has(c.iso), "중복 " + c.iso);
    seen.add(c.iso);
    assert.ok([1, 2, 3].includes(c.tier), c.name + " tier");
    assert.ok(c.hint && c.hint.length <= 45, c.name + " hint");
  });
});

test("대륙마다 1·2·3단계가 모두 있다", () => {
  D.CONTINENTS.forEach((ct) => {
    [1, 2, 3].forEach((t) => {
      assert.ok(D.COUNTRIES.some((c) => c.continent === ct.key && c.tier === t), ct.key + " " + t);
    });
  });
});

test("국기 파일이 전부 있다", () => {
  D.COUNTRIES.forEach((c) => {
    assert.ok(fs.existsSync(path.join(ROOT, "flags", c.iso + ".svg")), c.iso);
  });
});
