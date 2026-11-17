<script>
  import { onMount, onDestroy, createEventDispatcher } from 'svelte';
  import L from 'leaflet';
  import 'leaflet/dist/leaflet.css';
  import { feature, mesh } from 'topojson-client';

  export let events = []; // all events from App.svelte
  export let highlight = []; // events drawn as lock-on reticles (the target list)
  export let focus = null; // selected hotspot: ringed on the map
  export let flyToFocus = true; // move the map to it (off when it was picked on the map itself)

  const dispatch = createEventDispatcher();

  let mapContainer;
  let mapInstance = null;
  let dotLayer = null;
  let reticleLayer = null;
  let focusLayer = null;
  let cursor = null; // { lat, lon } under the pointer

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

  // Markers only report hover and click; the brief itself is shown in a fixed
  // panel under the map, so nothing floats over the map or the lists.
  function wire(marker, event) {
    return marker
      .on('mouseover', () => dispatch('hover', event))
      .on('mouseout', () => dispatch('hover', null))
      .on('click', () => dispatch('select', event));
  }

  function reticleIcon(event, index) {
    const color = riskColor(event.risk_score || 0);
    return L.divIcon({
      className: 'hud-reticle-wrap',
      iconSize: [34, 34],
      iconAnchor: [17, 17],
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

  const WORLD_VIEW = [[-56, -168], [80, 178]];

  // Shapes that cross the 180° meridian (eastern Russia, Fiji) jump from +180 to
  // -180 mid-outline, which a flat map draws as a line across the whole world.
  // Make each outline's longitudes continuous, letting it run slightly past ±180.
  function unwrapLine(line) {
    let offset = 0;
    let sum = 0;
    const out = line.map(([lon, lat], i) => {
      if (i > 0) {
        const step = lon - line[i - 1][0];
        if (step > 180) offset -= 360;
        else if (step < -180) offset += 360;
      }
      sum += lon + offset;
      return [lon + offset, lat];
    });
    // keep the outline in the copy of the world where most of it lies
    const shift = -360 * Math.round(sum / out.length / 360);
    return shift ? out.map(([lon, lat]) => [lon + shift, lat]) : out;
  }

  function unwrapAntimeridian(geo) {
    const walk = (coords, depth) => (depth === 1 ? unwrapLine(coords) : coords.map((c) => walk(c, depth - 1)));
    const DEPTH = { LineString: 1, MultiLineString: 2, Polygon: 2, MultiPolygon: 3 };
    const fix = (geometry) =>
      DEPTH[geometry.type] ? { ...geometry, coordinates: walk(geometry.coordinates, DEPTH[geometry.type]) } : geometry;
    if (geo.type === 'Feature') return { ...geo, geometry: fix(geo.geometry) };
    if (geo.type === 'FeatureCollection') return { ...geo, features: geo.features.map(unwrapAntimeridian) };
    return fix(geo);
  }

  // Vector world outline bundled with the app (Natural Earth 1:50m), so the
  // map is sharp at every zoom and does not depend on a tile server.
  async function drawWorld() {
    const { default: world } = await import('world-atlas/countries-50m.json');
    if (!mapInstance) return;
    const canvas = L.canvas({ padding: 0.5 });
    const base = { renderer: canvas, interactive: false, pane: 'tilePane' };

    const land = unwrapAntimeridian(feature(world, world.objects.land));

    L.geoJSON(land, {
      ...base,
      style: { stroke: false, fillColor: '#0f3a29', fillOpacity: 1 }
    }).addTo(mapInstance);

    // internal borders, then the coastline on top
    L.geoJSON(unwrapAntimeridian(mesh(world, world.objects.countries, (a, b) => a !== b)), {
      ...base,
      style: { color: '#2a9a68', weight: 0.7, opacity: 0.8, fill: false }
    }).addTo(mapInstance);

    L.geoJSON(land, {
      ...base,
      style: { color: GREEN, weight: 1.3, opacity: 1, fill: false }
    }).addTo(mapInstance);
  }

  function drawMarkers() {
    if (!mapInstance) return;
    dotLayer.clearLayers();
    reticleLayer.clearLayers();

    const targets = new Set(highlight);

    for (const event of events || []) {
      const position = coords(event);
      if (!position || targets.has(event)) continue;
      const risk = event.risk_score || 0;
      const color = riskColor(risk);
      wire(
        L.circleMarker(position, {
          // area grows with the number of outlets reporting
          radius: Math.max(2, Math.min(1.5 + 1.1 * Math.sqrt(event.outlets || 1), 11)),
          color,
          weight: 1,
          fillColor: color,
          fillOpacity: 0.22
        }),
        event
      ).addTo(dotLayer);
    }

    (highlight || []).forEach((event, index) => {
      const position = coords(event);
      if (!position) return;
      wire(
        L.marker(position, {
          icon: reticleIcon(event, index),
          zIndexOffset: 1000 - index,
          keyboard: false
        }),
        event
      ).addTo(reticleLayer);
    });
  }

  function showFocus(event, fly) {
    if (!mapInstance) return;
    focusLayer.clearLayers();
    const position = event && coords(event);
    if (!position) return;
    L.circleMarker(position, { radius: 22, color: AMBER, weight: 2, fill: false, interactive: false, className: 'hud-focus' })
      .addTo(focusLayer);
    if (fly) mapInstance.flyTo(position, Math.max(mapInstance.getZoom(), 5), { duration: 0.8 });
  }

  onMount(() => {
    mapInstance = L.map(mapContainer, {
      zoomSnap: 0.25,
      minZoom: 1,
      maxZoom: 7,
      maxBounds: [[-89, -200], [89, 200]],
      maxBoundsViscosity: 0.8,
      attributionControl: false
    });
    mapInstance.fitBounds(WORLD_VIEW);
    L.control
      .attribution({ prefix: false })
      .addAttribution('Map: Natural Earth')
      .addTo(mapInstance);

    drawWorld();

    dotLayer = L.layerGroup().addTo(mapInstance);
    reticleLayer = L.layerGroup().addTo(mapInstance);
    focusLayer = L.layerGroup().addTo(mapInstance);

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

  $: if (mapInstance) showFocus(focus, flyToFocus);
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
    height: min(50vh, 520px);
    min-height: 320px;
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
      rgba(61, 255, 154, 0.07) 358deg,
      rgba(61, 255, 154, 0.22) 360deg
    );
    animation: hud-sweep 7s linear infinite;
  }

  .rings {
    position: absolute;
    inset: 0;
    pointer-events: none;
    z-index: 501;
    background:
      linear-gradient(rgba(61, 255, 154, 0.12), rgba(61, 255, 154, 0.12)) center / 1px 100% no-repeat,
      linear-gradient(rgba(61, 255, 154, 0.12), rgba(61, 255, 154, 0.12)) center / 100% 1px no-repeat,
      repeating-radial-gradient(circle at center, transparent 0 139px, rgba(61, 255, 154, 0.1) 139px 140px);
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

  :global(.leaflet-container) {
    background: #03100b;
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

  :global(.hud-focus) {
    filter: drop-shadow(0 0 6px #ffb000);
    stroke-dasharray: 10 6;
    animation: hud-blink 1.2s steps(1) infinite;
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
