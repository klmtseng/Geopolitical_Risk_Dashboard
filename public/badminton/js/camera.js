// Camera / file source handling.

export async function openCamera({ facing = 'environment', height = 960, fps = 30, audio = true } = {}) {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error('此瀏覽器不支援相機存取（需要 HTTPS 或 localhost）。');
  }
  // Ask by *height*: on a phone the sensor is landscape-native, so constraining
  // width fights the orientation. Height keeps portrait and landscape sane.
  const video = {
    facingMode: { ideal: facing },
    height: { ideal: height },
    frameRate: { ideal: fps },
  };
  try {
    return await navigator.mediaDevices.getUserMedia({ video, audio });
  } catch (err) {
    if (audio && (err.name === 'NotFoundError' || err.name === 'NotAllowedError')) {
      // Retry without the microphone — some devices refuse the combined request.
      return navigator.mediaDevices.getUserMedia({ video, audio: false });
    }
    if (err.name === 'OverconstrainedError') {
      return navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: facing } }, audio: false });
    }
    throw err;
  }
}

export function stopStream(stream) {
  if (!stream) return;
  for (const t of stream.getTracks()) { try { t.stop(); } catch { /* noop */ } }
}

/** Resolve once the element actually has frames to read. */
export function waitForVideo(video) {
  return new Promise((resolve, reject) => {
    if (video.readyState >= 2 && video.videoWidth) return resolve();
    const ok = () => { cleanup(); resolve(); };
    const bad = () => { cleanup(); reject(new Error('影片載入失敗。')); };
    const cleanup = () => {
      video.removeEventListener('loadeddata', ok);
      video.removeEventListener('error', bad);
    };
    video.addEventListener('loadeddata', ok, { once: true });
    video.addEventListener('error', bad, { once: true });
  });
}

/**
 * Per-frame driver. Uses requestVideoFrameCallback where available so we run
 * once per *decoded frame* rather than once per display refresh — that keeps
 * pose timestamps monotonic and avoids feeding the model duplicate frames.
 */
export function driveFrames(video, cb) {
  let stopped = false;
  const hasRVFC = typeof video.requestVideoFrameCallback === 'function';
  if (hasRVFC) {
    const step = (now, meta) => {
      if (stopped) return;
      cb(now, meta);
      video.requestVideoFrameCallback(step);
    };
    video.requestVideoFrameCallback(step);
  } else {
    const step = (now) => {
      if (stopped) return;
      cb(now, null);
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
  return () => { stopped = true; };
}
