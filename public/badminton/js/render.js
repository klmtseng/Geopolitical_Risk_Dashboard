// Canvas renderer. Everything upstream works in unrotated, normalised video
// coordinates; this module is the only place that knows about rotation,
// mirroring and pixels.

import { LM, SKELETON, JOINTS } from './geometry.js';

export class Renderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d', { alpha: false, desynchronized: true });
    this.rotate = 0;
    this.mirror = false;
    this.vw = 0; this.vh = 0;
  }

  /** Size the canvas from the source video plus the current rotation. */
  sync(video, rotate, mirror) {
    const vw = video.videoWidth, vh = video.videoHeight;
    if (!vw || !vh) return false;
    const swap = rotate === 90 || rotate === 270;
    const cw = swap ? vh : vw;
    const ch = swap ? vw : vh;
    if (this.canvas.width !== cw || this.canvas.height !== ch) {
      this.canvas.width = cw;
      this.canvas.height = ch;
    }
    this.rotate = rotate;
    this.mirror = mirror;
    this.vw = vw; this.vh = vh;
    return true;
  }

  /** Push the rotate/mirror transform; afterwards draw in VIDEO pixel space. */
  begin() {
    const ctx = this.ctx;
    ctx.save();
    ctx.translate(this.canvas.width / 2, this.canvas.height / 2);
    if (this.rotate) ctx.rotate((this.rotate * Math.PI) / 180);
    if (this.mirror) ctx.scale(-1, 1);
    ctx.translate(-this.vw / 2, -this.vh / 2);
  }

  end() { this.ctx.restore(); }

  clear(skeletonOnly) {
    const ctx = this.ctx;
    ctx.fillStyle = skeletonOnly ? '#000000' : '#050810';
    ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);
  }

  drawVideo(video) {
    this.ctx.drawImage(video, 0, 0, this.vw, this.vh);
  }

  /* ---------------- skeleton ---------------- */

  drawPerson(person, { thickness = 4, minVis = 0.35, showLabel = true } = {}) {
    const ctx = this.ctx;
    const { vw, vh } = this;
    const L = person.lms;
    const px = (i) => ({ x: L[i].x * vw, y: L[i].y * vh, v: L[i].visibility ?? 1 });
    // Scale line weight with the frame so a 1080p clip does not get hairlines.
    const unit = Math.max(vw, vh) / 720;
    const lw = thickness * unit;

    const groups = [
      [SKELETON.torso, person.color.line, 1.0],
      [SKELETON.armsLeft, person.color.line, 0.95],
      [SKELETON.armsRight, person.color.line, 0.95],
      [SKELETON.legsLeft, person.color.line, 0.9],
      [SKELETON.legsRight, person.color.line, 0.9],
    ];

    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    // Dark underlay keeps the skeleton readable over a bright gym floor.
    ctx.strokeStyle = 'rgba(0,0,0,.55)';
    ctx.lineWidth = lw + 2.5 * unit;
    for (const [bones] of groups) {
      for (const [a, b] of bones) {
        const pa = px(a), pb = px(b);
        if (pa.v < minVis || pb.v < minVis) continue;
        ctx.beginPath(); ctx.moveTo(pa.x, pa.y); ctx.lineTo(pb.x, pb.y); ctx.stroke();
      }
    }

    for (const [bones, color, alpha] of groups) {
      ctx.strokeStyle = color;
      ctx.globalAlpha = alpha;
      ctx.lineWidth = lw;
      for (const [a, b] of bones) {
        const pa = px(a), pb = px(b);
        if (pa.v < minVis || pb.v < minVis) continue;
        ctx.beginPath(); ctx.moveTo(pa.x, pa.y); ctx.lineTo(pb.x, pb.y); ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;

    // joints
    ctx.fillStyle = person.color.joint;
    for (const i of JOINTS) {
      const p = px(i);
      if (p.v < minVis) continue;
      ctx.beginPath(); ctx.arc(p.x, p.y, lw * 0.62, 0, Math.PI * 2); ctx.fill();
    }

    // head
    const nose = px(LM.nose);
    const lEar = px(LM.leftEar), rEar = px(LM.rightEar);
    if (nose.v >= minVis) {
      const r = Math.max(Math.hypot(lEar.x - rEar.x, lEar.y - rEar.y) * 0.85, lw * 2.4);
      ctx.strokeStyle = person.color.line;
      ctx.lineWidth = lw * 0.85;
      ctx.beginPath(); ctx.arc(nose.x, nose.y - r * 0.15, r, 0, Math.PI * 2); ctx.stroke();
    }

    if (showLabel) {
      const sh = px(LM.leftShoulder), sh2 = px(LM.rightShoulder);
      const cx = (sh.x + sh2.x) / 2;
      const cy = Math.min(sh.y, sh2.y) - 26 * unit;
      this._tag(cx, cy, person.color.name, person.color.line, unit);
    }
  }

  drawBodyTrail(points, color, unit = 1) {
    if (points.length < 2) return;
    const ctx = this.ctx;
    ctx.strokeStyle = color;
    ctx.globalAlpha = 0.5;
    ctx.lineWidth = 2 * unit;
    ctx.setLineDash([6 * unit, 6 * unit]);
    ctx.beginPath();
    points.forEach((p, i) => {
      const x = p.x * this.vw, y = p.y * this.vh;
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.globalAlpha = 1;
  }

  /* ---------------- racket ---------------- */

  drawRacket(r, color) {
    const ctx = this.ctx;
    const { vw, vh } = this;
    const unit = Math.max(vw, vh) / 720;
    const w = { x: r.wrist.x * vw, y: r.wrist.y * vh };
    const h = { x: r.head.x * vw, y: r.head.y * vh };
    const ang = Math.atan2(h.y - w.y, h.x - w.x);
    const shaftLen = Math.hypot(h.x - w.x, h.y - w.y);
    const headR = shaftLen * 0.33;

    // trail
    if (r.trail.length > 1) {
      ctx.lineCap = 'round';
      for (let i = 1; i < r.trail.length; i++) {
        const a = r.trail[i - 1], b = r.trail[i];
        const t = i / r.trail.length;
        ctx.strokeStyle = color;
        ctx.globalAlpha = 0.06 + t * 0.5;
        ctx.lineWidth = (1 + t * 3.2) * unit;
        ctx.beginPath();
        ctx.moveTo(a.x * vw, a.y * vh);
        ctx.lineTo(b.x * vw, b.y * vh);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    }

    // shaft
    ctx.strokeStyle = 'rgba(0,0,0,.5)';
    ctx.lineWidth = 4.5 * unit;
    ctx.beginPath(); ctx.moveTo(w.x, w.y); ctx.lineTo(h.x, h.y); ctx.stroke();
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.6 * unit;
    ctx.beginPath(); ctx.moveTo(w.x, w.y); ctx.lineTo(h.x, h.y); ctx.stroke();

    // oval head
    ctx.save();
    ctx.translate(h.x, h.y);
    ctx.rotate(ang);
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.6 * unit;
    ctx.globalAlpha = r.refined ? 1 : 0.55;
    ctx.beginPath();
    ctx.ellipse(headR * 0.55, 0, headR * 0.72, headR * 0.56, 0, 0, Math.PI * 2);
    ctx.stroke();
    // strings
    ctx.globalAlpha = (r.refined ? 0.45 : 0.25);
    ctx.lineWidth = 1 * unit;
    for (let k = -2; k <= 2; k++) {
      const off = (k / 2.6) * headR * 0.56;
      ctx.beginPath();
      ctx.moveTo(headR * 0.55 - headR * 0.6, off);
      ctx.lineTo(headR * 0.55 + headR * 0.6, off);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
    ctx.restore();
  }

  /* ---------------- shuttle ---------------- */

  drawShuttle(s, { now = 0, trailSeconds = 1.5 } = {}) {
    const ctx = this.ctx;
    const { vw, vh } = this;
    const unit = Math.max(vw, vh) / 720;

    if (s.trail.length > 1) {
      for (let i = 1; i < s.trail.length; i++) {
        const a = s.trail[i - 1], b = s.trail[i];
        const age = now - b.t;
        const t = Math.max(0, 1 - age / trailSeconds);
        ctx.strokeStyle = b.measured ? '#ffe066' : '#ffb870';
        ctx.globalAlpha = 0.1 + t * 0.85;
        ctx.lineWidth = (1.2 + t * 3.6) * unit;
        ctx.lineCap = 'round';
        ctx.setLineDash(b.measured ? [] : [4 * unit, 4 * unit]);
        ctx.beginPath();
        ctx.moveTo(a.x * vw, a.y * vh);
        ctx.lineTo(b.x * vw, b.y * vh);
        ctx.stroke();
      }
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;
    }

    if (s.pos) {
      const x = s.pos.x * vw, y = s.pos.y * vh;
      const r = 7 * unit;
      ctx.save();
      ctx.shadowColor = 'rgba(255,224,102,.9)';
      ctx.shadowBlur = 16 * unit;
      ctx.fillStyle = '#fffbe6';
      ctx.beginPath(); ctx.arc(x, y, r * 0.55, 0, Math.PI * 2); ctx.fill();
      ctx.restore();
      ctx.strokeStyle = 'rgba(255,224,102,.95)';
      ctx.lineWidth = 2 * unit;
      ctx.beginPath(); ctx.arc(x, y, r * 1.7, 0, Math.PI * 2); ctx.stroke();
    }
  }

  drawCandidates(cands) {
    const ctx = this.ctx;
    const { vw, vh } = this;
    ctx.strokeStyle = 'rgba(120,255,180,.65)';
    ctx.lineWidth = 1.2;
    for (const c of cands) {
      ctx.strokeRect((c.x - c.bw / 2) * vw, (c.y - c.bh / 2) * vh, c.bw * vw, c.bh * vh);
    }
  }

  _tag(x, y, text, color, unit) {
    const ctx = this.ctx;
    const size = 13 * unit;
    ctx.font = `600 ${size}px -apple-system, "Noto Sans TC", sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const w = ctx.measureText(text).width + 14 * unit;
    const h = size + 9 * unit;
    ctx.fillStyle = 'rgba(6,10,20,.72)';
    this._roundRect(x - w / 2, y - h / 2, w, h, 6 * unit);
    ctx.fill();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.2 * unit;
    ctx.stroke();
    ctx.fillStyle = '#fff';
    ctx.fillText(text, x, y + 0.5 * unit);
  }

  _roundRect(x, y, w, h, r) {
    const ctx = this.ctx;
    ctx.beginPath();
    if (ctx.roundRect) { ctx.roundRect(x, y, w, h, r); return; }
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  /* ---------------- HUD (drawn in CANVAS space, outside the transform) --- */

  drawHud(lines) {
    if (!lines.length) return;
    const ctx = this.ctx;
    const unit = Math.max(this.canvas.width, this.canvas.height) / 720;
    const size = 14 * unit;
    ctx.font = `600 ${size}px -apple-system, "Noto Sans TC", sans-serif`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    const pad = 9 * unit;
    const lh = size * 1.5;
    const w = Math.max(...lines.map((l) => ctx.measureText(l).width)) + pad * 2;
    const h = lines.length * lh + pad * 1.4;
    const x = this.canvas.width - w - 12 * unit;
    const y = 12 * unit;
    ctx.fillStyle = 'rgba(6,10,20,.6)';
    this._roundRect(x, y, w, h, 9 * unit);
    ctx.fill();
    ctx.fillStyle = '#e8edf7';
    lines.forEach((l, i) => ctx.fillText(l, x + pad, y + pad * 0.7 + i * lh));
  }
}
