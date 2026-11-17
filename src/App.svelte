<script>
  import { onMount } from 'svelte';
  import Map from './components/Map.svelte';
  import Timeseries from './components/Timeseries.svelte';
  import Hotlist from './components/Hotlist.svelte';
  import Brief from './components/Brief.svelte';
  import Panel from './components/Panel.svelte';
  import Ticker from './components/Ticker.svelte';
  import SevenSeg from './components/SevenSeg.svelte';

  // Ranking windows offered by the ETL, shortest first.
  const WINDOWS = [
    { id: '1h', label: '1H' },
    { id: '6h', label: '6H' },
    { id: '24h', label: '24H' },
    { id: '7d', label: '7D' }
  ];
  const WINDOW_KEY = 'grd.window';

  let payload = null; // hotspots.json: { updated, data_through, windows }
  let windowId = '24h';
  let dailyAverageRiskData = []; // For Timeseries: array of {date: 'YYYY-MM-DD', avgRisk: X}
  let focusEvent = null; // selected hotspot (ringed on the map)
  let focusFromMap = false; // picked on the map itself, so the map should not move
  let hoverEvent = null; // hotspot under the pointer, previewed in the brief panel
  let loadState = 'loading'; // 'loading' | 'ready' | 'error'
  let now = new Date();

  // Data files live next to index.html; resolve them relative to the page so
  // the app also works under a GitHub Pages project path.
  const dataUrl = (name) => `${import.meta.env.BASE_URL}data/${name}`;

  const pad = (n, width = 2) => String(n).padStart(width, '0');
  const utcClock = (d) => `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
  // "20261116104500" -> "2026-11-16 10:45Z"
  const exportStamp = (ts) =>
    ts ? `${ts.slice(0, 4)}-${ts.slice(4, 6)}-${ts.slice(6, 8)} ${ts.slice(8, 10)}:${ts.slice(10, 12)}Z` : null;

  $: current = payload?.windows?.[windowId] ?? null;
  $: hotspots = current?.hotspots ?? [];
  $: top10 = hotspots.slice(0, 10); // the ETL already ranks them
  $: maxRisk = hotspots.reduce((max, h) => Math.max(max, h.risk_score || 0), 0);
  $: surging = hotspots.filter((h) => h.surge != null && h.surge >= 3 && h.outlets >= 5).length;
  $: threatColor =
    maxRisk > 70 ? 'var(--hud-red)' : maxRisk > 40 ? 'var(--hud-amber)' : 'var(--hud-green)';
  $: threatLabel = maxRisk > 70 ? 'CONDITION RED' : maxRisk > 40 ? 'CONDITION AMBER' : 'CONDITION GREEN';
  $: partial = current && current.hours_covered < current.hours;
  // One brief at a time, always in the same place: what is hovered, else what is selected, else the top hotspot.
  $: briefEvent = hoverEvent || focusEvent || top10[0] || null;
  $: briefMode = hoverEvent ? 'PREVIEW' : focusEvent ? 'LOCKED' : 'TOP';

  function select(hotspot, fromMap) {
    focusFromMap = fromMap;
    focusEvent = hotspot;
  }

  onMount(() => {
    try {
      const saved = localStorage.getItem(WINDOW_KEY);
      if (WINDOWS.some((w) => w.id === saved)) windowId = saved;
    } catch {
      // storage unavailable: keep the default
    }
    const timer = setInterval(() => (now = new Date()), 1000);
    loadData();
    return () => clearInterval(timer);
  });

  function setWindow(id) {
    windowId = id;
    focusEvent = null;
    hoverEvent = null;
    try {
      localStorage.setItem(WINDOW_KEY, id);
    } catch {
      // ignore
    }
  }

  async function loadJson(name) {
    const response = await fetch(dataUrl(name));
    if (!response.ok) throw new Error(`${name}: HTTP ${response.status}`);
    return response.json();
  }

  async function loadData() {
    try {
      payload = await loadJson('hotspots.json');
      loadState = 'ready';
    } catch (error) {
      console.error('Failed to load hotspot data:', error);
      loadState = 'error';
      return;
    }
    try {
      const history = await loadJson('history.json');
      if (Array.isArray(history)) dailyAverageRiskData = history;
    } catch {
      // the trend chart simply stays empty
    }
  }
</script>

<main>
  <header class="topbar">
    <div class="ident">
      <span class="unit">GRD-01</span>
      <h1>Geopolitical Risk <span>Tactical Display</span></h1>
    </div>
    <dl class="readouts">
      <div><dt>Hotspots</dt><dd>{pad(current?.total ?? 0, 4)}</dd></div>
      <div><dt>Surging</dt><dd class="amber">{pad(surging, 3)}</dd></div>
      <div><dt>Peak</dt><dd style="color: {threatColor}">{pad(maxRisk, 3)}</dd></div>
      <div><dt>UTC</dt><dd>{utcClock(now)}</dd></div>
    </dl>
    <div class="condition" style="--c: {threatColor}">
      {#if loadState === 'loading'}
        <span class="blink">LINK ESTABLISHING…</span>
      {:else if loadState === 'error'}
        <span class="blink" style="--c: var(--hud-red)">NO SIGNAL</span>
      {:else}
        <span>{threatLabel}</span>
      {/if}
    </div>
  </header>

  <Ticker {dataUrl} />

  <div class="windowbar">
    <span class="lbl">WINDOW</span>
    <div class="windows" role="group" aria-label="Time window">
      {#each WINDOWS as w}
        <button type="button" class:on={windowId === w.id} aria-pressed={windowId === w.id} on:click={() => setWindow(w.id)}>
          {w.label}
        </button>
      {/each}
    </div>
    <span class="note">
      {#if current}
        RANKED BY DISTINCT OUTLETS REPORTING IN THE LAST {current.hours} H
        {#if partial}
          <b title="Hours of this window for which data has been collected so far">
            · DATA FOR {current.hours_covered} OF {current.hours} H</b>
        {/if}
      {/if}
    </span>
  </div>

  <div class="dashboard-layout">
    <div class="map-container">
      <Panel title="Tactical Radar" code="SCN-A">
        <Map
          events={hotspots}
          highlight={top10}
          focus={focusEvent}
          flyToFocus={!focusFromMap}
          on:hover={(e) => (hoverEvent = e.detail)}
          on:select={(e) => select(e.detail, true)}
        />
      </Panel>
      <div class="brief-panel">
        <Panel title="Target Brief" code={briefMode}>
          {#if briefEvent}
            <Brief event={briefEvent} />
          {:else}
            <p class="no-brief">NO HOTSPOT IN THIS WINDOW</p>
          {/if}
        </Panel>
      </div>
    </div>
    <aside class="sidebar">
      <Panel title="Threat Index" code="TOP 20 / {windowId.toUpperCase()}">
        <div class="threat">
          <SevenSeg value={current?.index == null ? '---' : pad(current.index, 3)} color={threatColor} height={56} />
          <div class="threat-meta">
            <span>MEAN OF TOP 20</span>
            <span>SCALE 000–100</span>
            <span class="amber">PEAK {pad(maxRisk, 3)}</span>
          </div>
        </div>
        <Timeseries {dailyAverageRiskData} />
      </Panel>
      <Panel title="Target List" code="TOP 10">
        <Hotlist
          events={top10}
          selected={focusEvent}
          on:select={(e) => select(e.detail, false)}
          on:hover={(e) => (hoverEvent = e.detail)}
        />
      </Panel>
    </aside>
  </div>

  <footer>
    <span>SRC: GDELT 2.0 EVENT EXPORT</span>
    <span>{payload?.data_through ? `DATA THROUGH ${exportStamp(payload.data_through)}` : 'DATA TIME UNKNOWN'}</span>
    <span>NOT FOR OPERATIONAL USE</span>
  </footer>
</main>

<style>
  main {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
    max-width: 1700px;
    margin: 0 auto;
    padding: 0 16px;
    box-sizing: border-box;
  }

  .topbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px 28px;
    padding: 12px 4px;
    border-bottom: 2px solid var(--hud-green-dim);
  }

  .ident {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-right: auto;
  }

  .unit {
    padding: 3px 8px;
    background: var(--hud-amber);
    color: #000;
    font-weight: bold;
    font-size: 0.8rem;
    white-space: nowrap;
  }

  h1 {
    margin: 0;
    font-size: 1.25rem;
    font-weight: normal;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: var(--hud-green);
    text-shadow: 0 0 8px rgba(61, 255, 154, 0.7);
  }

  h1 span {
    color: var(--hud-text);
    opacity: 0.7;
  }

  .readouts {
    display: flex;
    gap: 22px;
    margin: 0;
  }

  .readouts div {
    display: flex;
    flex-direction: column;
  }

  dt {
    font-size: 0.62rem;
    text-transform: uppercase;
    color: var(--hud-green-dim);
  }

  dd {
    margin: 0;
    font-size: 1.15rem;
    color: var(--hud-green);
    text-shadow: 0 0 6px currentColor;
    font-variant-numeric: tabular-nums;
  }

  .amber {
    color: var(--hud-amber);
  }

  .condition {
    padding: 6px 14px;
    border: 1px solid var(--c);
    color: var(--c);
    font-size: 0.85rem;
    text-shadow: 0 0 6px currentColor;
    box-shadow: inset 0 0 12px color-mix(in srgb, var(--c) 25%, transparent);
  }

  .blink {
    color: var(--c, var(--hud-green));
    animation: hud-blink 1.1s steps(1) infinite;
  }

  .windowbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px 12px;
    margin-top: 12px;
    font-size: 0.75rem;
  }

  .windowbar .lbl {
    color: var(--hud-green-dim);
  }

  .windows {
    display: flex;
    border: 1px solid var(--hud-green-dim);
  }

  .windows button {
    padding: 5px 12px;
    background: none;
    border: 0;
    border-right: 1px solid var(--hud-green-dim);
    color: var(--hud-green-dim);
    font: inherit;
    letter-spacing: inherit;
    cursor: pointer;
  }
  .windows button:last-child {
    border-right: 0;
  }
  .windows button:hover,
  .windows button:focus-visible {
    color: var(--hud-green);
    background: var(--hud-green-faint);
    outline: none;
  }
  .windows button.on {
    background: var(--hud-green);
    color: #000;
  }

  .note {
    color: var(--hud-green-dim);
  }
  .note b {
    font-weight: normal;
    color: var(--hud-amber);
  }

  .dashboard-layout {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    padding: 16px 0;
    align-items: flex-start;
  }

  .map-container {
    flex: 3;
    min-width: 300px;
  }

  .brief-panel {
    margin-top: 16px;
    /* room for a headline, summary and the facts, so the page does not jump while hovering */
    min-height: 190px;
  }

  .no-brief {
    margin: 0;
    color: var(--hud-green-dim);
    font-size: 0.8rem;
  }

  .sidebar {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 16px;
    min-width: 300px;
  }

  .threat {
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 6px;
  }

  .threat-meta {
    display: flex;
    flex-direction: column;
    gap: 3px;
    font-size: 0.68rem;
    color: var(--hud-green-dim);
  }

  footer {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: 6px 20px;
    margin-top: auto;
    padding: 10px 4px 14px;
    border-top: 1px solid var(--hud-green-dim);
    font-size: 0.68rem;
    color: var(--hud-green-dim);
  }

  @media (max-width: 768px) {
    .dashboard-layout {
      flex-direction: column;
      align-items: stretch;
    }
    .readouts {
      gap: 14px;
    }
  }
</style>
