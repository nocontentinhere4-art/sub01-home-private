// Tokyo daylight follows the same simulation clock as his life and windows.
const smooth = (a, b, value) => {
  const x = Math.max(0, Math.min(1, (value - a) / (b - a)));
  return x * x * (3 - 2 * x);
};
export function homeLighting(timestamp) {
  const hour = (((timestamp / 3600 + 9) % 24) + 24) % 24;
  const angle = ((hour - 6) / 12) * Math.PI;
  const elevation = Math.sin(angle);
  const daylight = smooth(-0.08, 0.2, elevation);
  const sun = Math.max(0, elevation);
  return {
    hour,
    daylight,
    sunIntensity: 3.2 * sun,
    hemisphere: 0.08 + 0.32 * daylight,
    environment: 0.08 + 0.57 * daylight,
    sunPosition: [-14 * Math.cos(angle), 3 + 15 * sun, 12 * sun],
    sunColor: sun < 0.35 ? "#ffba7b" : "#ffead0",
    sky: daylight < 0.05 ? "#172335" : daylight < 0.7 ? "#ba9286" : "#bcc8ce",
  };
}
