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

    const option = {
      title: {
        text: 'Global Average Risk Trend (Last 14 Days)',
        left: 'center',
        textStyle: {
          fontSize: 16,
          fontWeight: 'normal'
        }
      },
      tooltip: {
        trigger: 'axis',
        formatter: function (params) {
          const param = params[0];
          return `Date: ${param.axisValueLabel}<br/>Average Risk: ${param.value}`;
        }
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%', // Adjusted if dataZoom is used
        containLabel: true
      },
      xAxis: {
        type: 'category',
        boundaryGap: false, // For line charts, often better to not have gaps
        data: data.map(item => item.date),
        axisLabel: {
          fontSize: 10
        }
      },
      yAxis: {
        type: 'value',
        name: 'Avg. Risk Score',
        nameTextStyle: {
            fontSize: 12,
            padding: [0, 0, 0, 50] // Adjust padding to prevent overlap if name is long
        },
        min: 0,
        max: 100,
        axisLabel: {
          fontSize: 10
        }
      },
      series: [
        {
          name: 'Average Risk',
          type: 'line',
          smooth: true,
          data: data.map(item => item.avgRisk),
          itemStyle: {
            color: '#2980b9' // Example line color
          },
          areaStyle: { // Optional: to fill area under line
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(41, 128, 185, 0.5)' },
              { offset: 1, color: 'rgba(41, 128, 185, 0.1)' }
            ])
          }
        }
      ],
      // Optional: DataZoom for larger datasets, not strictly needed for 14 points
      // dataZoom: [
      //   {
      //     type: 'inside',
      //     start: 0,
      //     end: 100
      //   },
      //   {
      //     start: 0,
      //     end: 100,
      //     handleSize: '80%',
      //     handleStyle: { color: '#fff', shadowBlur: 3, shadowColor: 'rgba(0,0,0,0.6)', shadowOffsetX: 2, shadowOffsetY: 2 },
      //     bottom: 10, // Position of the slider
      //     height: 20 // Height of the slider
      //   }
      // ]
    };

    chartInstance.setOption(option, true); // true to not merge with previous options
  }
</script>

<div bind:this={chartContainer} style="width: 100%; height: 300px;">
  <!-- EChart will be rendered here -->
</div>
{#if !chartInstance && typeof window !== 'undefined'}
  <p style="text-align: center;">Initializing timeseries chart...</p>
{:else if typeof window !== 'undefined' && (!dailyAverageRiskData || dailyAverageRiskData.length === 0)}
  <p style="text-align: center;">No timeseries data available.</p>
{/if}

<style>
  div[bind:this={chartContainer}] {
    width: 100%;
    height: 300px; /* Default height, can be overridden by parent or props */
  }
  p {
    font-size: 0.9em;
    color: #777;
  }
</style>
