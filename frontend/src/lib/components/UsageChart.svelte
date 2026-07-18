<script lang="ts">
  import { onMount } from 'svelte';
  import type { Chart as ChartType, ChartData, ChartOptions, Plugin } from 'chart.js';
  import type { UsagePoint } from '$lib/types';
  import { chartColor } from '$lib/utils';

  let {
    points,
    metric = 'cpu',
    height = 320
  }: {
    points: UsagePoint[];
    metric?: 'cpu' | 'memory';
    height?: number;
  } = $props();

  let canvas: HTMLCanvasElement;
  let chart: ChartType | null = null;

  // Active accent token follows the selected metric (read at draw time so
  // theme + metric switches stay in sync without rebuilding plugins).
  const tone = () => (metric === 'cpu' ? 'primary' : 'info');
  const altTone = () => (metric === 'cpu' ? 'info' : 'primary');

  // Soft vertical gradient fill beneath the line.
  function areaFill() {
    return (ctx: { chart: ChartType }) => {
      const { ctx: c, chartArea } = ctx.chart;
      if (!chartArea) return chartColor(tone(), 0.14);
      const g = c.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
      g.addColorStop(0, chartColor(tone(), 0.22));
      g.addColorStop(0.6, chartColor(tone(), 0.06));
      g.addColorStop(1, chartColor(tone(), 0));
      return g;
    };
  }

  // Horizontal two-accent gradient stroke — a subtle hue drift across time.
  function lineGradient() {
    return (ctx: { chart: ChartType }) => {
      const { ctx: c, chartArea } = ctx.chart;
      if (!chartArea) return chartColor(tone(), 0.7);
      const g = c.createLinearGradient(chartArea.left, 0, chartArea.right, 0);
      g.addColorStop(0, chartColor(tone(), 0.7));
      g.addColorStop(1, chartColor(altTone(), 0.7));
      return g;
    };
  }

  // Soft glow under the line.
  const glow: Plugin<'line'> = {
    id: 'glow',
    beforeDatasetsDraw(c) {
      c.ctx.save();
      c.ctx.shadowColor = chartColor(tone(), 0.18);
      c.ctx.shadowBlur = 12;
      c.ctx.shadowOffsetY = 5;
    },
    afterDatasetsDraw(c) {
      c.ctx.restore();
    }
  };

  // Glowing endpoint marker at the latest sample.
  const endpoint: Plugin<'line'> = {
    id: 'endpoint',
    afterDatasetsDraw(c) {
      const pts = c.getDatasetMeta(0).data;
      if (!pts.length) return;
      const p = pts[pts.length - 1];
      const ctx = c.ctx;
      ctx.save();
      ctx.beginPath();
      ctx.arc(p.x, p.y, 8, 0, Math.PI * 2);
      ctx.fillStyle = chartColor(tone(), 0.16);
      ctx.fill();
      ctx.beginPath();
      ctx.arc(p.x, p.y, 3.5, 0, Math.PI * 2);
      ctx.fillStyle = chartColor(tone());
      ctx.fill();
      ctx.lineWidth = 2;
      ctx.strokeStyle = chartColor('background');
      ctx.stroke();
      ctx.restore();
    }
  };

  // Vertical crosshair following the tooltip.
  const crosshair: Plugin<'line'> = {
    id: 'crosshair',
    afterDatasetsDraw(c) {
      const active = c.tooltip?.getActiveElements?.() ?? [];
      if (!active.length) return;
      const x = active[0].element.x;
      const { top, bottom } = c.chartArea;
      const ctx = c.ctx;
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(x, top);
      ctx.lineTo(x, bottom);
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.strokeStyle = chartColor(tone(), 0.4);
      ctx.stroke();
      ctx.restore();
    }
  };

  function buildData(): ChartData<'line'> {
    const isCpu = metric === 'cpu';
    return {
      datasets: [
        {
          label: isCpu ? 'CPU %' : 'Memory used (GB)',
          data: points.map((p) => ({
            x: new Date(p.time).getTime(),
            y: isCpu ? p.cpu_percent : p.memory_used_bytes / 1024 ** 3
          })),
          borderColor: lineGradient(),
          backgroundColor: areaFill(),
          fill: true,
          tension: 0.4,
          cubicInterpolationMode: 'monotone',
          borderWidth: 2.5,
          borderJoinStyle: 'round',
          borderCapStyle: 'round',
          pointRadius: 0,
          pointHoverRadius: 5,
          pointHoverBackgroundColor: chartColor(tone()),
          pointHoverBorderColor: chartColor('background'),
          pointHoverBorderWidth: 2
        }
      ]
    };
  }

  function buildOptions(): ChartOptions<'line'> {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 650, easing: 'easeOutQuart' },
      layout: { padding: { top: 10, right: 12, bottom: 0, left: 2 } },
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: {
          type: 'time',
          time: { tooltipFormat: 'MMM d, HH:mm' },
          border: { display: false },
          grid: { display: false },
          ticks: {
            color: chartColor('muted-foreground'),
            maxRotation: 0,
            autoSkipPadding: 28,
            font: { size: 11 }
          }
        },
        y: {
          beginAtZero: true,
          suggestedMax: metric === 'cpu' ? 100 : undefined,
          border: { display: false },
          grid: { color: chartColor('border', 0.4), tickLength: 0 },
          ticks: {
            color: chartColor('muted-foreground'),
            maxTicksLimit: 4,
            padding: 10,
            font: { size: 11 },
            callback: (v) => (metric === 'cpu' ? `${v}%` : `${(+v).toFixed(1)}G`)
          }
        }
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: chartColor('popover'),
          borderColor: chartColor('border'),
          borderWidth: 1,
          padding: 12,
          cornerRadius: 10,
          displayColors: false,
          titleColor: chartColor('muted-foreground'),
          titleFont: { size: 11, weight: 'normal' },
          bodyColor: chartColor('popover-foreground'),
          bodyFont: { size: 13, weight: 'bold' },
          callbacks: {
            label: (ctx) =>
              metric === 'cpu'
                ? `${(+(ctx.parsed.y ?? 0)).toFixed(1)}%`
                : `${(+(ctx.parsed.y ?? 0)).toFixed(2)} GB`
          }
        }
      }
    };
  }

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
        options: buildOptions(),
        plugins: [glow, endpoint, crosshair]
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
