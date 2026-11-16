<script>
  import { onMount, onDestroy } from 'svelte';
  import L from 'leaflet';
  import 'leaflet/dist/leaflet.css';

  export let events = []; // all events from App.svelte
  export let highlight = []; // events drawn as lock-on reticles (the target list)
  export let focus = null; // event the radar should lock onto

  let mapContainer;
  let mapInstance = null;
  let dotLayer = null;
  let reticleLayer = null;
  let cursor = null; // { lat, lon } under the pointer
  const reticles = new Map(); // event -> marker

  const GREEN = '#3dff9a';
  const DIM = '#1f7a53';
  const AMBER = '#ffb000';
  const RED = '#ff4b3a';

  const riskColor = (risk) => (risk > 70 ? RED : risk > 40 ? AMBER : risk > 10 ? GREEN : DIM);
  const pad = (n, width) => String(n).padStart(width, '0');

  function coords(event) {
    if (event.lat == null || event.lon == null) return null;
    const lat = parseFloat(event.lat);
    const lon = parseFloat(event.lon);
    return isNaN(lat) || isNaN(lon) ? null : [lat, lon];
  }

  function formatCoord(value, positive, negative) {
    return `${Math.abs(value).toFixed(2).padStart(6, '0')}${value >= 0 ? positive : negative}`;
  }

  // Popup built from DOM nodes so event text is never parsed as HTML.
  function popupContent(event) {
    const root = document.createElement('div');
    root.className = 'hud-popup';

    const title = document.createElement('strong');
    title.textContent = event.title || 'UNIDENTIFIED';
    root.appendChild(title);

    const risk = document.createElement('div');
    risk.textContent = `RISK ${event.risk_score != null ? pad(event.risk_score, 3) : '---'}  ·  ${(event.tag || 'n/a').toUpperCase()}`;
    root.appendChild(risk);

    if (/^https?:\/\//.test(event.source_url || '')) {
      const link = document.createElement('a');
      link.href = event.source_url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = 'OPEN SOURCE ▸';
      root.appendChild(link);
    }
    return root;
  }

  function reticleIcon(event, index) {
    const color = riskColor(event.risk_score || 0);
    return L.divIcon({
      className: 'hud-reticle-wrap',
      iconSize: [34, 34],
      iconAnchor: [17, 17],
      popupAnchor: [0, -14],
      html: `<div class="hud-reticle" style="--c:${color}">
        <svg viewBox="0 0 34 34" aria-hidden="true">
          <path d="M2 10V2h8M24 2h8v8M32 24v8h-8M10 32H2v-8" fill="none" stroke="currentColor" stroke-width="2"/>
          <path d="M17 9v5M17 20v5M9 17h5M20 17h5" stroke="currentColor" stroke-width="1.2"/>
          <rect x="15.5" y="15.5" width="3" height="3" fill="currentColor"/>
        </svg>
        <span>${pad(index + 1, 2)}</span>
      </div>`
    });
  }

  function drawMarkers() {
    if (!mapInstance) return;
    dotLayer.clearLayers();
    reticleLayer.clearLayers();
    reticles.clear();

    const targets = new Set(highlight);

    for (const event of events || []) {
      const position = coords(event);
      if (!position || targets.has(event)) continue;
      const risk = event.risk_score || 0;
      const color = riskColor(risk);
      L.circleMarker(position, {
        radius: Math.max(2, Math.min(2 + risk / 12, 9)),
        color,
        weight: 1,
        fillColor: color,
        fillOpacity: 0.35
      })
        .bindPopup(() => popupContent(event))
        .addTo(dotLayer);
    }

    (highlight || []).forEach((event, index) => {
      const position = coords(event);
      if (!position) return;
      const marker = L.marker(position, {
        icon: reticleIcon(event, index),
        zIndexOffset: 1000 - index,
        keyboard: false
      })
        .bindPopup(() => popupContent(event))
        .addTo(reticleLayer);
      reticles.set(event, marker);
    });
  }

  function lockOn(event) {
    if (!mapInstance || !event) return;
    const position = coords(event);
    if (!position) return;
    mapInstance.flyTo(position, Math.max(mapInstance.getZoom(), 5), { duration: 0.8 });
    const marker = reticles.get(event);
    if (marker) marker.openPopup();
  }

  onMount(() => {
    mapInstance = L.map(mapContainer, { worldCopyJump: true, minZoom: 2 }).setView([20, 10], 2);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      className: 'hud-tiles'
    }).addTo(mapInstance);

    dotLayer = L.layerGroup().addTo(mapInstance);
    reticleLayer = L.layerGroup().addTo(mapInstance);

    mapInstance.on('mousemove', (e) => {
      const wrapped = e.latlng.wrap();
      cursor = { lat: wrapped.lat, lon: wrapped.lng };
    });
    mapInstance.on('mouseout', () => (cursor = null));

    drawMarkers();
  });

  onDestroy(() => {
    if (mapInstance) {
      mapInstance.remove();
      mapInstance = null;
    }
  });

  // Redraw only when the data changes, not on every pointer move.
  $: if (mapInstance) {
    events;
    highlight;
    drawMarkers();
  }

  $: if (mapInstance && focus) lockOn(focus);
</script>

