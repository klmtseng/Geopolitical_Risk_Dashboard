<script>
  import { onMount } from 'svelte';
  import Map from './components/Map.svelte';
  import Timeseries from './components/Timeseries.svelte';
  import Hotlist from './components/Hotlist.svelte';
  import Panel from './components/Panel.svelte';
  import SevenSeg from './components/SevenSeg.svelte';

  let allEvents = [];
  let dailyAverageRiskData = []; // For Timeseries: array of {date: 'YYYY-MM-DD', avgRisk: X}
  let top10Events = [];
  let focusEvent = null; // event selected in the target list; the map locks onto it
  let loadState = 'loading'; // 'loading' | 'ready' | 'error'
  let now = new Date();
  let dataUpdatedAt = null; // Last-Modified of latest.json, when the server reports it

  // Data files live next to index.html; resolve them relative to the page so
  // the app also works under a GitHub Pages project path.
  const dataUrl = (name) => `${import.meta.env.BASE_URL}data/${name}`;

  async function fetchHistory() {
    try {
      const response = await fetch(dataUrl('history.json'));
      if (!response.ok) return null;
      const history = await response.json();
      return Array.isArray(history) && history.length > 0 ? history : null;
    } catch (error) {
      return null;
    }
  }

  const pad = (n, width = 2) => String(n).padStart(width, '0');
  const utcClock = (d) => `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
  const utcStamp = (d) =>
    `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}Z`;

  $: maxRisk = allEvents.reduce((max, e) => Math.max(max, e.risk_score || 0), 0);
  $: hostileCount = allEvents.filter((e) => e.tag === 'conflict').length;
  // Most recent day that has an average
  $: latestAverage = [...dailyAverageRiskData].reverse().find((d) => d.avgRisk != null)?.avgRisk ?? null;
  $: threatColor =
    maxRisk > 70 ? 'var(--hud-red)' : maxRisk > 40 ? 'var(--hud-amber)' : 'var(--hud-green)';
  $: threatLabel = maxRisk > 70 ? 'CONDITION RED' : maxRisk > 40 ? 'CONDITION AMBER' : 'CONDITION GREEN';

  onMount(() => {
    const timer = setInterval(() => (now = new Date()), 1000);
    loadData();
    return () => clearInterval(timer);
  });

  async function loadData() {
    try {
      const response = await fetch(dataUrl('latest.json'));
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      allEvents = data;
      processEventData(data);

      const lastModified = response.headers.get('last-modified');
      if (lastModified && !isNaN(Date.parse(lastModified))) {
        dataUpdatedAt = new Date(lastModified);
      }

      // Prefer the per-day history built by the ETL from the archive; the
      // latest snapshot alone only covers about one day.
      const history = await fetchHistory();
      if (history) {
        dailyAverageRiskData = history;
      }
      loadState = 'ready';
    } catch (error) {
      console.error("Failed to fetch or process event data:", error);
      allEvents = []; // Ensure it's an array even on error
      loadState = 'error';
    }
  }

  function processEventData(events) {
    if (!events || events.length === 0) {
        dailyAverageRiskData = [];
        top10Events = [];
        return;
    }

    // Calculate Top 10 Events by risk_score
    top10Events = [...events] // Create a new array to sort
      .sort((a, b) => b.risk_score - a.risk_score)
      .slice(0, 10);

    // Calculate Global Average Risk for the last 14 days
    const riskByDay = {}; // Store sum of risks and count for each day
    const today = new Date();
    const fourteenDaysAgo = new Date(today);
    fourteenDaysAgo.setDate(today.getDate() - 14);

    events.forEach(event => {
      const eventDate = new Date(event.timestamp);
      if (eventDate >= fourteenDaysAgo && eventDate <= today) {
        const dayStr = eventDate.toISOString().split('T')[0]; // YYYY-MM-DD
        if (!riskByDay[dayStr]) {
          riskByDay[dayStr] = { totalRisk: 0, count: 0 };
        }
        riskByDay[dayStr].totalRisk += event.risk_score;
        riskByDay[dayStr].count += 1;
      }
    });

    const calculatedDailyAverages = [];
    for (let i = 0; i < 14; i++) {
        const date = new Date(today);
        date.setDate(today.getDate() - i);
        const dayStr = date.toISOString().split('T')[0];

        if (riskByDay[dayStr] && riskByDay[dayStr].count > 0) {
            calculatedDailyAverages.push({
                date: dayStr,
                avgRisk: Math.round(riskByDay[dayStr].totalRisk / riskByDay[dayStr].count)
            });
        } else {
            // No events for that day: leave a gap rather than a misleading 0
            calculatedDailyAverages.push({ date: dayStr, avgRisk: null });
        }
    }
    // Data for chart should be in chronological order
    dailyAverageRiskData = calculatedDailyAverages.sort((a,b) => new Date(a.date) - new Date(b.date));
  }

</script>

<main>
  <header class="topbar">
    <div class="ident">
      <span class="unit">GRD-01</span>
      <h1>Geopolitical Risk <span>Tactical Display</span></h1>
    </div>
    <dl class="readouts">
      <div><dt>Contacts</dt><dd>{pad(allEvents.length, 4)}</dd></div>
      <div><dt>Hostile</dt><dd class="amber">{pad(hostileCount, 3)}</dd></div>
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

  <div class="dashboard-layout">
    <div class="map-container">
      <Panel title="Tactical Radar" code="SCN-A">
        <Map events={allEvents} highlight={top10Events} focus={focusEvent} />
      </Panel>
    </div>
    <aside class="sidebar">
      <Panel title="Threat Index" code="AVG/24H">
        <div class="threat">
          <SevenSeg value={latestAverage == null ? '---' : pad(latestAverage, 3)} color={threatColor} height={56} />
          <div class="threat-meta">
            <span>MEAN RISK</span>
            <span>SCALE 000–100</span>
            <span class="amber">PEAK {pad(maxRisk, 3)}</span>
          </div>
        </div>
        <Timeseries {dailyAverageRiskData} />
      </Panel>
      <Panel title="Target List" code="TOP 10">
        <Hotlist events={top10Events} selected={focusEvent} on:select={(e) => (focusEvent = e.detail)} />
      </Panel>
    </aside>
  </div>

  <footer>
    <span>SRC: GDELT 2.0 EVENT EXPORT</span>
    <span>{dataUpdatedAt ? `DATA ${utcStamp(dataUpdatedAt)}` : 'DATA TIME UNKNOWN'}</span>
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
