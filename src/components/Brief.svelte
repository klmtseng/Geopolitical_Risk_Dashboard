<script>
  import { buildBrief } from '../brief.js';

  export let event;
  export let risk = true; // show the risk line (off where the score is already visible)
  export let compact = false; // only the key facts, for the map popup

  const KEY_FACTS = ['ACTIVITY', 'LOCATION', 'COVERAGE', 'SURGE'];

  $: brief = buildBrief(event);
</script>

<div class="brief">
  <strong>{brief.headline}</strong>
  {#if brief.headlineIsGuess}
    <em>most-covered article · headline read from the link</em>
  {:else if event.headline}
    <em>most-covered article</em>
  {/if}
  {#if brief.summary && !compact}<p>{brief.summary}</p>{/if}
  <dl>
    {#if risk}
      <dt>SCORE</dt>
      <dd>{event.risk_score ?? '---'} · {(event.tag || 'n/a').toUpperCase()}</dd>
    {/if}
    {#each compact ? brief.facts.filter(([label]) => KEY_FACTS.includes(label)) : brief.facts as [label, value]}
      <dt>{label}</dt>
      <dd>{value}</dd>
    {/each}
  </dl>
</div>

<style>
  .brief {
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 0.74rem;
    line-height: 1.45;
    color: var(--hud-text);
  }
  strong {
    font-weight: normal;
    font-size: 0.86rem;
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
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 2px 10px;
    margin: 0;
  }
  dt {
    color: var(--hud-green-dim);
  }
  dd {
    margin: 0;
    overflow-wrap: anywhere;
  }
</style>
