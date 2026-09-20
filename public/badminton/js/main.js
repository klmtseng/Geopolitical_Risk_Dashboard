// Application wiring: source -> pose -> motion -> shuttle/racket -> render,
// plus recording and the settings sheet.

import { PoseEngine, PersonTracker } from './pose.js';
import { MotionField } from './motion.js';
import { ShuttleTracker, estimateKmh } from './shuttle.js';
import { RacketEstimator } from './racket.js';
import { Renderer } from './render.js';
import { SMOOTH_PRESETS } from './geometry.js';
import { openCamera, stopStream, waitForVideo, driveFrames } from './camera.js';
import {
  DualRecorder, isSupported as recSupported, pickMime, extFor,
  timestampName, formatDuration, formatBytes,
} from './recorder.js';
import * as Settings from './settings.js';

const $ = (id) => document.getElementById(id);

// ~15 minutes at 30 fps; beyond this the JSON buffer starts costing real memory.
const JSON_FRAME_CAP = 27000;

const el = {
  view: $('view'),
  source: $('source'),
  stage: $('stage'),
  startPanel: $('startPanel'),
  loadingPanel: $('loadingPanel'),
  loadingText: $('loadingText'),
  startHint: $('startHint'),
  stageControls: $('stageControls'),
  btnStartCam: $('btnStartCam'),
  btnPickFile: $('btnPickFile'),
  fileInput: $('fileInput'),
  btnRecord: $('btnRecord'),
  btnFlip: $('btnFlip'),
  btnSnap: $('btnSnap'),
  recBadge: $('recBadge'),
  recTime: $('recTime'),
  btnSettings: $('btnSettings'),
  btnCloseSheet: $('btnCloseSheet'),
  sheet: $('sheet'),
  toast: $('toast'),
  clipList: $('clipList'),
  meterFps: $('meterFps'),
  meterInfer: $('meterInfer'),
  meterPeople: $('meterPeople'),
  codecNote: $('codecNote'),
  heightField: $('heightField'),
  btnReset: $('btnReset'),
};

const settings = Settings.load();

const state = {
  mode: null,              // 'camera' | 'file'
  stream: null,
  engine: null,
  engineVariant: null,
  engineLoading: false,
  tracker: new PersonTracker(),
  motion: new MotionField(208),
  shuttle: new ShuttleTracker(),
  racket: new RacketEstimator(),
  renderer: new Renderer(el.view),
  recorder: new DualRecorder(),
  stopLoop: null,
  frameNo: 0,
  lastPoses: [],
  bodyTrails: new Map(),
  fpsWindow: [],
  lastFrameT: 0,
  recTimer: null,
  jsonFrames: null,
  clips: [],
  inferSamples: [],
  perfHintShown: false,
};

/* ------------------------------------------------------------------ *
 * UI helpers
 * ------------------------------------------------------------------ */

let toastTimer = null;
function toast(msg, ms = 2600) {
  el.toast.textContent = msg;
  el.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.toast.hidden = true; }, ms);
}

function showLoading(text) {
  el.loadingText.textContent = text;
  el.loadingPanel.classList.remove('hidden');
}
function hideLoading() { el.loadingPanel.classList.add('hidden'); }

/** Non-blocking progress line in the top bar, used once the preview is live. */
function setStatus(text) {
  if (text) {
    el.meterInfer.textContent = text;
    el.meterInfer.dataset.status = '1';
  } else {
    delete el.meterInfer.dataset.status;
  }
}

function syncLabels() {
  $('valSmooth').textContent = SMOOTH_PRESETS[settings.smooth]?.label ?? '中';
  $('valThick').textContent = settings.thickness;
  $('valRacketLen').textContent = settings.racketLen.toFixed(1);
  $('valRacketTrail').textContent = settings.racketTrail.toFixed(1);
  $('valSens').textContent = settings.sensitivity;
  $('valShuttleTrail').textContent = settings.shuttleTrail.toFixed(1);
  el.heightField.hidden = !settings.speed;
}

/* ------------------------------------------------------------------ *
 * Source management
 * ------------------------------------------------------------------ */

