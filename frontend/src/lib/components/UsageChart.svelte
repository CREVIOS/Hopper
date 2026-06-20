<script lang="ts">
  import { onMount } from 'svelte';
  import type { Chart as ChartType, ChartData, ChartOptions } from 'chart.js';
  import type { UsagePoint } from '$lib/types';
  import { chartColor } from '$lib/utils';

  let {
    points,
    metric = 'cpu',
    height = 220
  }: {
    points: UsagePoint[];
    metric?: 'cpu' | 'memory';
    height?: number;
  } = $props();

  let canvas: HTMLCanvasElement;
  let chart: ChartType | null = null;

  // Soft vertical gradient fill beneath the line — falls back to a flat
  // tint if the canvas context/area isn't ready yet.
  function areaFill(token: string) {
    return (ctx: { chart: ChartType }) => {
      const { ctx: c, chartArea } = ctx.chart;
      if (!chartArea) return chartColor(token, 0.12);
      const g = c.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
      g.addColorStop(0, chartColor(token, 0.28));
      g.addColorStop(1, chartColor(token, 0));
      return g;
    };
  }

  function buildData(): ChartData<'line'> {
    if (metric === 'cpu') {
      return {
        datasets: [
          {
            label: 'CPU %',
            data: points.map((p) => ({
              x: new Date(p.time).getTime(),
              y: p.cpu_percent
            })),
            borderColor: chartColor('primary'),
            backgroundColor: areaFill('primary'),
            fill: true,
            tension: 0.35,
            borderWidth: 2,
            pointRadius: 0,
            pointHoverRadius: 4,
            pointHoverBackgroundColor: chartColor('primary'),
            pointHoverBorderColor: chartColor('background')
          }
        ]
      };
    }
    return {
      datasets: [
        {
          label: 'Memory used (GB)',
          data: points.map((p) => ({
            x: new Date(p.time).getTime(),
            y: p.memory_used_bytes / 1024 ** 3
          })),
          borderColor: chartColor('info'),
          backgroundColor: areaFill('info'),
          fill: true,
          tension: 0.35,
          borderWidth: 2,
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHoverBackgroundColor: chartColor('info'),
          pointHoverBorderColor: chartColor('background')
        }
      ]
    };
  }

  function buildOptions(): ChartOptions<'line'> {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 500 },
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: {
          type: 'time',
          time: { tooltipFormat: 'MMM d, HH:mm' },
          border: { display: false },
          ticks: {
            color: chartColor('muted-foreground'),
            maxRotation: 0,
            autoSkipPadding: 24
          },
          grid: { display: false }
        },
        y: {
          beginAtZero: true,
          suggestedMax: metric === 'cpu' ? 100 : undefined,
          border: { display: false },
          ticks: {
            color: chartColor('muted-foreground'),
            maxTicksLimit: 5,
            callback: (v) => (metric === 'cpu' ? `${v}%` : `${(+v).toFixed(1)} GB`)
          },
          grid: { color: chartColor('border', 0.5) }
        }
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: chartColor('popover'),
          borderColor: chartColor('border'),
          borderWidth: 1,
          padding: 10,
          cornerRadius: 8,
          titleColor: chartColor('popover-foreground'),
          bodyColor: chartColor('popover-foreground'),
          callbacks: {
            label: (ctx) =>
              metric === 'cpu'
                ? `CPU: ${(+(ctx.parsed.y ?? 0)).toFixed(1)}%`
                : `Memory: ${(+(ctx.parsed.y ?? 0)).toFixed(2)} GB`
          }
        }
      }
    };
  }

  // Sync mount: spawn an async loader but register cleanup synchronously so
  // svelte-check is happy.
  function applyConfig() {
    if (!chart) return;
    chart.data = buildData();
    chart.options = buildOptions();
    chart.update('none');
  }

  onMount(() => {
    let cancelled = false;
    let local: ChartType | null = null;
    // Rebuild on light/dark toggle so resolved canvas colors stay in sync.
    const observer = new MutationObserver(() => applyConfig());
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class']
    });
    (async () => {
      const { Chart, registerables } = await import('chart.js');
      // chartjs-adapter-date-fns ships no .d.ts; safe to import for side-effects.
      // @ts-expect-error -- ambient module
      await import('chartjs-adapter-date-fns');
      Chart.register(...registerables);
      if (cancelled || !canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      local = new Chart(ctx, {
        type: 'line',
        data: buildData(),
        options: buildOptions()
      });
      chart = local;
    })();
    return () => {
      cancelled = true;
      observer.disconnect();
      local?.destroy();
      chart = null;
    };
  });

  $effect(() => {
    points;
    metric;
    applyConfig();
  });
</script>

<div style="height: {height}px;" class="w-full">
  <canvas bind:this={canvas}></canvas>
</div>
