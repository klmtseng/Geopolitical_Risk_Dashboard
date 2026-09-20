// Pose backend. Wraps MediaPipe Pose Landmarker and adds the two things the
// raw task does not give us: stable person IDs across frames, and per-landmark
// temporal smoothing.
//
// The backend is deliberately behind a small interface (`create` / `detect` /
// `close`) so a different model — MoveNet MultiPose, a YOLO-pose ONNX graph —
// can be dropped in later without touching the renderer or the trackers.

import { LM, OneEuro2D, SMOOTH_PRESETS, dist, mid } from './geometry.js';

const LIB_VERSION = '1.0.1';

// Try a self-hosted copy first (see scripts/fetch-badminton-assets.mjs), then
// fall back to the public CDN. Self-hosting is what makes the app work on a
// gym Wi-Fi that blocks jsdelivr, or fully offline.
const LOCAL_ROOT = new URL('../vendor/', import.meta.url).href;
const CDN_ROOT = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${LIB_VERSION}/`;

const MODEL_FILES = {
  lite: 'pose_landmarker_lite.task',
  full: 'pose_landmarker_full.task',
  heavy: 'pose_landmarker_heavy.task',
};
const MODEL_CDN = 'https://storage.googleapis.com/mediapipe-models/pose_landmarker/';
const modelCdnUrl = (v) => `${MODEL_CDN}pose_landmarker_${v}/float16/1/${MODEL_FILES[v]}`;

async function exists(url) {
  try {
    const r = await fetch(url, { method: 'HEAD', cache: 'no-store' });
    return r.ok;
  } catch { return false; }
}

let visionModule = null;
async function loadVisionModule() {
  if (visionModule) return visionModule;
  const localBundle = `${LOCAL_ROOT}vision_bundle.mjs`;
  if (await exists(localBundle)) {
    try {
      visionModule = { mod: await import(/* @vite-ignore */ localBundle), wasmBase: `${LOCAL_ROOT}wasm`, local: true };
      return visionModule;
    } catch { /* fall through to CDN */ }
  }
  visionModule = {
    mod: await import(/* @vite-ignore */ `${CDN_ROOT}vision_bundle.mjs`),
    wasmBase: `${CDN_ROOT}wasm`,
    local: false,
  };
  return visionModule;
}

export class PoseEngine {
  constructor(landmarker, meta) {
    this.landmarker = landmarker;
    this.meta = meta;          // { variant, numPoses, delegate, local }
    this.lastInferMs = 0;
  }

  static get POSE_VARIANTS() { return Object.keys(MODEL_FILES); }

  static async create({ variant = 'full', numPoses = 2, onProgress = () => {} } = {}) {
    onProgress('載入執行環境…');
    const { mod, wasmBase, local } = await loadVisionModule();
    const { FilesetResolver, PoseLandmarker } = mod;

    const fileset = await FilesetResolver.forVisionTasks(wasmBase);

    onProgress('下載姿態模型…');
    const localModel = `${LOCAL_ROOT}models/${MODEL_FILES[variant]}`;
    const modelAssetPath = (await exists(localModel)) ? localModel : modelCdnUrl(variant);

    const baseOptions = { modelAssetPath };
    let landmarker = null;
    let delegate = 'GPU';
    try {
      onProgress('初始化 GPU 推論…');
      landmarker = await PoseLandmarker.createFromOptions(fileset, {
        baseOptions: { ...baseOptions, delegate: 'GPU' },
        runningMode: 'VIDEO',
        numPoses,
        minPoseDetectionConfidence: 0.4,
        minPosePresenceConfidence: 0.4,
        minTrackingConfidence: 0.4,
        outputSegmentationMasks: false,
      });
    } catch (err) {
      console.warn('[pose] GPU delegate unavailable, falling back to CPU', err);
      onProgress('GPU 不可用，改用 CPU…');
      delegate = 'CPU';
      landmarker = await PoseLandmarker.createFromOptions(fileset, {
        baseOptions: { ...baseOptions, delegate: 'CPU' },
        runningMode: 'VIDEO',
        numPoses,
        minPoseDetectionConfidence: 0.4,
        minPosePresenceConfidence: 0.4,
        minTrackingConfidence: 0.4,
        outputSegmentationMasks: false,
      });
    }

    const engine = new PoseEngine(landmarker, { variant, numPoses, delegate, local });
    engine.connections = PoseLandmarker.POSE_CONNECTIONS;
    return engine;
  }

  async setNumPoses(numPoses) {
    if (numPoses === this.meta.numPoses) return;
    this.meta.numPoses = numPoses;
    await this.landmarker.setOptions({ numPoses });
  }

  /** @returns {Array<Array<{x,y,z,visibility}>>} raw landmark sets, video-normalised */
  detect(videoEl, timestampMs) {
    const t0 = performance.now();
    let res;
    try {
      res = this.landmarker.detectForVideo(videoEl, timestampMs);
    } catch (err) {
      console.warn('[pose] detect failed', err);
      return [];
    }
    this.lastInferMs = performance.now() - t0;
    return res?.landmarks ?? [];
  }

  close() {
    try { this.landmarker.close(); } catch { /* noop */ }
  }
}

/* ------------------------------------------------------------------ *
 * Person tracking
 * ------------------------------------------------------------------ */

const PALETTE = [
  { name: '球員 1', line: '#4fd1c5', glow: 'rgba(79,209,197,.35)', joint: '#e6fffb' },
  { name: '球員 2', line: '#f472b6', glow: 'rgba(244,114,182,.35)', joint: '#fff0f7' },
  { name: '球員 3', line: '#fbbf24', glow: 'rgba(251,191,36,.35)', joint: '#fffbeb' },
  { name: '球員 4', line: '#818cf8', glow: 'rgba(129,140,248,.35)', joint: '#eef2ff' },
];

function anchorOf(lms) {
  const l = lms[LM.leftHip], r = lms[LM.rightHip];
  if (l && r && (l.visibility + r.visibility) > 0.6) return mid(l, r);
  const ls = lms[LM.leftShoulder], rs = lms[LM.rightShoulder];
  if (ls && rs) return mid(ls, rs);
  return lms[LM.nose] ?? { x: 0.5, y: 0.5 };
}

/** Rough body scale (shoulder-to-hip span) used to size overlays and gates. */
function scaleOf(lms, ar) {
  const sh = mid(lms[LM.leftShoulder], lms[LM.rightShoulder]);
  const hp = mid(lms[LM.leftHip], lms[LM.rightHip]);
  const torso = dist(sh, hp, ar);
  return torso > 0.01 ? torso : 0.12;
}

/** Full-body pixel height, when head and feet are both visible. For calibration. */
function bodyHeightOf(lms, ar) {
  const head = lms[LM.nose];
  const feet = [lms[LM.leftAnkle], lms[LM.rightAnkle]].filter((p) => p && p.visibility > 0.5);
  if (!head || head.visibility < 0.5 || !feet.length) return null;
  const footY = Math.max(...feet.map((p) => p.y));
  const h = footY - head.y;
  return h > 0.05 ? h * 1.06 : null; // +6%: nose sits below the crown of the head
}

export class PersonTracker {
  constructor() {
    this.tracks = new Map(); // id -> { id, filters:Map, lastSeen, colorIdx }
    this.nextId = 1;
    this.smoothIdx = 2;
  }

  setSmoothing(idx) {
    this.smoothIdx = idx;
    const p = SMOOTH_PRESETS[idx];
    for (const t of this.tracks.values()) {
      for (const f of t.filters.values()) f.retune(p.minCutoff, p.beta);
    }
  }

  /**
   * @param {Array<Array>} rawSets landmark sets from PoseEngine.detect
   * @param {number} tSec monotonic seconds
   * @param {number} ar video aspect ratio (w/h)
   * @returns {Array<{id,color,lms,anchor,scale,bodyHeight}>}
   */
  update(rawSets, tSec, ar) {
    const anchors = rawSets.map(anchorOf);
    const unused = new Set(this.tracks.keys());
    const assigned = new Array(rawSets.length).fill(null);

    // Greedy nearest-neighbour matching. With <= 4 people this is exact enough
    // and far cheaper than Hungarian assignment.
    const pairs = [];
    for (let i = 0; i < anchors.length; i++) {
      for (const id of unused) {
        const t = this.tracks.get(id);
        pairs.push({ i, id, d: dist(anchors[i], t.anchor, ar) });
      }
    }
    pairs.sort((a, b) => a.d - b.d);
    const takenDet = new Set();
    for (const p of pairs) {
      if (takenDet.has(p.i) || !unused.has(p.id)) continue;
      if (p.d > 0.35) continue; // too far to be the same person
      assigned[p.i] = p.id;
      takenDet.add(p.i);
      unused.delete(p.id);
    }

    const usedColors = new Set([...this.tracks.values()].map((t) => t.colorIdx));
    const preset = SMOOTH_PRESETS[this.smoothIdx];
    const out = [];

    for (let i = 0; i < rawSets.length; i++) {
      let id = assigned[i];
      if (id === null) {
        id = this.nextId++;
        let colorIdx = 0;
        while (usedColors.has(colorIdx) && colorIdx < PALETTE.length - 1) colorIdx++;
        usedColors.add(colorIdx);
        this.tracks.set(id, { id, colorIdx, filters: new Map(), anchor: anchors[i], lastSeen: tSec });
      }
      const track = this.tracks.get(id);
      track.anchor = anchors[i];
      track.lastSeen = tSec;

      const raw = rawSets[i];
      const lms = new Array(raw.length);
      for (let k = 0; k < raw.length; k++) {
        const p = raw[k];
        let f = track.filters.get(k);
        if (!f) {
          f = new OneEuro2D({ minCutoff: preset.minCutoff, beta: preset.beta });
          track.filters.set(k, f);
        }
        const s = preset.minCutoff > 1e5 ? p : f.filter(p, tSec);
        lms[k] = { x: s.x, y: s.y, z: p.z, visibility: p.visibility };
      }

      out.push({
        id,
        color: PALETTE[track.colorIdx % PALETTE.length],
        lms,
        anchor: anchorOf(lms),
        scale: scaleOf(lms, ar),
        bodyHeight: bodyHeightOf(lms, ar),
      });
    }

    // Drop tracks that have been missing for over a second.
    for (const [id, t] of this.tracks) {
      if (tSec - t.lastSeen > 1.0) this.tracks.delete(id);
    }
    return out;
  }

  reset() { this.tracks.clear(); this.nextId = 1; }
}