<div class="radar">
  <div bind:this={mapContainer} class="map"></div>
  <div class="sweep" aria-hidden="true"></div>
  <div class="rings" aria-hidden="true"></div>
  <div class="coords">
    {#if cursor}
      LAT {formatCoord(cursor.lat, 'N', 'S')} &nbsp; LON {formatCoord(cursor.lon, 'E', 'W')}
    {:else}
      LAT ---.-- &nbsp; LON ---.--
    {/if}
  </div>
  <div class="legend" aria-hidden="true">
    <span style="--c: {DIM}">≤10</span>
    <span style="--c: {GREEN}">11–40</span>
    <span style="--c: {AMBER}">41–70</span>
    <span style="--c: {RED}">&gt;70</span>
  </div>
</div>
{#if events.length === 0}
  <p class="empty">NO CONTACTS</p>
{/if}

<style>
  .radar {
    position: relative;
    height: min(68vh, 640px);
    min-height: 360px;
    overflow: hidden;
    border: 1px solid var(--hud-green-dim);
    background: #020503;
  }

  .map {
    position: absolute;
    inset: 0;
    background: #020503;
  }

  /* Rotating radar sweep, drawn over the map but transparent to input */
  .sweep {
    position: absolute;
    left: 50%;
    top: 50%;
    width: 220%;
    aspect-ratio: 1;
    margin: -110% 0 0 -110%;
    pointer-events: none;
    z-index: 500;
    background: conic-gradient(
      from 0deg,
      rgba(61, 255, 154, 0) 0deg,
      rgba(61, 255, 154, 0) 300deg,
      rgba(61, 255, 154, 0.22) 358deg,
      rgba(61, 255, 154, 0.5) 360deg
    );
    animation: hud-sweep 7s linear infinite;
  }

  .rings {
    position: absolute;
    inset: 0;
    pointer-events: none;
    z-index: 501;
    background:
      linear-gradient(rgba(61, 255, 154, 0.25), rgba(61, 255, 154, 0.25)) center / 1px 100% no-repeat,
      linear-gradient(rgba(61, 255, 154, 0.25), rgba(61, 255, 154, 0.25)) center / 100% 1px no-repeat,
      repeating-radial-gradient(circle at center, transparent 0 89px, rgba(61, 255, 154, 0.2) 89px 90px);
  }

  .coords,
  .legend {
    position: absolute;
    z-index: 600;
    padding: 4px 8px;
    font-size: 0.7rem;
    background: rgba(4, 9, 7, 0.8);
    border: 1px solid var(--hud-green-dim);
    color: var(--hud-green);
    pointer-events: none;
    font-variant-numeric: tabular-nums;
  }

  .coords {
    left: 8px;
    bottom: 8px;
  }

  .legend {
    right: 8px;
    top: 8px;
    display: flex;
    gap: 10px;
  }

  .legend span {
    color: var(--c);
  }
  .legend span::before {
    content: '■ ';
  }

  .empty {
    margin: 8px 0 0;
    text-align: center;
    font-size: 0.8rem;
    color: var(--hud-green-dim);
  }

  /* Recolour the map tiles to a dark green monochrome */
  :global(.hud-tiles) {
    filter: grayscale(1) invert(1) contrast(1.15) brightness(0.55) sepia(1) hue-rotate(75deg) saturate(2.2);
  }

  :global(.leaflet-container) {
    background: #020503;
    font-family: var(--hud-font);
  }

  :global(.hud-reticle-wrap) {
    background: none;
    border: 0;
  }

  :global(.hud-reticle) {
    position: relative;
    width: 34px;
    height: 34px;
    color: var(--c);
    filter: drop-shadow(0 0 4px var(--c));
    animation: hud-lock 0.7s ease-out both;
  }

  :global(.hud-reticle svg) {
    width: 100%;
    height: 100%;
    animation: hud-blink 1.6s steps(1) infinite;
  }

  :global(.hud-reticle span) {
    position: absolute;
    left: 100%;
    top: -4px;
    margin-left: 2px;
    font-size: 10px;
    line-height: 1;
    color: var(--c);
    text-shadow: 0 0 3px #000, 0 0 3px #000;
  }

  :global(.leaflet-popup-content-wrapper),
  :global(.leaflet-popup-tip) {
    background: rgba(4, 9, 7, 0.95);
    color: var(--hud-text);
    border: 1px solid var(--hud-green);
    border-radius: 0;
    box-shadow: 0 0 14px rgba(61, 255, 154, 0.35);
  }

  :global(.leaflet-popup-content) {
    margin: 10px 12px;
    font-size: 0.75rem;
  }

  :global(.hud-popup) {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  :global(.hud-popup strong) {
    color: var(--hud-green);
    font-weight: normal;
    text-transform: uppercase;
  }

  :global(.hud-popup a) {
    color: var(--hud-amber);
    text-decoration: none;
  }

  :global(.leaflet-container a.leaflet-popup-close-button) {
    color: var(--hud-green);
  }

  :global(.leaflet-bar a.leaflet-disabled) {
    background: rgba(4, 9, 7, 0.9);
    color: var(--hud-green-dim);
    opacity: 0.6;
  }

  :global(.leaflet-bar a),
  :global(.leaflet-bar a:hover) {
    background: rgba(4, 9, 7, 0.9);
    color: var(--hud-green);
    border-color: var(--hud-green-dim);
    border-radius: 0;
  }

  :global(.leaflet-bar) {
    border: 1px solid var(--hud-green-dim);
    border-radius: 0;
  }

  :global(.leaflet-control-attribution) {
    background: rgba(4, 9, 7, 0.75) !important;
    color: var(--hud-green-dim);
    font-size: 9px;
  }

  :global(.leaflet-control-attribution a) {
    color: var(--hud-green-dim);
  }
</style>
