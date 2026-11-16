<script>
  import { onMount, onDestroy, afterUpdate } from 'svelte';
  import * as echarts from 'echarts/core';
  import { LineChart } from 'echarts/charts';
  import {
    TitleComponent,
    TooltipComponent,
    GridComponent,
    DataZoomComponent // Added for potential future use, good to have
  } from 'echarts/components';
  import { CanvasRenderer } from 'echarts/renderers';

  // Register the required ECharts components
  echarts.use([
    TitleComponent,
    TooltipComponent,
    GridComponent,
    DataZoomComponent,
    LineChart,
    CanvasRenderer
  ]);

  export let dailyAverageRiskData = []; // Expected: [{date: 'YYYY-MM-DD', avgRisk: X}, ...]

  let chartContainer; // Bound to the div element
  let chartInstance = null;

  const handleResize = () => {
    if (chartInstance && !chartInstance.isDisposed()) {
      chartInstance.resize();
    }
  };

  onMount(() => {
    if (typeof window !== 'undefined') {
      if (!chartContainer) {
        console.error("Timeseries chart container not found onMount.");
        return;
      }
      chartInstance = echarts.init(chartContainer, null, { renderer: 'canvas' });
      updateChart(dailyAverageRiskData);
      window.addEventListener('resize', handleResize);
    }
  });

  afterUpdate(() => {
    // Called after props update. Update chart if instance exists and data changed.
    if (chartInstance && !chartInstance.isDisposed()) {
      updateChart(dailyAverageRiskData);
    }
  });

  onDestroy(() => {
    if (chartInstance && !chartInstance.isDisposed()) {
      chartInstance.dispose();
      chartInstance = null;
    }
    if (typeof window !== 'undefined') {
      window.removeEventListener('resize', handleResize);
    }
  });

  function updateChart(data) {
    if (!chartInstance || chartInstance.isDisposed() || !data) {
      return;
    }

    const GREEN = '#3dff9a';
    const DIM = '#1f7a53';
    const FONT = "'Share Tech Mono', Consolas, Menlo, monospace";
    const peak = Math.max(0, ...data.map(item => item.avgRisk ?? 0));

    const option = {
      backgroundColor: 'transparent',
      textStyle: { fontFamily: FONT, color: GREEN },
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(4, 9, 7, 0.95)',
        borderColor: GREEN,
        textStyle: { color: GREEN, fontFamily: FONT, fontSize: 11 },
        axisPointer: { lineStyle: { color: '#ffb000', type: 'dashed' } },
        formatter: function (params) {
          const param = params[0];
          return `${param.axisValueLabel}<br/>MEAN RISK ${param.value ?? '---'}`;
        }
      },
      grid: { left: 4, right: 12, top: 14, bottom: 4, containLabel: true },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: data.map(item => item.date.slice(5)),
        axisLine: { lineStyle: { color: DIM } },
        axisTick: { lineStyle: { color: DIM } },
        axisLabel: { fontSize: 10, color: DIM }
      },
      yAxis: {
        type: 'value',
        min: 0,
        // Scores run 0-100 but daily means sit low; keep the trace readable.
        max: Math.max(20, Math.ceil(peak / 10) * 10 + 10),
        splitLine: { lineStyle: { color: 'rgba(61, 255, 154, 0.14)', type: 'dashed' } },
        axisLabel: { fontSize: 10, color: DIM }
      },
      series: [
        {
          name: 'Average Risk',
          type: 'line',
          step: 'middle',
          connectNulls: true,
          symbol: 'rect',
          symbolSize: 5,
          data: data.map(item => item.avgRisk),
          lineStyle: { color: GREEN, width: 1.5, shadowColor: GREEN, shadowBlur: 8 },
          itemStyle: { color: GREEN },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(61, 255, 154, 0.35)' },
              { offset: 1, color: 'rgba(61, 255, 154, 0)' }
            ])
          }
        }
      ]
    };

    chartInstance.setOption(option, true); // true to not merge with previous options
  }
</script>

<div bind:this={chartContainer} class="chart"></div>
{#if !dailyAverageRiskData || dailyAverageRiskData.length === 0}
  <p>NO TREND DATA</p>
{/if}

<style>
  .chart {
    width: 100%;
    height: 190px;
  }
  p {
    margin: 0;
    text-align: center;
    font-size: 0.75rem;
    color: var(--hud-green-dim);
  }
</style>