async function ensureEngine() {
  if (state.engine && state.engineVariant === settings.model) {
    await state.engine.setNumPoses(settings.people);
    return state.engine;
  }
  if (state.engineLoading) return null;
  state.engineLoading = true;
  setStatus('載入姿態模型…');
  try {
    state.engine?.close();
    state.engine = await PoseEngine.create({
      variant: settings.model,
      numPoses: settings.people,
      onProgress: showLoading,
    });
    state.engineVariant = settings.model;
    state.tracker.reset();
    state.racket.reset();
    state.perfHintShown = false;
    state.inferSamples.length = 0;
    if (state.engine.meta.delegate === 'CPU') {
      toast('GPU 推論不可用，已改用 CPU（速度較慢）。', 4200);
    }
  } catch (err) {
    console.error(err);
    const offline = /fetch|network|load/i.test(err.message ?? '');
    toast(offline
      ? '模型下載失敗，請確認網路連線；離線使用請先執行 npm run badminton:assets。'
      : `模型載入失敗：${err.message}`, 7000);
    state.engine = null;
  } finally {
    state.engineLoading = false;
    setStatus(null);
  }
  return state.engine;
}

async function startCamera() {
  try {
    showLoading('開啟相機…');
    stopStream(state.stream);
    state.stream = await openCamera({
      facing: settings.facing,
      height: settings.resolution,
      fps: settings.fps,
      audio: settings.recAudio,
    });
    el.source.srcObject = state.stream;
    el.source.removeAttribute('src');
    el.source.muted = true;
    el.source.loop = false;
    el.source.controls = false;
    await el.source.play();
    await waitForVideo(el.source);
    state.mode = 'camera';
    onSourceReady();
  } catch (err) {
    console.error(err);
    hideLoading();
    el.startHint.textContent = `無法開啟相機：${err.message}`;
    toast(`無法開啟相機：${err.message}`, 5000);
  }
}

async function startFile(file) {
  try {
    showLoading('載入影片…');
    stopStream(state.stream);
    state.stream = null;
    el.source.srcObject = null;
    el.source.src = URL.createObjectURL(file);
    el.source.muted = false;
    el.source.loop = true;
    await el.source.play().catch(() => {});
    await waitForVideo(el.source);
    state.mode = 'file';
    onSourceReady();
    toast('影片模式：可錄製骨架疊加影片（原始影像請直接用原檔）。', 4200);
  } catch (err) {
    console.error(err);
    hideLoading();
    toast(`無法載入影片：${err.message}`, 5000);
  }
}

async function onSourceReady() {
  el.startPanel.classList.add('hidden');
  el.stageControls.hidden = false;
  el.btnFlip.disabled = state.mode !== 'camera';
  resetAnalysis();
  // Start painting immediately. The model takes seconds to download on a
  // phone the first time, and staring at a spinner when the camera is already
  // live feels broken; the skeleton simply appears once the model is ready.
  hideLoading();
  startLoop();
  await ensureEngine();
}

function resetAnalysis() {
  state.tracker.reset();
  state.racket.reset();
  state.shuttle.reset();
  state.bodyTrails.clear();
  state.motion = new MotionField(208);
  state.frameNo = 0;
}

/* ------------------------------------------------------------------ *
 * Main loop
 * ------------------------------------------------------------------ */

function startLoop() {
  state.stopLoop?.();
  state.stopLoop = driveFrames(el.source, onFrame);
}

