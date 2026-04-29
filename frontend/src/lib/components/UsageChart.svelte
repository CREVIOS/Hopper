<script lang="ts">
  import { onMount } from 'svelte';
  import type { Chart as ChartType, ChartData, ChartOptions } from 'chart.js';
  import type { UsagePoint } from '$lib/types';

  let {
    points,
    metric = 'cpu',
    height = 240
  }: {
    points: UsagePoint[];
    metric?: 'cpu' | 'memory';
    height?: number;
  } = $props();

  let canvas: HTMLCanvasElement;
  let chart: ChartType | null = null;

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
            borderColor: 'hsl(var(--primary))',
            backgroundColor: 'hsl(var(--primary) / 0.12)',
            fill: true,
            tension: 0.3,
            borderWidth: 2,
            pointRadius: 0,
            pointHoverRadius: 4
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
          borderColor: 'hsl(var(--info))',
          backgroundColor: 'hsl(var(--info) / 0.12)',
          fill: true,
          tension: 0.3,
          borderWidth: 2,
          pointRadius: 0,
          pointHoverRadius: 4
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
          ticks: {
            color: 'hsl(var(--muted-foreground))',
            maxRotation: 0,
            autoSkipPadding: 24
          },
          grid: { color: 'hsl(var(--border) / 0.5)' }
        },
        y: {
          beginAtZero: true,
          suggestedMax: metric === 'cpu' ? 100 : undefined,
          ticks: {
            color: 'hsl(var(--muted-foreground))',
            callback: (v) => (metric === 'cpu' ? `${v}%` : `${(+v).toFixed(1)} GB`)
          },
          grid: { color: 'hsl(var(--border) / 0.5)' }
        }
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'hsl(var(--popover))',
          borderColor: 'hsl(var(--border))',
          borderWidth: 1,
          titleColor: 'hsl(var(--popover-foreground))',
          bodyColor: 'hsl(var(--popover-foreground))',
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
  onMount(() => {
    let cancelled = false;
    let local: ChartType | null = null;
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
      local?.destroy();
      chart = null;
    };
  });

  $effect(() => {
    if (!chart) return;
    chart.data = buildData();
    chart.options = buildOptions();
    chart.update('none');
  });
</script>

<div style="height: {height}px;" class="w-full">
  <canvas bind:this={canvas}></canvas>
</div>
