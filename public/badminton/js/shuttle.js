// Shuttlecock tracker.
//
// Small-blob detection on the motion field, then multi-hypothesis tracking:
// every plausible blob seeds its own candidate track, and a track is only
// promoted to "the shuttle" once it has survived several consecutive frames of
// physically consistent motion. Committing to a single blob at cold start (the
// obvious design) fails in a real gym, where a moving shoe or a shirt fold is
// often the first blob in scan order and steals every other frame.
//
// Selectivity comes from three places, in order of importance:
//   1. the gate is a small FRACTION of the predicted step, not a fixed radius,
//      so a fast shuttle is allowed to travel far but must land near its own
//      linear prediction;
//   2. direction and speed may only change so much between frames;
//   3. a single dropped frame kills an unconfirmed hypothesis — a shuttle in
//      flight shows up on essentially every frame, so gappy evidence is noise.

import { findBlobs } from './motion.js';
import { clamp } from './geometry.js';

const GATE_BASE = 0.07;      // frame-heights; floor of the association gate
const GATE_BOOT = 0.34;      // gate on the step right after a hypothesis is born
const GATE_SPEED_K = 0.5;    // gate grows as a fraction of the predicted step
const GATE_MAX = 0.40;       // beyond this a gate stops being evidence
const CONFIRM_HITS = 5;      // consecutive detections before a hypothesis becomes "the shuttle".
                             // 4 lets ~13% of pure-noise frames through, 6 costs a
                             // visible chunk of every fast drive; 5 is the knee.      // consecutive detections before a hypothesis is the shuttle
const MAX_MISS = 9;          // frames a confirmed track may coast before dying
const MAX_HYPOS = 12;        // cap on simultaneous candidate tracks
const GRAVITY = 1.1;         // frame-heights / s^2; a gentle downward prior
const TURN_COS = Math.cos((45 * Math.PI) / 180);
const SPEED_RATIO = [0.45, 2.2];
const OUT_OF_FRAME = 0.06;   // margin beyond the frame edge before a track is released

let hypoSeq = 1;

class Hypothesis {
  constructor(pos) {
    this.id = hypoSeq++;
    this.pos = { x: pos.x, y: pos.y };
    this.vel = { x: 0, y: 0 };
    this.hits = 1;
    this.miss = 0;
    this.confirmed = false;
    this.trail = [];
  }

  predict(dt) {
    return {
      x: this.pos.x + this.vel.x * dt,
      y: this.pos.y + this.vel.y * dt + 0.5 * GRAVITY * dt * dt,
    };
  }

  gate(dt, ar) {
    if (this.hits < 2) return Math.min(GATE_MAX, GATE_BOOT * (1 + this.miss * 0.5));
    const step = Math.hypot(this.vel.x * ar, this.vel.y) * dt;
    return Math.min(GATE_MAX, (GATE_BASE + step * GATE_SPEED_K) * (1 + this.miss * 0.5));
  }

  /** Is the implied direction and speed change physically plausible? */
  consistent(c, dt, ar) {
    if (this.hits < 2) return true;   // no velocity yet to compare against
    const vx = ((c.x - this.pos.x) / dt) * ar;
    const vy = (c.y - this.pos.y) / dt;
    const nSpeed = Math.hypot(vx, vy);
    const oSpeed = Math.hypot(this.vel.x * ar, this.vel.y);
    if (oSpeed < 0.12 || nSpeed < 0.12) return true;  // near-stationary
    const ratio = nSpeed / oSpeed;
    if (ratio < SPEED_RATIO[0] || ratio > SPEED_RATIO[1]) return false;
    return (vx * this.vel.x * ar + vy * this.vel.y) / (nSpeed * oSpeed) >= TURN_COS;
  }

  absorb(meas, dt, tSec) {
    const vx = (meas.x - this.pos.x) / dt;
    const vy = (meas.y - this.pos.y) / dt;
    // The first measured step has no prior velocity to blend with; take it
    // whole, or the estimate starts at a fraction of the true speed and the
    // next gate comes out far too small.
    this.vel = this.hits < 2
      ? { x: vx, y: vy }
      : { x: this.vel.x * 0.3 + vx * 0.7, y: this.vel.y * 0.3 + vy * 0.7 };
    this.pos = { x: this.pos.x * 0.15 + meas.x * 0.85, y: this.pos.y * 0.15 + meas.y * 0.85 };
    this.hits++;
    this.miss = 0;
    if (this.confirmed) this.trail.push({ ...this.pos, t: tSec, measured: true });
  }

  coast(dt, tSec) {
    this.miss++;
    this.pos = this.predict(dt);
    this.vel.y += GRAVITY * dt;
    if (this.confirmed) this.trail.push({ ...this.pos, t: tSec, measured: false });
  }

  get offFrame() {
    const { x, y } = this.pos;
    return x < -OUT_OF_FRAME || x > 1 + OUT_OF_FRAME || y < -OUT_OF_FRAME || y > 1 + OUT_OF_FRAME;
  }

  speed(ar) { return Math.hypot(this.vel.x * ar, this.vel.y); }
}

export class ShuttleTracker {
  constructor() {
    this.hypos = [];
    this.confirmed = null;
    this.candidates = [];
    this.lastT = null;
    this.ar = 1;
  }

  reset() {
    this.hypos = [];
    this.confirmed = null;
    this.candidates = [];
  }