function onFrame(nowMs) {
  const video = el.source;
  if (!video.videoWidth) return;

  const tSec = nowMs / 1000;
  const dt = state.lastFrameT ? Math.min(0.25, tSec - state.lastFrameT) : 1 / 30;
  state.lastFrameT = tSec;
  state.frameNo++;

  const r = state.renderer;
  if (!r.sync(video, settings.rotate, settings.mirror && state.mode === 'camera')) return;
  const ar = r.vw / r.vh;

  // ---- analysis ------------------------------------------------------
  if (settings.pose && state.engine && state.frameNo % settings.stride === 0) {
    const raw = state.engine.detect(video, nowMs);
    state.lastPoses = state.tracker.update(raw, tSec, ar);
  } else if (!settings.pose) {
    state.lastPoses = [];
  }
  const people = state.lastPoses;

  const needMotion = settings.shuttle || settings.racket;
  if (needMotion) state.motion.update(video, settings.sensitivity);

  let shuttleRes = null;
  if (settings.shuttle) {
    shuttleRes = state.shuttle.update(state.motion, people, tSec, ar, settings.shuttleTrail);
  }

  const rackets = [];
  if (settings.racket) {
    for (const p of people) {
      const res = state.racket.update(p, state.motion, tSec, ar, {
        lengthFactor: settings.racketLen,
        trailSeconds: settings.racketTrail,
        dtSec: dt,
      });
      if (res) rackets.push({ person: p, racket: res });
    }
  }

  if (settings.bodyTrail) {
    const alive = new Set(people.map((p) => p.id));
    for (const p of people) {
      if (!state.bodyTrails.has(p.id)) state.bodyTrails.set(p.id, []);
      state.bodyTrails.get(p.id).push({ x: p.anchor.x, y: p.anchor.y, t: tSec });
    }
    // Trim every trail, not just the visible ones, so a player who walks out
    // of frame does not leave a stale entry behind for the rest of the session.
    for (const [id, trail] of state.bodyTrails) {
      while (trail.length && trail[0].t < tSec - 4) trail.shift();
      if (!trail.length && !alive.has(id)) state.bodyTrails.delete(id);
    }
  }
  state.racket.prune(new Set(people.map((p) => p.id)));

  // ---- draw ----------------------------------------------------------
  r.clear(settings.skeletonOnly);
  r.begin();
  if (!settings.skeletonOnly) r.drawVideo(video);

  const unit = Math.max(r.vw, r.vh) / 720;
  if (settings.bodyTrail) {
    for (const p of people) {
      const t = state.bodyTrails.get(p.id);
      if (t) r.drawBodyTrail(t, p.color.line, unit);
    }
  }
  for (const { person, racket } of rackets) r.drawRacket(racket, person.color.line);
  for (const p of people) r.drawPerson(p, { thickness: settings.thickness });
  if (shuttleRes) {
    if (settings.shuttleDebug) r.drawCandidates(shuttleRes.candidates);
    r.drawShuttle(shuttleRes, { now: tSec, trailSeconds: settings.shuttleTrail });
  }
  r.end();

  r.drawHud(buildHud(people, shuttleRes, rackets));

  // ---- capture data ----------------------------------------------------
  if (state.jsonFrames && state.recorder.active) {
    if (state.jsonFrames.length >= JSON_FRAME_CAP) {
      if (state.jsonFrames.length === JSON_FRAME_CAP) {
        toast('動作資料已達上限，停止記錄（影片不受影響）。', 4000);
        state.jsonFrames.push(null);
      }
    } else state.jsonFrames.push({
      t: +(state.recorder.elapsedMs / 1000).toFixed(3),
      poses: people.map((p) => ({
        id: p.id,
        lm: p.lms.map((l) => [+l.x.toFixed(4), +l.y.toFixed(4), +l.z.toFixed(4), +(l.visibility ?? 0).toFixed(2)]),
      })),
      rackets: rackets.map(({ person, racket }) => ({
        id: person.id, side: racket.side,
        head: [+racket.head.x.toFixed(4), +racket.head.y.toFixed(4)],
      })),
      shuttle: shuttleRes?.pos
        ? { x: +shuttleRes.pos.x.toFixed(4), y: +shuttleRes.pos.y.toFixed(4), c: +shuttleRes.confidence.toFixed(2) }
        : null,
    });
  }

  // ---- meters ----------------------------------------------------------
  state.fpsWindow.push(nowMs);
  while (state.fpsWindow.length > 40) state.fpsWindow.shift();
  if (state.engine?.lastInferMs) {
    state.inferSamples.push(state.engine.lastInferMs);
    if (state.inferSamples.length > 60) state.inferSamples.shift();
  }
  if (state.frameNo % 10 === 0) {
    const span = state.fpsWindow.at(-1) - state.fpsWindow[0];
    const fps = span > 0 ? ((state.fpsWindow.length - 1) * 1000) / span : 0;
    el.meterFps.textContent = `${fps.toFixed(0)} fps`;
    if (!el.meterInfer.dataset.status) {
      el.meterInfer.textContent = `${(state.engine?.lastInferMs ?? 0).toFixed(0)} ms`;
    }
    el.meterPeople.textContent = `${people.length} 人`;
    maybeSuggestLighterSettings();
  }
}

