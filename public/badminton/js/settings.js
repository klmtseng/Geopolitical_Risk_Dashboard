// Settings: a plain object mirrored into localStorage and bound to the DOM by
// element id. Each entry declares the element id, the kind of control, and a
// default; everything else (load, save, wiring, reset) is generic.

const KEY = 'badminton-pose-settings-v1';

export const SCHEMA = {
  facing:        { el: 'optFacing',        kind: 'value',   def: 'environment' },
  resolution:    { el: 'optRes',           kind: 'number',  def: 960 },
  fps:           { el: 'optFps',           kind: 'number',  def: 30 },
  rotate:        { el: 'optRotate',        kind: 'number',  def: 0 },
  mirror:        { el: 'optMirror',        kind: 'checked', def: false },

  pose:          { el: 'optPose',          kind: 'checked', def: true },
  model:         { el: 'optModel',         kind: 'value',   def: 'full' },
  people:        { el: 'optPeople',        kind: 'number',  def: 2 },
  stride:        { el: 'optStride',        kind: 'number',  def: 1 },
  smooth:        { el: 'optSmooth',        kind: 'number',  def: 2 },
  thickness:     { el: 'optThick',         kind: 'number',  def: 4 },
  bodyTrail:     { el: 'optTraceBody',     kind: 'checked', def: false },

  racket:        { el: 'optRacket',        kind: 'checked', def: true },
  racketLen:     { el: 'optRacketLen',     kind: 'number',  def: 1.7 },
  racketTrail:   { el: 'optRacketTrail',   kind: 'number',  def: 0.8 },

  shuttle:       { el: 'optShuttle',       kind: 'checked', def: true },
  sensitivity:   { el: 'optSens',          kind: 'number',  def: 18 },
  shuttleTrail:  { el: 'optShuttleTrail',  kind: 'number',  def: 1.5 },
  shuttleDebug:  { el: 'optShuttleDebug',  kind: 'checked', def: false },
  speed:         { el: 'optSpeed',         kind: 'checked', def: false },
  playerHeight:  { el: 'optHeight',        kind: 'number',  def: 150 },

  recRaw:        { el: 'optRecRaw',        kind: 'checked', def: true },
  recOverlay:    { el: 'optRecOverlay',    kind: 'checked', def: true },
  recAudio:      { el: 'optRecAudio',      kind: 'checked', def: true },
  skeletonOnly:  { el: 'optSkeletonOnly',  kind: 'checked', def: false },
  bitrate:       { el: 'optBitrate',       kind: 'number',  def: 8e6 },
  recJson:       { el: 'optRecJson',       kind: 'checked', def: false },
};

export function defaults() {
  const o = {};
  for (const [k, s] of Object.entries(SCHEMA)) o[k] = s.def;
  return o;
}

export function load() {
  const base = defaults();
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) Object.assign(base, JSON.parse(raw));
  } catch { /* storage blocked — defaults are fine */ }
  return base;
}

export function save(settings) {
  try { localStorage.setItem(KEY, JSON.stringify(settings)); } catch { /* noop */ }
}

/** Push settings into the DOM, then listen for changes. */
export function bind(settings, onChange) {
  for (const [key, s] of Object.entries(SCHEMA)) {
    const el = document.getElementById(s.el);
    if (!el) continue;
    if (s.kind === 'checked') el.checked = !!settings[key];
    else el.value = String(settings[key]);

    const handler = () => {
      settings[key] = s.kind === 'checked' ? el.checked
        : s.kind === 'number' ? Number(el.value)
        : el.value;
      save(settings);
      onChange(key, settings[key]);
    };
    el.addEventListener('change', handler);
    if (el.type === 'range') el.addEventListener('input', handler);
  }
}

export function reset() {
  try { localStorage.removeItem(KEY); } catch { /* noop */ }
}
