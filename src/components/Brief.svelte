<script>
  import { buildBrief } from '../brief.js';

  export let event;

  $: brief = buildBrief(event);
  $: links = (event.links || []).filter((item) => /^https?:\/\//.test(item.url || ''));
</script>

<div class="brief">
  <div class="lead">
    <strong>{brief.headline}</strong>
    {#if brief.headlineIsGuess}
      <em>most-covered article · headline read from the link</em>
    {:else if event.headline}
      <em>most-covered article</em>
    {/if}
    {#if brief.summary}<p>{brief.summary}</p>{/if}
    {#if links.length}
      <ul class="links">
        {#each links as item}
          <li><a href={item.url} target="_blank" rel="noopener noreferrer">▸ {item.domain || 'source'}</a></li>
        {/each}
      </ul>
    {/if}
  </div>
  <dl>
    <div>
      <dt>SCORE</dt>
      <dd>{event.risk_score ?? '---'} · {(event.tag || 'n/a').toUpperCase()}</dd>
    </div>
    {#each brief.facts as [label, value]}
      <div>
        <dt>{label}</dt>
        <dd>{value}</dd>
      </div>
    {/each}
  </dl>
</div>

<style>
  /* Two columns when the panel is wide: story on the left, facts on the right. */
  .brief {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr));
    gap: 10px 28px;
    font-size: 0.76rem;
    line-height: 1.45;
    color: var(--hud-text);
  }
  .lead {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
  }
  strong {
    font-weight: normal;
    font-size: 0.92rem;
    color: var(--hud-green);
    text-shadow: 0 0 6px rgba(61, 255, 154, 0.5);
  }
  em {
    font-style: normal;
    font-size: 0.62rem;
    color: var(--hud-green-dim);
    text-transform: uppercase;
  }
  p {
    margin: 0;
    padding-left: 8px;
    border-left: 2px solid var(--hud-amber);
    letter-spacing: 0.01em;
  }
  .links {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 16px;
    margin: 2px 0 0;
    padding: 0;
    list-style: none;
  }
  .links a {
    color: var(--hud-amber);
    text-decoration: none;
  }
  .links a:hover,
  .links a:focus-visible {
    text-decoration: underline;
    outline: none;
  }
  dl {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
    gap: 3px 20px;
    margin: 0;
    align-content: start;
  }
  dl div {
    display: grid;
    grid-template-columns: 13ch 1fr;
    gap: 8px;
  }
  dt {
    color: var(--hud-green-dim);
  }
  dd {
    margin: 0;
    overflow-wrap: anywhere;
  }
</style>
