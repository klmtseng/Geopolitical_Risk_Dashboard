<script>
  import { createEventDispatcher } from 'svelte';
  import Brief from './Brief.svelte';
  import { actionLabel } from '../brief.js';

  export let events = []; // top events, already sorted by risk_score
  export let selected = null;

  const dispatch = createEventDispatcher();
  const pad = (n, width) => String(n).padStart(width, '0');
  const level = (risk) => (risk > 70 ? 'high' : risk > 40 ? 'medium' : 'low');
  // "GDELT Event: 192 in TU" -> "EVT 192 / TU": keeps the part that differs visible in a narrow column
  const shortName = (title) =>
    (title || 'UNIDENTIFIED').replace(/^GDELT Event:\s*/i, 'EVT ').replace(/\s+in\s+/i, ' / ');
  // What happened; the country code sits in its own column so it is never cut off.
  const rowName = (event) => actionLabel(event) || shortName(event.title);

  // The panel clips its contents, so the card is moved to <body> to float above it.
  function portal(node) {
    document.body.appendChild(node);
    return { destroy: () => node.remove() };
  }

  // Hover brief: one floating card, placed beside the hovered row.
  let hovered = null;
  let cardStyle = '';

  function showBrief(event, node) {
    const rect = node.getBoundingClientRect();
    const width = Math.min(340, window.innerWidth - 24);
    // beside the list when there is room on the left, otherwise under the row
    const beside = rect.left - width - 14 >= 8;
    const left = beside ? rect.left - width - 14 : Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
    const top = beside ? Math.max(8, Math.min(rect.top - 8, window.innerHeight - 260)) : rect.bottom + 6;
    cardStyle = `left:${left}px; top:${top}px; width:${width}px`;
    hovered = event;
  }

  const hideBrief = () => (hovered = null);

  const isLink = (url) => /^https?:\/\//.test(url || '');
</script>

{#if events && events.length > 0}
  <ol class="targets">
    {#each events as event, i}
      <li
        class={level(event.risk_score)}
        class:locked={selected === event}
        on:mouseenter={(e) => showBrief(event, e.currentTarget)}
        on:mouseleave={hideBrief}
        on:focusin={(e) => showBrief(event, e.currentTarget)}
        on:focusout={hideBrief}
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
          <span class="name">{rowName(event)}</span>
          <span class="gauge" aria-hidden="true">
            <span style="width: {Math.max(0, Math.min(100, event.risk_score || 0))}%"></span>
          </span>
          <span class="score">{event.risk_score != null ? pad(event.risk_score, 3) : '---'}</span>
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

{#if hovered}
  <div class="card" style={cardStyle} role="tooltip" use:portal>
    <span class="tag">▮ TARGET BRIEF</span>
    <Brief event={hovered} />
  </div>
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
    grid-template-columns: 2ch 2ch minmax(0, 1fr) 48px 3ch;
    align-items: center;
    gap: 8px;
    padding: 7px 4px;
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
  .cc { color: var(--hud-amber); }

  .name {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    text-transform: uppercase;
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

  .card {
    position: fixed;
    z-index: 2000;
    box-sizing: border-box;
    padding: 10px 12px 12px;
    background: rgba(4, 9, 7, 0.97);
    border: 1px solid var(--hud-green);
    box-shadow: 0 0 18px rgba(61, 255, 154, 0.3);
    pointer-events: none;
    font-family: var(--hud-font);
    clip-path: polygon(0 0, calc(100% - 12px) 0, 100% 12px, 100% 100%, 0 100%);
  }

  .tag {
    display: block;
    margin-bottom: 6px;
    font-size: 0.62rem;
    color: var(--hud-amber);
  }

  .empty {
    margin: 0;
    padding: 18px 0;
    text-align: center;
    color: var(--hud-green-dim);
  }
</style>
