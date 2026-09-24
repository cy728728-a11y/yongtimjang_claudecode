const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const D = require("../js/countries.js");

const FILE = path.join(__dirname, "..", "data", "world.json");

test("world.json 이 1.5MB 이하 TopoJSON 이다", () => {
  assert.ok(fs.existsSync(FILE), "npm run build:map 먼저 실행");
  assert.ok(fs.statSync(FILE).size < 1.5 * 1024 * 1024);
  const topo = JSON.parse(fs.readFileSync(FILE, "utf8"));
  assert.strictEqual(topo.type, "Topology");
  assert.ok(topo.objects.countries.geometries.length > 200);
});

test("105개 나라가 지도에 전부 있다", () => {
  const topo = JSON.parse(fs.readFileSync(FILE, "utf8"));
  const have = new Set(topo.objects.countries.geometries.map((g) => g.properties.iso));
  const missing = D.COUNTRIES.filter((c) => !have.has(c.iso)).map((c) => c.iso);
  assert.deepStrictEqual(missing, []);
});

test("속성은 iso·cont·ko 만 남긴다", () => {
  const topo = JSON.parse(fs.readFileSync(FILE, "utf8"));
  const g = topo.objects.countries.geometries.find((x) => x.properties.iso === "fr");
  assert.deepStrictEqual(Object.keys(g.properties).sort(), ["cont", "iso", "ko"]);
  assert.strictEqual(g.properties.cont, "europe");
});
