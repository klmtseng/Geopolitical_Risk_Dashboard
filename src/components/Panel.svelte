<script>
  export let title = '';
  export let code = ''; // small identifier shown at the right of the title bar
</script>

<section class="panel">
  <header>
    <span class="title">{title}</span>
    <span class="rule" aria-hidden="true"></span>
    {#if code}<span class="code">{code}</span>{/if}
  </header>
  <div class="body">
    <slot />
  </div>
  <i class="corner tl" aria-hidden="true"></i>
  <i class="corner tr" aria-hidden="true"></i>
  <i class="corner bl" aria-hidden="true"></i>
  <i class="corner br" aria-hidden="true"></i>
</section>

<style>
  .panel {
    position: relative;
    background: var(--hud-panel);
    border: 1px solid var(--hud-green-dim);
    box-shadow: 0 0 18px rgba(61, 255, 154, 0.08), inset 0 0 30px rgba(61, 255, 154, 0.04);
    /* clipped corner, top right */
    clip-path: polygon(0 0, calc(100% - 14px) 0, 100% 14px, 100% 100%, 0 100%);
  }

  header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 22px 6px 12px;
    border-bottom: 1px solid var(--hud-green-dim);
    font-size: 0.78rem;
    text-transform: uppercase;
    color: var(--hud-green);
    text-shadow: 0 0 6px rgba(61, 255, 154, 0.6);
  }

  .title::before {
    content: '▮ ';
    color: var(--hud-amber);
  }

  .rule {
    flex: 1;
    height: 5px;
    background: repeating-linear-gradient(90deg, var(--hud-green-dim) 0 2px, transparent 2px 6px);
  }

  .code {
    color: var(--hud-amber);
    font-size: 0.7rem;
  }

  .body {
    padding: 12px;
  }

  .corner {
    position: absolute;
    width: 10px;
    height: 10px;
    border: 2px solid var(--hud-green);
    pointer-events: none;
  }
  .tl { top: -1px; left: -1px; border-right: 0; border-bottom: 0; }
  .tr { display: none; }
  .bl { bottom: -1px; left: -1px; border-right: 0; border-top: 0; }
  .br { bottom: -1px; right: -1px; border-left: 0; border-top: 0; }
</style>
