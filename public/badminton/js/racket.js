// Racket estimation.
//
// There is no off-the-shelf detector for a badminton racket, and training one
// would need a labelled dataset. What we *do* have, for free, is the arm: the
// racket is a rigid extension of the forearm through the grip. So:
//
//   1. pick the racket arm  — the wrist with more sustained motion energy
//   2. extrapolate           — head = wrist + unit(wrist - elbow) * k * forearm
//   3. refine with motion    — the racket head is the fastest-moving thing in
//                              the frame after the shuttle; look for motion
//                              pixels in a wedge along the forearm direction
//                              and pull the estimate towards their centroid
//
// Step 3 is what makes it track a real swing rather than a stick glued to the
// arm. It degrades gracefully: no motion found, you still get the geometry.

import { LM, OneEuro2D, dist, dir, advance, clamp } from './geometry.js';

const WEDGE_DEG = 42;
const MIN_MOTION_PX = 5;

export class RacketEstimator {
  constructor() {
    this.perPerson = new Map(); // personId -> state
  }

  reset() { this.perPerson.clear(); }

  /** Drop per-person state for players who are no longer tracked. */
  prune(aliveIds) {
    for (const id of this.perPerson.keys()) {
      if (!aliveIds.has(id)) this.perPerson.delete(id);
    }
  }

  _state(id) {
    if (!this.perPerson.has(id)) {
      this.perPerson.set(id, {
        energyL: 0, energyR: 0, side: null,
        head: new OneEuro2D({ minCutoff: 2.4, beta: 0.06 }),
        trail: [],
        prevWrist: null,
      });
    }
    return this.perPerson.get(id);
  }

  /**
   * @returns {{side, wrist, elbow, head, dir, length, trail, refined}|null}
   */
  update(person, field, tSec, ar, { lengthFactor = 1.7, trailSeconds = 0.8, dtSec = 1 / 30 } = {}) {
    const st = this._state(person.id);
    const L = person.lms;
    const lw = L[LM.leftWrist], rw = L[LM.rightWrist];
    const le = L[LM.leftElbow], re = L[LM.rightElbow];
    if (!lw || !rw || !le || !re) return null;

    // --- 1. which arm holds the racket -----------------------------------
    const probe = person.scale * 0.55;
    const eL = field?.ready ? field.energyAt(lw.x, lw.y, probe / ar) : 0;
    const eR = field?.ready ? field.energyAt(rw.x, rw.y, probe / ar) : 0;
    st.energyL = st.energyL * 0.9 + eL * 0.1;
    st.energyR = st.energyR * 0.9 + eR * 0.1;
    if (st.side === null) {
      st.side = st.energyR >= st.energyL ? 'right' : 'left';
    } else {
      // hysteresis: only switch when the other arm is clearly busier
      const cur = st.side === 'right' ? st.energyR : st.energyL;
      const other = st.side === 'right' ? st.energyL : st.energyR;
      if (other > cur * 1.6 + 2) st.side = st.side === 'right' ? 'left' : 'right';
    }

    const wrist = st.side === 'right' ? rw : lw;
    const elbow = st.side === 'right' ? re : le;
    if ((wrist.visibility ?? 1) < 0.35 || (elbow.visibility ?? 1) < 0.35) return null;

    // --- 2. geometric extrapolation ---------------------------------------
    const d = dir(elbow, wrist, ar);
    const forearm = Math.max(d.len, person.scale * 0.45);
    const length = forearm * lengthFactor;
    let head = advance(wrist, d, length, ar);
    let refined = false;

    // --- 3. motion refinement ---------------------------------------------
    if (field?.ready) {
      const m = this._motionCentroid(field, wrist, d, length, ar);
      if (m && m.count >= MIN_MOTION_PX) {
        // Blend towards the motion centroid, but keep the direction sane by
        // re-projecting the blend back onto a plausible radius.
        const bx = head.x * 0.45 + m.x * 0.55;
        const by = head.y * 0.45 + m.y * 0.55;
        const bd = dir(wrist, { x: bx, y: by }, ar);
        const r = clamp(dist(wrist, { x: bx, y: by }, ar), length * 0.45, length * 1.45);
        head = advance(wrist, bd, r, ar);
        refined = true;
      }
    }

    head = st.head.filter(head, tSec);

    // --- trail --------------------------------------------------------------
    st.trail.push({ x: head.x, y: head.y, t: tSec });
    const cutoff = tSec - trailSeconds;
    while (st.trail.length && st.trail[0].t < cutoff) st.trail.shift();

    const swingSpeed = st.prevWrist
      ? dist(wrist, st.prevWrist, ar) / Math.max(dtSec, 1e-3)
      : 0;
    st.prevWrist = { x: wrist.x, y: wrist.y };

    return {
      side: st.side,
      wrist, elbow, head,
      dir: dir(wrist, head, ar),
      length: dist(wrist, head, ar),
      trail: st.trail,
      refined,
      swingSpeed,
    };
  }

  /** Motion centroid inside a wedge extending from the wrist along `d`. */
  _motionCentroid(field, wrist, d, length, ar) {
    const { w, h, maskNow } = field;
    const cx = wrist.x * w, cy = wrist.y * h;
    const rMin = length * 0.45 * h, rMax = length * 1.5 * h;
    const x0 = Math.max(0, Math.floor(cx - rMax)), x1 = Math.min(w - 1, Math.ceil(cx + rMax));
    const y0 = Math.max(0, Math.floor(cy - rMax)), y1 = Math.min(h - 1, Math.ceil(cy + rMax));
    // Direction is in aspect-corrected space; convert to pixel space.
    const dxp = d.x * h, dyp = d.y * h;
    const dn = Math.hypot(dxp, dyp) || 1;
    const ux = dxp / dn, uy = dyp / dn;
    const cosLimit = Math.cos((WEDGE_DEG * Math.PI) / 180);

    let sx = 0, sy = 0, count = 0;
    for (let y = y0; y <= y1; y++) {
      const row = y * w;
      for (let x = x0; x <= x1; x++) {
        if (!maskNow[row + x]) continue;
        const vx = x - cx, vy = y - cy;
        const r = Math.hypot(vx, vy);
        if (r < rMin || r > rMax) continue;
        if ((vx * ux + vy * uy) / (r || 1) < cosLimit) continue;
        // Weight by radius so the far end (the head) dominates the near end
        // (the forearm), which also moves.
        const wgt = r / rMax;
        sx += x * wgt; sy += y * wgt; count += wgt;
      }
    }
    if (count < MIN_MOTION_PX) return null;
    return { x: sx / count / w, y: sy / count / h, count };
  }
}
