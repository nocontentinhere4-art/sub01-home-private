// Walkable surface inside the terrace rails, with a narrow entrance throat.
export function terraceAllows(x, z) {
  if (z <= 3.76) return true;
  if (z < 4.12) return x >= 1.63 && x <= 2.37;
  return x >= .91 && x <= 3.09 && z <= 5.64;
}
