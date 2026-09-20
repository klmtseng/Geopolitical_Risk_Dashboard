#!/usr/bin/env node
/**
 * Vendors the MediaPipe runtime and pose models into
 * public/badminton/vendor/ so the app works offline — on a gym Wi-Fi that
 * blocks CDNs, on a captive-portal network, or on a plane.
 *
 * The app probes for these files at startup and silently falls back to the
 * public CDN when they are absent, so running this is optional.
 *
 *   node scripts/fetch-badminton-assets.mjs            # runtime + lite & full
 *   node scripts/fetch-badminton-assets.mjs --all      # ...also the heavy model
 *   node scripts/fetch-badminton-assets.mjs --models lite
 *
 * The output is ~25-60 MB and is git-ignored on purpose: it is a build
 * artefact, not source.
 */

import { createWriteStream } from 'node:fs';
import { mkdir, rm, readdir, rename, stat } from 'node:fs/promises';
import { pipeline } from 'node:stream/promises';
import { Readable } from 'node:stream';
import { createGunzip } from 'node:zlib';
import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const VENDOR = path.join(ROOT, 'public', 'badminton', 'vendor');
const LIB_VERSION = '1.0.1';

const MODEL_BASE = 'https://storage.googleapis.com/mediapipe-models/pose_landmarker';
const MODELS = {
  lite: `${MODEL_BASE}/pose_landmarker_lite/float16/1/pose_landmarker_lite.task`,
  full: `${MODEL_BASE}/pose_landmarker_full/float16/1/pose_landmarker_full.task`,
  heavy: `${MODEL_BASE}/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task`,
};

const args = process.argv.slice(2);
const wantAll = args.includes('--all');
const explicit = args.includes('--models')
  ? args[args.indexOf('--models') + 1]?.split(',').map((s) => s.trim()).filter(Boolean)
  : null;
const variants = explicit ?? (wantAll ? Object.keys(MODELS) : ['lite', 'full']);

const human = (b) => (b > 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${(b / 1024).toFixed(0)} KB`);

async function download(url, dest) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${url}`);
  await mkdir(path.dirname(dest), { recursive: true });
  await pipeline(Readable.fromWeb(res.body), createWriteStream(dest));
  const { size } = await stat(dest);
  console.log(`  ✓ ${path.relative(ROOT, dest)} (${human(size)})`);
}

function run(cmd, cmdArgs, cwd) {
  return new Promise((resolve, reject) => {
    const p = spawn(cmd, cmdArgs, { cwd, stdio: 'inherit' });
    p.on('error', reject);
    p.on('close', (code) => (code === 0 ? resolve() : reject(new Error(`${cmd} exited ${code}`))));
  });
}

async function fetchRuntime() {
  console.log(`\n▸ MediaPipe tasks-vision ${LIB_VERSION}`);
  const meta = await fetch(`https://registry.npmjs.org/@mediapipe/tasks-vision/${LIB_VERSION}`);
  if (!meta.ok) throw new Error(`npm metadata lookup failed: ${meta.status}`);
  const tarball = (await meta.json()).dist.tarball;

  const tmp = path.join(VENDOR, '.tmp');
  await rm(tmp, { recursive: true, force: true });
  await mkdir(tmp, { recursive: true });

  const tgz = path.join(tmp, 'pkg.tgz');
  await download(tarball, tgz);
  await run('tar', ['xzf', tgz, '-C', tmp]);

  const pkg = path.join(tmp, 'package');
  for (const name of ['vision_bundle.mjs', 'vision_bundle.mjs.map']) {
    await rename(path.join(pkg, name), path.join(VENDOR, name)).catch(() => {});
  }
  await rm(path.join(VENDOR, 'wasm'), { recursive: true, force: true });
  await rename(path.join(pkg, 'wasm'), path.join(VENDOR, 'wasm'));
  await rm(tmp, { recursive: true, force: true });

  const files = await readdir(path.join(VENDOR, 'wasm'));
  console.log(`  ✓ vendor/wasm (${files.length} files)`);
}

async function fetchModels() {
  console.log(`\n▸ Pose models: ${variants.join(', ')}`);
  for (const v of variants) {
    const url = MODELS[v];
    if (!url) { console.warn(`  ! unknown model "${v}", skipping`); continue; }
    await download(url, path.join(VENDOR, 'models', path.basename(url)));
  }
}

try {
  await mkdir(VENDOR, { recursive: true });
  await fetchRuntime();
  await fetchModels();
  console.log(`\n✅ Done. ${path.relative(ROOT, VENDOR)} is now self-hosted; the app will prefer it over the CDN.\n`);
} catch (err) {
  console.error(`\n❌ ${err.message}`);
  console.error('The app still works without this step — it falls back to the public CDN.\n');
  process.exitCode = 1;
}
