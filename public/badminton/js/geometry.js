// Shared maths: landmark indices, vector helpers and the One Euro filter.
//
// Coordinate convention used across the whole app:
//   * every position is NORMALISED to the *unrotated* video frame, x,y in [0,1]
//   * only the renderer converts to canvas pixels (applying rotation / mirror)
//   * distances and angles must be computed in ASPECT-CORRECTED space, i.e.
//     with x multiplied by the frame aspect ratio, otherwise a 16:9 frame
//     squashes every angle. Helpers below take `ar` for that reason.

export const LM = {
  nose: 0,
  leftEye: 2, rightEye: 5,
  leftEar: 7, rightEar: 8,
  leftShoulder: 11, rightShoulder: 12,
  leftElbow: 13, rightElbow: 14,
  leftWrist: 15, rightWrist: 16,
  leftPinky: 17, rightPinky: 18,
  leftIndex: 19, rightIndex: 20,
  leftHip: 23, rightHip: 24,
  leftKnee: 25, rightKnee: 26,
  leftAnkle: 27, rightAnkle: 28,
  leftHeel: 29, rightHeel: 30,
  leftToe: 31, rightToe: 32,
};

// A deliberately trimmed skeleton: MediaPipe's own POSE_CONNECTIONS includes
// the face mesh, which is visual noise at badminton distances.
export const SKELETON = {
  torso: [
    [LM.leftShoulder, LM.rightShoulder],
    [LM.leftShoulder, LM.leftHip],
    [LM.rightShoulder, LM.rightHip],
    [LM.leftHip, LM.rightHip],
  ],
  armsLeft: [
    [LM.leftShoulder, LM.leftElbow],
    [LM.leftElbow, LM.leftWrist],
    [LM.leftWrist, LM.leftIndex],
  ],
  armsRight: [
    [LM.rightShoulder, LM.rightElbow],
    [LM.rightElbow, LM.rightWrist],
    [LM.rightWrist, LM.rightIndex],
  ],
  legsLeft: [
    [LM.leftHip, LM.leftKnee],
    [LM.leftKnee, LM.leftAnkle],
    [LM.leftAnkle, LM.leftToe],
  ],
  legsRight: [
    [LM.rightHip, LM.rightKnee],
    [LM.rightKnee, LM.rightAnkle],
    [LM.rightAnkle, LM.rightToe],
  ],
};

export const JOINTS = [
  LM.leftShoulder, LM.rightShoulder, LM.leftElbow, LM.rightElbow,
  LM.leftWrist, LM.rightWrist, LM.leftHip, LM.rightHip,
  LM.leftKnee, LM.rightKnee, LM.leftAnkle, LM.rightAnkle,
];

export const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
export const lerp = (a, b, t) => a + (b - a) * t;

/** Distance between two normalised points, corrected for frame aspect ratio. */
export function dist(a, b, ar = 1) {
  const dx = (a.x - b.x) * ar;
  const dy = a.y - b.y;
  return Math.hypot(dx, dy);
}

/** Unit vector a -> b in aspect-corrected space, returned in that same space. */
export function dir(a, b, ar = 1) {
  const dx = (b.x - a.x) * ar;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1e-6;
  return { x: dx / len, y: dy / len, len };
}

/** Walk `len` units along an aspect-corrected direction, back to normalised space. */
export function advance(p, d, len, ar = 1) {
  return { x: p.x + (d.x * len) / ar, y: p.y + d.y * len };
}

export const mid = (a, b) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });

class LowPass {
  constructor() { this.s = null; }
  filter(x, alpha) {
    this.s = this.s === null ? x : alpha * x + (1 - alpha) * this.s;
    return this.s;
  }
  get value() { return this.s; }
}

/**
 * One Euro filter — low lag at speed, low jitter at rest. Far better than a
 * fixed EMA for limbs that alternate between still and explosive.
 */
export class OneEuro {
  constructor({ minCutoff = 1.4, beta = 0.03, dCutoff = 1.0 } = {}) {
    this.minCutoff = minCutoff;
    this.beta = beta;
    this.dCutoff = dCutoff;
    this.x = new LowPass();
    this.dx = new LowPass();
    this.tPrev = null;
    this.xPrev = null;
  }
  static alpha(cutoff, dt) {
    const tau = 1 / (2 * Math.PI * cutoff);
    return 1 / (1 + tau / dt);
  }
  reset() { this.x = new LowPass(); this.dx = new LowPass(); this.tPrev = null; this.xPrev = null; }
  filter(value, tSec) {
    const dt = this.tPrev === null ? 1 / 30 : clamp(tSec - this.tPrev, 1 / 240, 0.25);
    this.tPrev = tSec;
    const rate = this.xPrev === null ? 0 : (value - this.xPrev) / dt;
    this.xPrev = value;
    const edx = this.dx.filter(rate, OneEuro.alpha(this.dCutoff, dt));
    const cutoff = this.minCutoff + this.beta * Math.abs(edx);
    return this.x.filter(value, OneEuro.alpha(cutoff, dt));
  }
}

/** One Euro applied to a 2D point. */
export class OneEuro2D {
  constructor(opts) { this.fx = new OneEuro(opts); this.fy = new OneEuro(opts); }
  reset() { this.fx.reset(); this.fy.reset(); }
  filter(p, tSec) { return { x: this.fx.filter(p.x, tSec), y: this.fy.filter(p.y, tSec) }; }
  retune(minCutoff, beta) {
    for (const f of [this.fx, this.fy]) { f.minCutoff = minCutoff; f.beta = beta; }
  }
}

/** Smoothing presets exposed as a single 0..4 slider in the UI. */
export const SMOOTH_PRESETS = [
  { label: '關閉', minCutoff: 1e6, beta: 0 },
  { label: '弱',   minCutoff: 3.0, beta: 0.05 },
  { label: '中',   minCutoff: 1.6, beta: 0.03 },
  { label: '強',   minCutoff: 0.9, beta: 0.015 },
  { label: '很強', minCutoff: 0.5, beta: 0.008 },
];
