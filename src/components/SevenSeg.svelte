<script>
  // Seven-segment readout drawn in SVG, so it needs no font file.
  export let value = '';
  export let color = 'var(--hud-green)';
  export let height = 44;

  //            a      b      c      d      e      f      g
  const SEGMENTS = {
    '0': 'abcdef', '1': 'bc', '2': 'abdeg', '3': 'abcdg', '4': 'bcfg',
    '5': 'acdfg', '6': 'acdefg', '7': 'abc', '8': 'abcdefg', '9': 'abcdfg',
    '-': 'g', ' ': ''
  };

  const SHAPES = {
    a: '3,1 17,1 15,3.5 5,3.5',
    b: '18,2 19,3 19,16.5 17.5,18 16,16.5 16,4.5',
    c: '17.5,19 19,20.5 19,34 18,35 16,32.5 16,20.5',
    d: '3,36 17,36 15,33.5 5,33.5',
    e: '2.5,19 4,20.5 4,32.5 2,35 1,34 1,20.5',
    f: '2,2 4,4.5 4,16.5 2.5,18 1,16.5 1,3',
    g: '3.5,18.5 5,17.2 15,17.2 16.5,18.5 15,19.8 5,19.8'
  };
  const NAMES = Object.keys(SHAPES);

  $: chars = String(value).split('');
</script>

<span class="readout" style="--seg-color: {color}; height: {height}px" role="img" aria-label={String(value)}>
  {#each chars as ch}
    {#if ch === '.'}
      <svg viewBox="0 0 6 37" class="dot"><rect x="1" y="32.5" width="4" height="4" /></svg>
    {:else}
      <svg viewBox="0 0 20 37">
        {#each NAMES as name}
          <polygon points={SHAPES[name]} class:on={(SEGMENTS[ch] ?? '').includes(name)} />
        {/each}
      </svg>
    {/if}
  {/each}
</span>

<style>
  .readout {
    display: inline-flex;
    gap: 5px;
    align-items: stretch;
    filter: drop-shadow(0 0 5px var(--seg-color));
  }
  svg {
    height: 100%;
    width: auto;
    overflow: visible;
  }
  polygon {
    fill: var(--seg-color);
    opacity: 0.09;
  }
  polygon.on,
  .dot rect {
    fill: var(--seg-color);
    opacity: 1;
  }
</style>
