<script>
  import { createEventDispatcher } from 'svelte';

  export let events = []; // top events, already sorted by risk_score
  export let selected = null;

  const dispatch = createEventDispatcher();
  const pad = (n, width) => String(n).padStart(width, '0');
  const level = (risk) => (risk > 70 ? 'high' : risk > 40 ? 'medium' : 'low');
  // "GDELT Event: 192 in TU" -> "EVT 192 / TU": keeps the part that differs visible in a narrow column
  const shortName = (title) =>
    (title || 'UNIDENTIFIED').replace(/^GDELT Event:\s*/i, 'EVT ').replace(/\s+in\s+/i, ' / ');
  const isLink = (url) => /^https?:\/\//.test(url || '');
</script>

{#if events && events.length > 0}
  <ol class="targets">
    {#each events as event, i}
      <li class={level(event.risk_score)} class:locked={selected === event}>
        <button
          type="button"
          class="lock"
          disabled={event.lat == null || event.lon == null}
          title="Lock the radar onto this target"
          on:click={() => dispatch('select', event)}
        >
          <span class="idx">{pad(i + 1, 2)}</span>
          <span class="name" title={event.title}>{shortName(event.title)}</span>
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
    grid-template-columns: 2ch minmax(0, 1fr) 56px 3ch;
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

  .empty {
    margin: 0;
    padding: 18px 0;
    text-align: center;
    color: var(--hud-green-dim);
  }
</style>
