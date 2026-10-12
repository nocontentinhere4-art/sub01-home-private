import assert from "node:assert/strict";
import { homeLighting } from "../../web/house/lighting.mjs";
const at = (hour) =>
  homeLighting(Date.parse("2026-10-12T00:00:00Z") / 1000 + (hour - 9) * 3600);
const night = at(0),
  noon = at(12);
assert.equal(night.hour, 0);
assert.equal(noon.hour, 12);
assert.equal(night.sunIntensity, 0);
assert.ok(noon.sunIntensity > 3);
assert.ok(night.environment < noon.environment / 5);
assert.ok(night.hemisphere < noon.hemisphere / 4);
assert.ok(at(6).daylight < at(7).daylight);
assert.ok(at(17).daylight > at(18).daylight);
assert.ok(at(8).sunPosition[0] < 0 && at(16).sunPosition[0] > 0);
for (let h = 0; h < 24; h += 0.01) {
  const light = at(h);
  assert.ok(light.daylight >= 0 && light.daylight <= 1);
  assert.ok(light.sunPosition.every(Number.isFinite));
  assert.ok(Math.abs(light.sunIntensity - at(h + 0.01).sunIntensity) < 0.01);
}
console.log(
  "PASS: Tokyo day/night, sunrise/sunset, light bounds and continuous sunlight",
);
