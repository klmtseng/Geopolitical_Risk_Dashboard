// Dual recording: the untouched camera feed and the annotated canvas, captured
// simultaneously by two independent MediaRecorders.
//
// The raw track is recorded straight off the camera MediaStream, so it is not
// re-encoded through the canvas and keeps full sensor quality. The overlay
// track comes from canvas.captureStream(), which pulls frames as the render
// loop paints them.

const VIDEO_MIMES = [
  'video/mp4;codecs=avc1.42E01E',   // Safari / iOS
  'video/mp4',
  'video/webm;codecs=vp9,opus',
  'video/webm;codecs=vp8,opus',
  'video/webm;codecs=vp9',
  'video/webm;codecs=vp8',
  'video/webm',
];

export function pickMime() {
  if (typeof MediaRecorder === 'undefined') return null;
  for (const m of VIDEO_MIMES) {
    try { if (MediaRecorder.isTypeSupported(m)) return m; } catch { /* noop */ }
  }
  return '';
}

export function isSupported() {
  return typeof MediaRecorder !== 'undefined' && pickMime() !== null;
}

export function extFor(mime) {
  return (mime || '').includes('mp4') ? 'mp4' : 'webm';
}

class Leg {
  constructor(kind, stream, mime, bitrate) {
    this.kind = kind;          // 'raw' | 'overlay'
    this.chunks = [];
    this.mime = mime;
    this.stream = stream;
    const opts = {};
    if (mime) opts.mimeType = mime;
    if (bitrate) opts.videoBitsPerSecond = bitrate;
    this.rec = new MediaRecorder(stream, opts);
    this.rec.ondataavailable = (e) => { if (e.data && e.data.size) this.chunks.push(e.data); };
    this.error = null;
    this.rec.onerror = (e) => { this.error = e.error || e; };
  }
  start(timeslice) { this.rec.start(timeslice); }
  stop() {
    return new Promise((resolve) => {
      if (this.rec.state === 'inactive') return resolve(this._finish());
      this.rec.onstop = () => resolve(this._finish());
      try { this.rec.stop(); } catch { resolve(this._finish()); }
    });
  }
  _finish() {
    const type = this.mime || this.chunks[0]?.type || 'video/webm';
    const blob = new Blob(this.chunks, { type });
    this.chunks = [];
    return { kind: this.kind, blob, mime: type, bytes: blob.size, error: this.error };
  }
}

export class DualRecorder {
  constructor() {
    this.legs = [];
    this.startedAt = 0;
    this.active = false;
    this.canvasStream = null;
  }

  /**
   * @param {object} o
   * @param {MediaStream} o.cameraStream  live camera (may be null in file mode)
   * @param {HTMLCanvasElement} o.canvas  annotated canvas
   * @param {boolean} o.raw               record the untouched feed
   * @param {boolean} o.overlay           record the annotated canvas
   * @param {boolean} o.audio             keep the microphone track
   * @param {number}  o.bitrate
   * @param {number}  o.fps
   */
  start({ cameraStream, canvas, raw, overlay, audio, bitrate = 8e6, fps = 30 }) {
    if (this.active) return;
    const mime = pickMime();
    if (mime === null) throw new Error('此瀏覽器不支援 MediaRecorder 錄影。');
    this.legs = [];

    const audioTracks = audio && cameraStream
      ? cameraStream.getAudioTracks().filter((t) => t.readyState === 'live')
      : [];

    if (raw && cameraStream) {
      const tracks = [...cameraStream.getVideoTracks(), ...audioTracks];
      this.legs.push(new Leg('raw', new MediaStream(tracks), mime, bitrate));
    }

    if (overlay) {
      this.canvasStream = canvas.captureStream(fps);
      const tracks = [...this.canvasStream.getVideoTracks(), ...audioTracks];
      this.legs.push(new Leg('overlay', new MediaStream(tracks), mime, bitrate));
    }

    if (!this.legs.length) throw new Error('請至少勾選一種要錄製的影片。');

    for (const leg of this.legs) leg.start(1000);
    this.startedAt = performance.now();
    this.active = true;
  }

  get elapsedMs() { return this.active ? performance.now() - this.startedAt : 0; }

  async stop() {
    if (!this.active) return [];
    const durationMs = this.elapsedMs;
    this.active = false;
    const results = await Promise.all(this.legs.map((l) => l.stop()));
    this.legs = [];
    if (this.canvasStream) {
      this.canvasStream.getTracks().forEach((t) => t.stop());
      this.canvasStream = null;
    }
    return results
      .filter((r) => r.bytes > 0)
      .map((r) => ({ ...r, durationMs, url: URL.createObjectURL(r.blob) }));
  }
}

export function timestampName() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

export function formatDuration(ms) {
  const s = Math.floor(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

export function formatBytes(b) {
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b / 1024).toFixed(0)} KB`;
  return `${(b / 1048576).toFixed(1)} MB`;
}
