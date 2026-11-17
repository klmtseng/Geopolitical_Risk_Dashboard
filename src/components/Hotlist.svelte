<script>
  import { createEventDispatcher } from 'svelte';
  import { actionLabel } from '../brief.js';

  export let events = []; // top events, already sorted by risk_score
  export let selected = null;

  const dispatch = createEventDispatcher();
  const pad = (n, width) => String(n).padStart(width, '0');
  const level = (risk) => (risk > 70 ? 'high' : risk > 40 ? 'medium' : 'low');
  // "Tehran, Tehran, Iran" -> "Tehran"; the country code has its own column.
  const placeName = (event) => (event.location || '').split(',')[0].trim() || event.country || 'Unknown';
  const rowName = (event) => {
    const activity = actionLabel(event);
    return activity ? `${placeName(event)}, ${activity}` : placeName(event);
  };

  // Hovering or focusing a row previews it in the brief panel (see App.svelte).
  const preview = (event) => dispatch('hover', event);

  const isLink = (url) => /^https?:\/\//.test(url || '');
</script>

{#if events && events.length > 0}
  <ol class="targets">
    {#each events as event, i}
      <li
        class={level(event.risk_score)}
        class:locked={selected === event}
        on:mouseenter={() => preview(event)}
        on:mouseleave={() => preview(null)}
        on:focusin={() => preview(event)}
        on:focusout={() => preview(null)}
      >
        <button
          type="button"
          class="lock"
          disabled={event.lat == null || event.lon == null}
          aria-label="Lock the radar onto target {i + 1}: {rowName(event)}, {event.country || 'unknown location'}"
          on:click={() => dispatch('select', event)}
        >
          <span class="idx">{pad(i + 1, 2)}</span>
          <span class="cc">{event.country || '--'}</span>
          <span class="name">
            {placeName(event)}
            <small>{actionLabel(event) || ''}</small>
          </span>
          <span class="gauge" aria-hidden="true">
            <span style="width: {Math.max(0, Math.min(100, event.risk_score || 0))}%"></span>
          </span>
          <span class="score">{event.risk_score != null ? pad(event.risk_score, 3) : '---'}</span>
          <span class="surge" class:hot={event.surge >= 3} title="Outlets now vs earlier windows of the same length">
            {event.surge != null && event.surge >= 2 ? `×${event.surge >= 10 ? Math.round(event.surge) : event.surge.toFixed(1)}` : ''}
          </span>
        </button>
        {#if isLink(event.source_url)}
          <a href={event.source_url} target="_blank" rel="noopener noreferrer" title="Open source article">SRC</a>
        {/if}
      </li>
    {/each}
  </ol>
{:else}
  <p class="empty">NO TARGETS ACQUIRED</p>
{/if}

<style>
  .targets {
    list-style: none;
    margin: 0;
    padding: 0;
    font-size: 0.8rem;
  }

  li {
    --c: var(--hud-green);
    display: flex;
    align-items: center;
    gap: 8px;
    border-bottom: 1px dashed var(--hud-green-dim);
  }
  li:last-child { border-bottom: 0; }
  li.medium { --c: var(--hud-amber); }
  li.high { --c: var(--hud-red); }

  .lock {
    flex: 1;
    min-width: 0;
    display: grid;
    grid-template-columns: 2ch 2ch minmax(0, 1fr) 40px 3ch 4ch;
    align-items: center;
    gap: 8px;
    padding: 5px 4px;
    background: none;
    border: 0;
    color: var(--hud-text);
    font: inherit;
    letter-spacing: inherit;
    text-align: left;
    cursor: pointer;
  }
  .lock:disabled { cursor: default; }
  .lock:hover:not(:disabled),
  .lock:focus-visible,
  li.locked .lock {
    background: var(--hud-green-faint);
    outline: none;
  }
  li.locked .idx::before {
    content: '▶';
    position: absolute;
    margin-left: -1.1ch;
    color: var(--hud-amber);
  }

  .idx { color: var(--hud-green-dim); }
  .surge { color: var(--hud-green-dim); font-size: 0.7rem; text-align: right; }
  .surge.hot { color: var(--hud-red); text-shadow: 0 0 6px currentColor; }
  .cc { color: var(--hud-amber); }

  .name {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    text-transform: uppercase;
  }

  .name small {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: 0.66rem;
    text-transform: none;
    color: var(--hud-green-dim);
  }

  .gauge {
    height: 8px;
    border: 1px solid var(--c);
    background: repeating-linear-gradient(90deg, transparent 0 4px, rgba(0, 0, 0, 0.6) 4px 5px);
  }
  .gauge span {
    display: block;
    height: 100%;
    background: var(--c);
    box-shadow: 0 0 6px var(--c);
    mix-blend-mode: screen;
  }

  .score {
    color: var(--c);
    text-shadow: 0 0 6px currentColor;
    font-variant-numeric: tabular-nums;
    text-align: right;
  }

  a {
    font-size: 0.65rem;
    padding: 2px 5px;
    border: 1px solid var(--hud-green-dim);
    color: var(--hud-green);
    text-decoration: none;
  }
  a:hover,
  a:focus-visible {
    background: var(--hud-green);
    color: #000;
    outline: none;
  }

  .empty {
    margin: 0;
    padding: 18px 0;
    text-align: center;
    color: var(--hud-green-dim);
  }
</style>