  /** Exposed for tests and the debug overlay. */
  get state() {
    if (this.confirmed) return 'tracking';
    return this.hypos.length ? 'tentative' : 'idle';
  }
  get pos() { return this.confirmed?.pos ?? null; }
  get trail() { return this.confirmed?.trail ?? []; }
  get vel() { return this.confirmed?.vel ?? { x: 0, y: 0 }; }
  get speed() { return this.confirmed ? this.confirmed.speed(this.ar) : 0; }

  /**
   * @param {MotionField} field
   * @param {Array} people tracked people, used to damp body-motion blobs
   * @param {number} tSec
   * @param {number} ar frame aspect ratio (w/h)
   * @param {number} trailSeconds
   */
  update(field, people, tSec, ar, trailSeconds = 1.5) {
    const dt = this.lastT === null ? 1 / 30 : clamp(tSec - this.lastT, 1 / 240, 0.2);
    this.lastT = tSec;
    this.ar = ar;
    if (!field.ready) return this.result();

    this.candidates = this._candidates(field, people, ar);

    // Confirmed track picks first, then the most-established hypotheses.
    this.hypos.sort((a, b) => (b.confirmed - a.confirmed) || (b.hits - a.hits));

    const claimed = new Set();
    const survivors = [];

    for (const h of this.hypos) {
      const pred = h.predict(dt);
      const gate = h.gate(dt, ar);
      let best = null, bestScore = Infinity;
      for (const c of this.candidates) {
        if (claimed.has(c)) continue;
        const d = Math.hypot((c.x - pred.x) * ar, c.y - pred.y);
        if (d > gate) continue;
        if (!h.consistent(c, dt, ar)) continue;
        const score = d + c.penalty * 0.05 + c.area * 0.0004;
        if (score < bestScore) { bestScore = score; best = c; }
      }

      if (best) {
        claimed.add(best);
        h.absorb(best, dt, tSec);
        survivors.push(h);
      } else if (h.confirmed) {
        h.coast(dt, tSec);
        if (h.miss <= MAX_MISS && !h.offFrame) survivors.push(h);
      }
      // An unconfirmed hypothesis that missed a frame is simply dropped.
    }

    // Promote the strongest qualifying hypothesis.
    if (!survivors.some((h) => h.confirmed)) {
      const ready = survivors.filter((h) => h.hits >= CONFIRM_HITS)
        .sort((a, b) => b.hits - a.hits)[0];
      if (ready) {
        ready.confirmed = true;
        ready.trail = [{ ...ready.pos, t: tSec, measured: true }];
      }
    }

    // Seed new hypotheses from whatever is left over.
    for (const c of this.candidates) {
      if (survivors.length >= MAX_HYPOS) break;
      if (claimed.has(c) || c.penalty) continue;
      survivors.push(new Hypothesis(c));
    }

    this.hypos = survivors;
    this.confirmed = survivors.find((h) => h.confirmed) ?? null;

    if (this.confirmed) {
      const cutoff = tSec - trailSeconds;
      const tr = this.confirmed.trail;
      while (tr.length && tr[0].t < cutoff) tr.shift();
    }

    return this.result();
  }

  _candidates(field, people, ar) {
    const { w, h, maskNew } = field;
    // A shuttle is a handful of pixels once the frame is downscaled to ~208px.
    const maxPx = Math.max(6, Math.round(w * 0.055));
    const blobs = findBlobs(maskNew, w, h, {
      minArea: 2,
      maxArea: Math.round(maxPx * maxPx * 0.9),
    });

    // Torso motion is the main false positive. Penalise (rather than reject)
    // blobs inside a player's core: the shuttle does pass in front of people.
    const cores = people.map((p) => ({
      x: p.anchor.x, y: p.anchor.y, rx: (p.scale * 1.15) / ar, ry: p.scale * 1.6,
    }));

    const out = [];
    for (const b of blobs) {
      const aspect = b.pxH > 0 ? b.pxW / b.pxH : 99;
      if (aspect > 3.4 || aspect < 0.29) continue;  // motion streaks and edges
      if (b.fill < 0.32) continue;                  // stringy noise
      if (b.pxW > maxPx || b.pxH > maxPx) continue;
      let penalty = 0;
      for (const c of cores) {
        const nx = (b.x - c.x) / c.rx, ny = (b.y - c.y) / c.ry;
        if (nx * nx + ny * ny < 1) { penalty = 1; break; }
      }
      out.push({ ...b, penalty });
    }
    return out;
  }

  result() {
    const c = this.confirmed;
    return {
      active: !!c,
      pos: c ? c.pos : null,
      vel: this.vel,
      speed: this.speed,
      trail: c ? c.trail : [],
      confidence: c ? clamp(1 - c.miss / MAX_MISS, 0, 1) : 0,
      candidates: this.candidates,
      hypotheses: this.hypos.length,
    };
  }
}

/**
 * Rough real-world speed. Calibration is a single scalar: how many metres the
 * frame height spans, derived from a player of known height. Depth changes
 * break it, so the reading is explicitly an estimate.
 */
export function estimateKmh(framesHeightsPerSec, frameHeightMeters) {
  if (!frameHeightMeters || frameHeightMeters <= 0) return null;
  return framesHeightsPerSec * frameHeightMeters * 3.6;
}
