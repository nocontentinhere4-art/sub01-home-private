// The gait model, shared by the room (room.html drive(): the walk clip's rate and its stride share) and the first-person
// body of the house (web/house/first_person_body.mjs): how long a step is and how many a second at a walking speed, and
// how a walk clip authored at one speed plays at another without its planted foot sliding over the floor.
//
// A walking adult lengthens the step and quickens the cadence together, each about with the square root of speed
// (Grieve & Gear 1966; Sekiya & Nagasaki 1998: the "walk ratio", step length over cadence, stays near 0.0058-0.0065 m
// per step/min across speeds). WALK_RATIO is that ratio in m·s (step length / steps per second): at 1.2 m/s a young
// adult takes 1.94 steps/s of 0.62 m, at 0.6 m/s 1.37 steps/s of 0.44 m, at 0.3 m/s 0.97 steps/s of 0.31 m.
//
// A walk clip has one step length: its planted foot moves back under the hips at REF_SPEED, the clip's reference foot
// speed, for duration / steps seconds (room_walk 0.43-0.45 m, the ARDY walk 0.59 m, the UAL walk 0.54 m, the first-person
// capture 0.72 m: the reference speeds measured by room_build/kimodo_g12/walk_metrics.py and in
// docs/design/natural-motion/2026-10-23). Played faster or slower it keeps that step and
// changes only the cadence. So where the model's step is shorter than the clip's, the walk blends toward the standing
// pose by the stride share s = step / clipStep (the swing shrinks about linearly with s, and the arms and the bob with
// it, as a short-stepped walk does) and plays at v / (s · REF_SPEED): a foot that moves back at s · REF_SPEED · rate
// under hips that move forward at v stays still on the floor. Where the model's step is longer than the clip's the
// stride is not stretched (an additive extrapolation measured +6 % of stride for a 1.3 cm sole dip on room_walk) and
// the cadence rises instead, v / clipStep steps a second.
export const WALK_RATIO = 0.32;      // m·s: step length over cadence (steps/s)
export const SHARE_MIN = 0.3;        // the shortest stride share: below it the blend reads as marching in place
export const SHARE_FLOOR = 0.15;     // the smallest share the rate divides by (a walk still fading in from a pose)
export const RATE_MIN = 0.2, RATE_MAX = 3;   // the clip's playback rate: the floor the page had, and a cap for a fade's first frames
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));

// a young adult's gait at speed v (m/s): steps a second, and the step length (m)
export function gaitAt(v, ratio = WALK_RATIO) {
  const cadence = Math.sqrt(Math.max(0, v) / ratio);
  return {cadence, step: cadence * ratio};
}
// a walk clip's own step length (m): its authored travel speed over its loop, for the steps in the loop (2: left, right)
export function clipStep(refSpeed, duration, steps = 2) { return refSpeed * duration / Math.max(1, steps); }
// the stride share at speed v for a clip whose step is clipStepM: 1 at and above the speed where the model's step
// reaches the clip's (v = clipStep² / WALK_RATIO: room_walk 0.6 m/s, the ARDY walk 1.1 m/s), shorter strides below
export function strideShare(v, clipStepM, ratio = WALK_RATIO) {
  return clipStepM > 0 ? clamp(gaitAt(v, ratio).step / clipStepM, SHARE_MIN, 1) : 1;
}
// the clip's playback rate at speed v with the walk at share s of the blend: the planted foot stays put on the floor
export function clipRate(v, share, refSpeed) {
  return refSpeed > 0 ? clamp(v / (Math.max(SHARE_FLOOR, share) * refSpeed), RATE_MIN, RATE_MAX) : 1;
}
// the cadence the walk shows at speed v with the clip at share s: steps a second
export function cadenceOf(v, share, clipStepM) { return clipStepM > 0 ? v / (Math.max(SHARE_FLOOR, share) * clipStepM) : 0; }
