<script>
  import { onMount } from 'svelte';

  export let dataUrl; // (name) => URL of a file in the data folder

  const MODE_KEY = 'grd.ticker.mode';
  let mode = 'news'; // 'news' | 'markets'
  let news = null; // { updated, items } once loaded
  let markets = null;
  let loaded = false;

  async function load(name) {
    try {
      const response = await fetch(dataUrl(name));
      if (!response.ok) return null;
      const payload = await response.json();
      return Array.isArray(payload?.items) && payload.items.length > 0 ? payload : null;
    } catch {
      return null;
    }
  }

  onMount(async () => {
    try {
      const saved = localStorage.getItem(MODE_KEY);
      if (saved === 'news' || saved === 'markets') mode = saved;
    } catch {
      // storage unavailable: keep the default
    }
    [news, markets] = await Promise.all([load('news.json'), load('markets.json')]);
    // start on whichever feed actually has data
    if (mode === 'news' && !news && markets) mode = 'markets';
    if (mode === 'markets' && !markets && news) mode = 'news';
    loaded = true;
  });

  function setMode(next) {
    mode = next;
    try {
      localStorage.setItem(MODE_KEY, next);
    } catch {
      // ignore
    }
  }

  const pad = (n) => String(n).padStart(2, '0');
  function clock(iso) {
    const d = new Date(iso);
    return isNaN(d) ? '' : `${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}Z`;
  }
  const signed = (value) => (value == null ? '---' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`);
  const direction = (value) => (value == null || value === 0 ? 'flat' : value > 0 ? 'up' : 'down');
  const arrow = { up: '▲', down: '▼', flat: '■' };
  const price = (value) => value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const newsTip = (item) =>
    [item.summary, [item.source, clock(item.published)].filter(Boolean).join(' · ')].filter(Boolean).join('\n');
  const marketTip = (item) =>
    `${item.name} (${item.symbol})\nLast ${price(item.price)}${item.currency ? ' ' + item.currency : ''}, session of ${item.as_of}\n` +
    `1D ${signed(item.change_1d)}   1W ${signed(item.change_1w)}   1M ${signed(item.change_1m)}`;

  $: active = mode === 'news' ? news : markets;
  // constant reading speed whatever the amount of text
  $: seconds = active
    ? Math.max(30, active.items.reduce((n, item) => n + (item.title || item.name).length + 14, 0) / 7)
    : 0;
</script>

<section class="ticker" aria-label="Ticker">
  <div class="modes" role="group" aria-label="Ticker content">
    <button type="button" class:on={mode === 'news'} aria-pressed={mode === 'news'} on:click={() => setMode('news')}>
      NEWS
    </button>
    <button
      type="button"
      class:on={mode === 'markets'}
      aria-pressed={mode === 'markets'}
      on:click={() => setMode('markets')}
    >
      MARKETS
    </button>
  </div>

  <div class="window">
    {#if active}
      {#key mode}
        <div class="track" style="animation-duration: {seconds}s">
          <!-- the list is rendered twice so the loop is seamless; the copy is hidden from assistive tech -->
          {#each [0, 1] as copy}
            <ul aria-hidden={copy === 1}>
              {#if mode === 'news'}
                {#each active.items as item}
                  <li>
                    <span class="src">{item.source}</span>
                    <a href={item.link} target="_blank" rel="noopener noreferrer" title={newsTip(item)} tabindex={copy === 1 ? -1 : 0}>
                      {item.title}
                    </a>
                  </li>
                {/each}
              {:else}
                {#each active.items as item}
                  <li class={direction(item.change_1d)} title={marketTip(item)}>
                    <span class="src">{item.name}</span>
                    <span class="px">{price(item.price)}</span>
                    <span class="chg">{arrow[direction(item.change_1d)]} {signed(item.change_1d)}</span>
                  </li>
                {/each}
              {/if}
            </ul>
          {/each}
        </div>
      {/key}
    {:else}
      <p class="idle">
        {#if !loaded}
          ACQUIRING FEED…
        {:else}
          NO {mode === 'news' ? 'NEWS' : 'MARKET'} FEED — WAITING FOR NEXT DATA RUN
        {/if}
      </p>
    {/if}
  </div>

  {#if active}
    <span
      class="stamp"
      title={mode === 'markets'
        ? 'Last price of each market\'s most recent session when the feed was fetched; hover an index for its date'
        : 'When the headlines were fetched'}
    >
      FETCHED {clock(active.updated)}
    </span>
  {/if}
</section>

<style>
  .ticker {
    display: flex;
    align-items: stretch;
    gap: 10px;
    margin-top: 12px;
    border: 1px solid var(--hud-green-dim);
    background: var(--hud-panel);
    font-size: 0.8rem;
  }

  .modes {
    display: flex;
    flex: none;
  }

  button {
    padding: 7px 10px;
    background: none;
    border: 0;
    border-right: 1px solid var(--hud-green-dim);
    color: var(--hud-green-dim);
    font: inherit;
    letter-spacing: inherit;
    cursor: pointer;
  }
  button:hover,
  button:focus-visible {
    color: var(--hud-green);
    outline: none;
    background: var(--hud-green-faint);
  }
  button.on {
    background: var(--hud-amber);
    color: #000;
  }

  .window {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    display: flex;
    align-items: center;
    /* fade both edges */
    mask-image: linear-gradient(90deg, transparent, #000 4%, #000 96%, transparent);
    -webkit-mask-image: linear-gradient(90deg, transparent, #000 4%, #000 96%, transparent);
  }

  .track {
    display: flex;
    width: max-content;
    animation: ticker-scroll linear infinite;
  }
  .window:hover .track,
  .window:focus-within .track {
    animation-play-state: paused;
  }

  @keyframes ticker-scroll {
    to { transform: translateX(-50%); }
  }

  ul {
    display: flex;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li {
    display: flex;
    align-items: baseline;
    gap: 8px;
    padding: 0 22px;
    white-space: nowrap;
    border-right: 1px dashed var(--hud-green-dim);
  }

  .src {
    font-size: 0.68rem;
    text-transform: uppercase;
    color: var(--hud-amber);
  }

  a {
    color: var(--hud-text);
    text-decoration: none;
  }
  a:hover,
  a:focus-visible {
    color: var(--hud-green);
    text-decoration: underline;
    outline: none;
  }

  .px {
    color: var(--hud-text);
    font-variant-numeric: tabular-nums;
  }
  .chg {
    font-variant-numeric: tabular-nums;
    text-shadow: 0 0 6px currentColor;
  }
  li.up .chg { color: var(--hud-green); }
  li.down .chg { color: var(--hud-red); }
  li.flat .chg { color: var(--hud-green-dim); }

  .idle {
    margin: 0;
    padding: 0 16px;
    color: var(--hud-green-dim);
  }

  .stamp {
    flex: none;
    align-self: center;
    padding-right: 10px;
    font-size: 0.65rem;
    color: var(--hud-green-dim);
    white-space: nowrap;
  }

  @media (max-width: 600px) {
    .stamp { display: none; }
  }

  /* Without motion the list becomes a row the reader scrolls by hand. */
  @media (prefers-reduced-motion: reduce) {
    .window { overflow-x: auto; }
    .track ul[aria-hidden='true'] { display: none; }
  }
</style>
