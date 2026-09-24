// Natural Earth 50m 나라 경계 → data/world.json (TopoJSON) 생성
import { existsSync, mkdirSync, readFileSync, writeFileSync, statSync } from "node:fs";
import mapshaper from "mapshaper";

const SRC_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson";
const RAW = "tools/.cache/ne50.geojson";
const SLIM = "tools/.cache/slim.geojson";
const OUT = "data/world.json";
// Natural Earth 대륙명 → 게임 대륙 키
const CONT = {
  "Europe": "europe", "Africa": "africa", "Asia": "asia", "Oceania": "oceania",
  "North America": "namerica", "South America": "samerica"
};

try {
  mkdirSync("tools/.cache", { recursive: true });
  mkdirSync("data", { recursive: true });

  // 1) 원본 다운로드 (캐시 있으면 생략)
  if (!existsSync(RAW)) {
    const res = await fetch(SRC_URL);
    if (!res.ok) throw new Error("다운로드 실패: HTTP " + res.status);
    writeFileSync(RAW, Buffer.from(await res.arrayBuffer()));
  }

  // 2) 속성 정리: 남극 제외, iso·cont·ko 만 남김
  const src = JSON.parse(readFileSync(RAW, "utf8"));
  const features = src.features
    .filter((f) => f.properties.CONTINENT !== "Antarctica")
    .map((f) => {
      const p = f.properties;
      const iso = p.ISO_A2_EH && p.ISO_A2_EH !== "-99" ? p.ISO_A2_EH.toLowerCase() : "";
      return {
        type: "Feature",
        geometry: f.geometry,
        properties: { iso: iso, cont: CONT[p.CONTINENT] || "", ko: p.NAME_KO || p.NAME || "" }
      };
    });
  writeFileSync(SLIM, JSON.stringify({ type: "FeatureCollection", features: features }));

  // 3) 단순화 + TopoJSON 변환
  await mapshaper.runCommands(
    `-i ${SLIM} name=countries -simplify 20% keep-shapes -o ${OUT} format=topojson quantization=100000 force`
  );
  console.log("완료:", OUT, Math.round(statSync(OUT).size / 1024) + "KB,", features.length + "개 나라");
} catch (err) {
  console.error("지도 빌드 실패:", err.message);
  process.exit(1);
}
