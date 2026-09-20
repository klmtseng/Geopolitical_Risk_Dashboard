// Regression tests for the badminton app's analysis logic.
// Pure functions only — no DOM, no camera. Run with: npm run test:badminton
//
// These cover the parts that are easy to break and hard to eyeball: blob
// filtering, and the shuttle tracker's balance between locking onto a real
// flight and refusing to invent one out of noise.

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { findBlobs } from '../public/badminton/js/motion.js';
import { ShuttleTracker, estimateKmh } from '../public/badminton/js/shuttle.js';
import { OneEuro2D, dir, advance, dist } from '../public/badminton/js/geometry.js';

const W = 208, H = 117;
const AR = W / H;
const DT = 1 / 30;

/** Deterministic PRNG so the noise tests give the same answer every run. */
function mulberry32(seed) {
  return function () {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** A stand-in for MotionField holding discs of "motion" at the given points. */
function fakeField(points, radius = 1.6) {
  const maskNew = new Uint8Array(W * H);
  const maskNow = new Uint8Array(W * H);
  for (const p of points) {
    const cx = p.x * W, cy = p.y * H;
    for (let y = Math.floor(cy - radius); y <= Math.ceil(cy + radius); y++) {
      for (let x = Math.floor(cx - radius); x <= Math.ceil(cx + radius); x++) {
        if (x < 0 || y < 0 || x >= W || y >= H) continue;
        if (Math.hypot(x - cx, y - cy) > radius) continue;
        maskNew[y * W + x] = 1;
        maskNow[y * W + x] = 1;
      }
    }
  }
  return { ready: true, w: W, h: H, maskNew, maskNow, energyAt: () => 0 };
}

test('findBlobs locates isolated blobs in normalised coordinates', () => {
  const f = fakeField([{ x: 0.3, y: 0.4 }, { x: 0.7, y: 0.6 }]);
  const blobs = findBlobs(f.maskNew, W, H, { minArea: 2, maxArea: 100 })
    .sort((a, b) => a.x - b.x);
  assert.equal(blobs.length, 2);
  assert.ok(Math.abs(blobs[0].x - 0.3) < 0.02, `x=${blobs[0].x}`);
  assert.ok(Math.abs(blobs[0].y - 0.4) < 0.03, `y=${blobs[0].y}`);
});

test('findBlobs rejects body-sized regions', () => {
  const mask = new Uint8Array(W * H);
  for (let y = 20; y < 90; y++) for (let x = 40; x < 90; x++) mask[y * W + x] = 1;
  assert.equal(findBlobs(mask, W, H, { minArea: 2, maxArea: 100 }).length, 0);
});

test('ShuttleTracker follows a parabolic clear', () => {
  const t = new ShuttleTracker();
  let x = 0.12, y = 0.65, vx = 1.05, vy = -0.95;
  let locked = 0, firstLock = -1, truth = null;
  for (let i = 0; i < 26; i++) {
    x += vx * DT; y += vy * DT + 0.5 * 1.1 * DT * DT; vy += 1.1 * DT;
    truth = { x, y };
    if (t.update(fakeField([truth]), [], i * DT, AR, 1.5).active) {
      locked++;
      if (firstLock < 0) firstLock = i;
    }
  }
  assert.ok(locked >= 18, `locked ${locked}/26 frames`);
  assert.ok(firstLock <= 5, `first lock at frame ${firstLock}`);
  const end = t.trail.at(-1);
  assert.ok(Math.hypot(end.x - truth.x, end.y - truth.y) < 0.04, 'trail ends on the shuttle');
});

test('ShuttleTracker follows a fast drive past distractors', () => {
  const rnd = mulberry32(7);
  const t = new ShuttleTracker();
  let x = 0.02, y = 0.30;
  const vx = 4.2 / AR, vy = 0.35;
  let locked = 0, err = 1;
  for (let i = 0; i < 12; i++) {
    x += vx * DT; y += vy * DT;
    const noise = Array.from({ length: 3 }, () => ({ x: rnd(), y: rnd() }));
    const r = t.update(fakeField([{ x, y }, ...noise]), [], i * DT, AR, 1.5);
    if (r.active) { locked++; err = Math.hypot(r.pos.x - x, r.pos.y - y); }
  }
  assert.ok(locked >= 6, `locked ${locked}/12 frames`);
  assert.ok(err < 0.05, `followed the shuttle, not a distractor (err ${err.toFixed(3)})`);
});

test('ShuttleTracker rarely confirms a track from pure noise', () => {
  let active = 0, frames = 0, worst = 0;
  for (let seed = 1; seed <= 40; seed++) {
    const rnd = mulberry32(seed);
    const t = new ShuttleTracker();
    let run = 0;
    for (let i = 0; i < 40; i++) {
      const pts = Array.from({ length: 6 }, () => ({ x: rnd(), y: rnd() }));
      if (t.update(fakeField(pts), [], i * DT, AR, 1.5).active) run++;
    }
    active += run; frames += 40; worst = Math.max(worst, run);
  }
  const rate = active / frames;
  assert.ok(rate < 0.06, `noise confirmed on ${(rate * 100).toFixed(1)}% of frames (worst run ${worst}/40)`);
});

test('ShuttleTracker coasts through a short dropout', () => {
  const t = new ShuttleTracker();
  let x = 0.2, y = 0.5, survived = false;
  for (let i = 0; i < 24; i++) {
    x += 0.9 * DT; y -= 0.1 * DT;
    const occluded = i >= 14 && i <= 17;
    const r = t.update(occluded ? fakeField([]) : fakeField([{ x, y }]), [], i * DT, AR, 1.5);
    if (i === 17 && r.active) survived = true;
  }
  assert.ok(survived, 'track survives four dropped frames');
});

test('ShuttleTracker releases a shuttle that exits the frame', () => {
  const t = new ShuttleTracker();
  let x = 0.55, y = 0.4;
  for (let i = 0; i < 16; i++) {
    x += 0.06; y += 0.004;
    t.update(x < 1 ? fakeField([{ x, y }]) : fakeField([]), [], i * DT, AR, 1.5);
  }
  assert.equal(t.state, 'idle');
  assert.equal(t.trail.length, 0);
});

test('geometry helpers are aspect-corrected', () => {
  const ar = 16 / 9;
  const d = dir({ x: 0.5, y: 0.5 }, { x: 0.5, y: 0.4 }, ar);
  assert.ok(Math.abs(d.x) < 1e-9 && Math.abs(d.y + 1) < 1e-9, 'points straight up');
  assert.ok(Math.abs(d.len - 0.1) < 1e-9, 'length in frame-heights');
  const head = advance({ x: 0.5, y: 0.4 }, d, 0.17, ar);
  assert.ok(Math.abs(head.y - 0.23) < 1e-9, `extrapolated head y=${head.y}`);
  assert.ok(Math.abs(dist({ x: 0, y: 0 }, { x: 0.1, y: 0 }, ar) - 0.1 * ar) < 1e-9,
    'horizontal distance scales with aspect ratio');
});

test('OneEuro2D suppresses jitter at rest', () => {
  const rnd = mulberry32(3);
  const f = new OneEuro2D({ minCutoff: 1.6, beta: 0.03 });
  let out;
  for (let i = 0; i < 60; i++) out = f.filter({ x: 0.5 + (rnd() - 0.5) * 0.01, y: 0.5 }, i * DT);
  assert.ok(Math.abs(out.x - 0.5) < 0.004, `settled at ${out.x}`);
});

test('estimateKmh converts frame-heights per second to km/h', () => {
  assert.ok(Math.abs(estimateKmh(0.9, 4) - 12.96) < 1e-6);
  assert.equal(estimateKmh(5, 0), null);
});