/**
 * Inference runs on the render thread, so a slow model does not just lower the
 * frame rate — it freezes the preview. Rather than silently degrading, tell the
 * user once what would fix it and let them choose.
 */
function maybeSuggestLighterSettings() {
  if (state.perfHintShown || state.inferSamples.length < 45) return;
  const sorted = [...state.inferSamples].sort((a, b) => a - b);
  const median = sorted[sorted.length >> 1];
  if (median < 70) return;
  state.perfHintShown = true;
  if (settings.model !== 'lite') {
    toast(`推論耗時 ${median.toFixed(0)} ms，畫面會卡。建議在設定中把模型改為 Lite。`, 6500);
  } else if (settings.stride < 2) {
    toast(`推論耗時 ${median.toFixed(0)} ms。建議把「推論頻率」改為每 2 幀，或降低解析度。`, 6500);
  }
}

function buildHud(people, shuttleRes, rackets) {
  const lines = [];
  if (settings.speed && shuttleRes?.active) {
    const withHeight = people.find((p) => p.bodyHeight);
    if (withHeight) {
      // bodyHeight is the player's height as a fraction of the frame height;
      // dividing the real height by it gives how many metres the frame spans.
      const frameMeters = (settings.playerHeight / 100) / withHeight.bodyHeight;
      const kmh = estimateKmh(shuttleRes.speed, frameMeters);
      if (kmh != null && kmh < 600) lines.push(`羽球 ≈ ${kmh.toFixed(0)} km/h`);
    } else {
      lines.push('球速：需拍到全身');
    }
  }
  for (const { person, racket } of rackets) {
    lines.push(`${person.color.name}：${racket.side === 'right' ? '右' : '左'}手持拍`);
  }
  return lines;
}

/* ------------------------------------------------------------------ *
 * Recording
 * ------------------------------------------------------------------ */

function toggleRecord() {
  state.recorder.active ? stopRecording() : startRecording();
}

function startRecording() {
  try {
    state.recorder.start({
      cameraStream: state.stream,
      canvas: el.view,
      raw: settings.recRaw && state.mode === 'camera',
      overlay: settings.recOverlay,
      audio: settings.recAudio,
      bitrate: settings.bitrate,
      fps: settings.fps,
    });
  } catch (err) {
    toast(err.message, 4500);
    return;
  }
  state.jsonFrames = settings.recJson ? [] : null;
  el.btnRecord.classList.add('on');
  el.recBadge.classList.remove('hidden');
  el.btnFlip.disabled = true;
  state.recTimer = setInterval(() => {
    el.recTime.textContent = formatDuration(state.recorder.elapsedMs);
  }, 250);
}

async function stopRecording() {
  clearInterval(state.recTimer);
  el.btnRecord.classList.remove('on');
  el.recBadge.classList.add('hidden');
  el.btnFlip.disabled = state.mode !== 'camera';
  const results = await state.recorder.stop();
  const stamp = timestampName();

  for (const rres of results) {
    addClip({
      name: `badminton-${stamp}-${rres.kind === 'raw' ? '原始' : '骨架'}.${extFor(rres.mime)}`,
      label: rres.kind === 'raw' ? '原始影像' : '骨架疊加',
      ...rres,
    });
  }

  if (state.jsonFrames?.length) {
    const blob = new Blob([JSON.stringify({
      version: 1,
      createdAt: new Date().toISOString(),
      frame: { width: state.renderer.vw, height: state.renderer.vh },
      model: state.engine?.meta ?? null,
      note: 'landmarks are normalised to the unrotated video frame; MediaPipe Pose 33-point topology',
      frames: state.jsonFrames.filter(Boolean),
    })], { type: 'application/json' });
    addClip({
      name: `badminton-${stamp}-data.json`,
      label: '動作資料',
      blob, mime: 'application/json', bytes: blob.size,
      url: URL.createObjectURL(blob),
      durationMs: results[0]?.durationMs ?? 0,
    });
  }
  state.jsonFrames = null;

  if (!results.length) toast('沒有錄到影片，請確認錄影選項。', 4000);
  else { toast(`已完成 ${results.length} 個檔案，可在設定 → 錄影檔案中下載。`, 4200); openSheet(); }
}

