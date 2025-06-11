<script context="module">
  // Attempt to import Leaflet CSS.
  // This ensures CSS is requested when the component module is loaded.
  // Actual loading and application depend on the build system (Vite/SvelteKit)
  // and whether this component is server-side rendered initially.
  // For client-side only rendering of the map, this is generally effective.
  if (typeof window !== 'undefined') {
    import('leaflet/dist/leaflet.css');
  }
</script>

<script>
  import { onMount, onDestroy, afterUpdate } from 'svelte';
  import L from 'leaflet';

  export let events = []; // Received from App.svelte

  let mapContainer; // Bound to the div element
  let mapInstance = null;
  let markerLayerGroup = null;

  onMount(async () => {
    // Ensure Leaflet is only initialized on the client-side
    if (typeof window !== 'undefined') {
      if (!mapContainer) {
        console.error("Map container not found onMount.");
        return;
      }

      // Initialize the map
      mapInstance = L.map(mapContainer).setView([20, 0], 2); // Default view

      // Add OpenStreetMap tile layer
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
      }).addTo(mapInstance);

      // Initialize marker layer group
      markerLayerGroup = L.layerGroup().addTo(mapInstance);

      // Initial drawing of markers
      updateMarkers(events);
    }
  });

  afterUpdate(() => {
    // Called after props update. Redraw markers if map is initialized.
    if (mapInstance && markerLayerGroup) {
      updateMarkers(events);
    }
  });

  onDestroy(() => {
    if (mapInstance) {
      mapInstance.remove();
      mapInstance = null;
      markerLayerGroup = null; // Clear reference
    }
  });

  function updateMarkers(currentEvents) {
    if (!mapInstance || !markerLayerGroup) {
      return;
    }

    markerLayerGroup.clearLayers(); // Clear existing markers

    if (!currentEvents || currentEvents.length === 0) {
      return;
    }

    currentEvents.forEach(event => {
      if (event.lat != null && event.lon != null) { // Check for null or undefined
        const lat = parseFloat(event.lat);
        const lon = parseFloat(event.lon);

        if (isNaN(lat) || isNaN(lon)) return; // Skip if parsing fails

        let radius = 5 + (event.risk_score || 0) / 10; // Default risk_score to 0 if undefined
        radius = Math.max(5, Math.min(radius, 20)); // Cap radius (e.g., 5-20)

        let color = 'blue'; // Default color
        const risk = event.risk_score || 0;
        if (risk > 70) {
          color = 'red';
        } else if (risk > 40) {
          color = 'orange';
        } else if (risk > 10) {
          color = 'yellow';
        } else {
          color = 'green'; // Low risk or default
        }

        const marker = L.circleMarker([lat, lon], {
          radius: radius,
          color: color,
          fillColor: color,
          fillOpacity: 0.6,
          weight: 1 // Border weight
        });

        // Ensure all parts of the popup content are defined
        const title = event.title || "No Title";
        const riskScoreDisplay = event.risk_score != null ? event.risk_score : "N/A";
        const sourceUrl = event.source_url || "#";
        const sourceLink = sourceUrl !== "#" ? `<a href="${sourceUrl}" target="_blank" rel="noopener noreferrer">Source</a>` : "No Source";

        marker.bindPopup(
          `<b>${title}</b><br>Risk Score: ${riskScoreDisplay}<br>${sourceLink}`
        );

        marker.addTo(markerLayerGroup);
      }
    });
  }
</script>

<div bind:this={mapContainer} style="height: 500px; width: 100%;">
  <!-- Map will be rendered here by Leaflet -->
</div>
{#if !mapInstance && typeof window !== 'undefined'}
  <p style="text-align: center;">Initializing map...</p>
{:else if typeof window !== 'undefined' && events.length === 0}
  <p style="text-align: center;">No event data to display on the map.</p>
{/if}

<style>
  /* Ensure the map container has a defined height, as required by Leaflet. */
  /* The style attribute on the div takes precedence but this can be a fallback. */
  div[bind:this={mapContainer}] {
    height: 500px;
    width: 100%;
    background-color: #eee; /* Placeholder background */
  }

  /* You might need to ensure Leaflet's CSS is properly scoped or globally applied.
     If using `import 'leaflet/dist/leaflet.css';` in <script context="module">,
     Vite/SvelteKit should handle it. If not, you might need to add it to a global
     stylesheet or app.html. The :global selector might be needed for some leaflet styles
     if they are not specific enough. */
  :global(.leaflet-popup-content-wrapper) {
    border-radius: 5px !important; /* Example: Customize popup style */
  }
  :global(.leaflet-popup-content b) {
    font-weight: bold;
  }
</style>
