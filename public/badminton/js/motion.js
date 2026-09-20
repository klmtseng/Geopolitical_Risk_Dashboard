// Frame-differencing motion field, shared by the shuttle tracker and the
// racket-head refinement.
//
// Why frame differencing rather than a neural detector: a shuttlecock is ~15px
// across, travels up to 400 km/h, and is heavily motion-blurred. Generic
// object detectors (YOLO on COCO, MediaPipe object detector) have no such
// class and miss it entirely; a purpose-built model (TrackNet) is ~30 MB and
// does not run at 30 fps in a browser. Motion is the signal that is actually
// available in real time, so we use it and gate it hard.
//
// Two masks are produced per frame:
//   maskNow — |f(t) - f(t-1)| : everything that moved, used for racket energy
//   maskNew — maskNow AND NOT |f(t-1) - f(t-2)| : pixels the object has *just*
//             entered, i.e. its current position with no one-frame lag

export class MotionField {
  constructor(targetWidth = 208) {
    this.targetWidth = targetWidth;
    this.w = 0; this.h = 0;
    this.canvas = null;
    this.ctx = null;
    this.gray = null; this.prev = null; this.prev2 = null;
    this.maskNow = null; this.maskNew = null;
    this.ready = false;
  }

  _resize(w, h) {
    this.w = w; this.h = h;
    const make = () => (typeof OffscreenCanvas !== 'undefined'
      ? new OffscreenCanvas(w, h)
      : Object.assign(document.createElement('canvas'), { width: w, height: h }));
    this.canvas = make();
    this.canvas.width = w; this.canvas.height = h;
    this.ctx = this.canvas.getContext('2d', { willReadFrequently: true });
    const n = w * h;
    this.gray = new Uint8ClampedArray(n);
    this.prev = new Uint8ClampedArray(n);
    this.prev2 = new Uint8ClampedArray(n);
    this.maskNow = new Uint8Array(n);
    this.maskNew = new Uint8Array(n);
    this.ready = false;
    this.frames = 0;
  }

  /**
   * @param {HTMLVideoElement} source unrotated video element
   * @param {number} threshold 6..40, exposed as the "sensitivity" slider
   */
  update(source, threshold) {
    const vw = source.videoWidth, vh = source.videoHeight;
    if (!vw || !vh) return false;
    const w = this.targetWidth;
    const h = Math.max(2, Math.round((w * vh) / vw));
    if (w !== this.w || h !== this.h) this._resize(w, h);

    this.ctx.drawImage(source, 0, 0, w, h);
    const img = this.ctx.getImageData(0, 0, w, h).data;

    const tmp = this.prev2;
    this.prev2 = this.prev;
    this.prev = this.gray;
    this.gray = tmp;

    const g = this.gray, p1 = this.prev, p2 = this.prev2;
    const now = this.maskNow, fresh = this.maskNew;
    const n = w * h;
    for (let i = 0, j = 0; i < n; i++, j += 4) {
      // Rec.601 luma, integer-ish for speed.
      g[i] = (img[j] * 77 + img[j + 1] * 150 + img[j + 2] * 29) >> 8;
    }

    this.frames++;
    if (this.frames < 3) { now.fill(0); fresh.fill(0); return false; }

    for (let i = 0; i < n; i++) {
      const d1 = Math.abs(g[i] - p1[i]);
      const d2 = Math.abs(p1[i] - p2[i]);
      const a = d1 > threshold ? 1 : 0;
      now[i] = a;
      fresh[i] = a && d2 <= threshold ? 1 : 0;
    }
    this.ready = true;
    return true;
  }

  /** Sum of motion inside a normalised-radius disc — used to pick the racket arm. */
  energyAt(nx, ny, nr, mask = this.maskNow) {
    if (!this.ready) return 0;
    const { w, h } = this;
    const cx = nx * w, cy = ny * h, r = Math.max(1, nr * w);
    const x0 = Math.max(0, Math.floor(cx - r)), x1 = Math.min(w - 1, Math.ceil(cx + r));
    const y0 = Math.max(0, Math.floor(cy - r)), y1 = Math.min(h - 1, Math.ceil(cy + r));
    let sum = 0;
    for (let y = y0; y <= y1; y++) {
      const row = y * w;
      for (let x = x0; x <= x1; x++) {
        const dx = x - cx, dy = y - cy;
        if (dx * dx + dy * dy <= r * r && mask[row + x]) sum++;
      }
    }
    return sum;
  }
}

/**
 * Connected components over a binary mask, 8-connectivity, iterative flood fill.
 * Returns blobs in normalised coordinates.
 */
export function findBlobs(mask, w, h, { minArea = 2, maxArea = 400, maxBlobs = 2000 } = {}) {
  const seen = new Uint8Array(w * h);
  const stack = new Int32Array(w * h);
  const blobs = [];
  for (let i = 0; i < w * h; i++) {
    if (!mask[i] || seen[i]) continue;
    let sp = 0;
    stack[sp++] = i;
    seen[i] = 1;
    let area = 0, sx = 0, sy = 0;
    let minX = w, maxX = -1, minY = h, maxY = -1;
    while (sp > 0) {
      const idx = stack[--sp];
      const x = idx % w, y = (idx / w) | 0;
      area++; sx += x; sy += y;
      if (x < minX) minX = x; if (x > maxX) maxX = x;
      if (y < minY) minY = y; if (y > maxY) maxY = y;
      if (area > maxArea * 4) break; // runaway blob (a body) — stop early
      for (let dy = -1; dy <= 1; dy++) {
        const ny = y + dy;
        if (ny < 0 || ny >= h) continue;
        for (let dx = -1; dx <= 1; dx++) {
          const nx = x + dx;
          if (nx < 0 || nx >= w) continue;
          const nidx = ny * w + nx;
          if (mask[nidx] && !seen[nidx]) { seen[nidx] = 1; stack[sp++] = nidx; }
        }
      }
    }
    if (area < minArea || area > maxArea) continue;
    const bw = maxX - minX + 1, bh = maxY - minY + 1;
    blobs.push({
      x: sx / area / w,
      y: sy / area / h,
      area,
      bw: bw / w,
      bh: bh / h,
      pxW: bw,
      pxH: bh,
      fill: area / (bw * bh),
    });
    if (blobs.length >= maxBlobs) break;
  }
  return blobs;
}