function addClip(clip) {
  state.clips.unshift(clip);
  renderClips();
}

function renderClips() {
  if (!state.clips.length) {
    el.clipList.innerHTML = '<p class="note">尚未有錄影。</p>';
    return;
  }
  el.clipList.innerHTML = '';
  state.clips.forEach((c, i) => {
    const wrap = document.createElement('div');
    wrap.className = 'clip';
    if (c.mime.startsWith('video/')) {
      const v = document.createElement('video');
      v.src = c.url; v.controls = true; v.playsInline = true; v.preload = 'metadata';
      wrap.appendChild(v);
    }
    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.innerHTML = `<strong>${c.label}</strong><span>${formatDuration(c.durationMs)} · ${formatBytes(c.bytes)}</span>`;
    const acts = document.createElement('div');
    acts.className = 'acts';
    const a = document.createElement('a');
    a.href = c.url; a.download = c.name; a.textContent = '下載';
    const del = document.createElement('button');
    del.className = 'mini'; del.textContent = '刪除';
    del.onclick = () => { URL.revokeObjectURL(c.url); state.clips.splice(i, 1); renderClips(); };
    acts.append(a, del);
    meta.appendChild(acts);
    wrap.appendChild(meta);
    el.clipList.appendChild(wrap);
  });
}

function snapshot() {
  el.view.toBlob((blob) => {
    if (!blob) return;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `badminton-${timestampName()}.png`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    toast('已擷取畫面。');
  }, 'image/png');
}

/* ------------------------------------------------------------------ *
 * Settings sheet
 * ------------------------------------------------------------------ */

function openSheet() { el.sheet.classList.add('open'); el.sheet.setAttribute('aria-hidden', 'false'); }
function closeSheet() { el.sheet.classList.remove('open'); el.sheet.setAttribute('aria-hidden', 'true'); }

async function onSettingChange(key) {
  syncLabels();
  if (key === 'smooth') state.tracker.setSmoothing(settings.smooth);
  if (key === 'model' || key === 'people') await ensureEngine();
  if ((key === 'facing' || key === 'resolution' || key === 'fps' || key === 'recAudio') && state.mode === 'camera') {
    if (state.recorder.active) { toast('錄影中無法更換相機設定。'); return; }
    await startCamera();
  }
  if (key === 'sensitivity') state.shuttle.reset();
}

/* ------------------------------------------------------------------ *
 * Boot
 * ------------------------------------------------------------------ */

function boot() {
  Settings.bind(settings, onSettingChange);
  syncLabels();
  state.tracker.setSmoothing(settings.smooth);

  el.btnStartCam.onclick = startCamera;
  el.btnPickFile.onclick = () => el.fileInput.click();
  el.fileInput.onchange = (e) => { const f = e.target.files?.[0]; if (f) startFile(f); };
  el.btnRecord.onclick = toggleRecord;
  el.btnSnap.onclick = snapshot;
  el.btnFlip.onclick = () => {
    if (state.recorder.active) return toast('錄影中無法切換鏡頭。');
    settings.facing = settings.facing === 'user' ? 'environment' : 'user';
    $('optFacing').value = settings.facing;
    Settings.save(settings);
    startCamera();
  };
  el.btnSettings.onclick = openSheet;
  el.btnCloseSheet.onclick = closeSheet;
  el.btnReset.onclick = () => { Settings.reset(); location.reload(); };

  if (!recSupported()) {
    el.codecNote.textContent = '⚠️ 此瀏覽器不支援 MediaRecorder，無法錄影（其他功能可正常使用）。';
  } else {
    const m = pickMime();
    el.codecNote.textContent = `錄影格式：${m || '瀏覽器預設'}（副檔名 .${extFor(m)}）。`;
  }

  if (!window.isSecureContext) {
    el.startHint.textContent = '⚠️ 目前不是安全連線（HTTPS），瀏覽器會拒絕開啟相機。仍可使用「載入影片檔」。';
  }

  window.addEventListener('beforeunload', (e) => {
    if (state.recorder.active) { e.preventDefault(); e.returnValue = ''; }
  });

  // Keep the canvas crisp when the phone rotates.
  window.addEventListener('orientationchange', () => setTimeout(() => state.renderer.sync(el.source, settings.rotate, settings.mirror), 350));
}

boot();
