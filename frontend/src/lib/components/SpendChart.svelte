<script lang="ts">
  import { onMount } from 'svelte';
  import type { Chart as ChartType, ChartConfiguration } from 'chart.js';
  import type { CreditTransaction } from '$lib/types';
  import { chartColor } from '$lib/utils';

  let {
    transactions,
    days = 14
  }: { transactions: CreditTransaction[]; days?: number } = $props();

  let canvas: HTMLCanvasElement;
  let chart: ChartType | null = null;

  function buildBuckets() {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const buckets: { label: string; date: Date; debit: number; credit: number }[] = [];
    for (let i = days - 1; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(today.getDate() - i);
      buckets.push({
        label: d.toLocaleDateString(undefined, {
          month: 'short',
          day: 'numeric'
        }),
        date: d,
        debit: 0,
        credit: 0
      });
    }
    const map = new Map<string, (typeof buckets)[number]>();
    for (const b of buckets) map.set(b.date.toDateString(), b);

    for (const tx of transactions) {
      const d = new Date(tx.created_at);
      d.setHours(0, 0, 0, 0);
      const b = map.get(d.toDateString());
      if (!b) continue;
      if (tx.direction === 'debit') b.debit += tx.amount;
      else b.credit += tx.amount;
    }
    return buckets;
  }

  // Soft vertical gradient on each bar — stronger at the top, fading down.
  function barGradient(token: string) {
    return (ctx: { chart: ChartType }) => {
      const { ctx: c, chartArea } = ctx.chart;
      if (!chartArea) return chartColor(token, 0.7);
      const g = c.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
      g.addColorStop(0, chartColor(token, 0.9));
      g.addColorStop(1, chartColor(token, 0.4));
      return g;
    };
  }

  function buildConfig(): ChartConfiguration<'bar'> {
    const buckets = buildBuckets();
    return {
      type: 'bar',
      data: {
        labels: buckets.map((b) => b.label),
        datasets: [
          {
            label: 'Spent',
            data: buckets.map((b) => b.debit),
            backgroundColor: barGradient('destructive'),
            hoverBackgroundColor: chartColor('destructive'),
            borderRadius: 6,
            borderSkipped: false,
            maxBarThickness: 18,
            stack: 's'
          },
          {
            label: 'Received',
            data: buckets.map((b) => b.credit),
            backgroundColor: barGradient('success'),
            hoverBackgroundColor: chartColor('success'),
            borderRadius: 6,
            borderSkipped: false,
            maxBarThickness: 18,
            stack: 's'
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { top: 8 } },
        animation: { duration: 600 },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: chartColor('popover'),
            borderColor: chartColor('border'),
            borderWidth: 1,
            padding: 10,
            cornerRadius: 8,
            usePointStyle: true,
            titleColor: chartColor('popover-foreground'),
            bodyColor: chartColor('popover-foreground'),
            callbacks: {
              label: (ctx) =>
                `${ctx.dataset.label}: ${(+(ctx.parsed.y ?? 0)).toFixed(2)} cr`
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            border: { display: false },
            ticks: {
              color: chartColor('muted-foreground'),
              font: { size: 11 },
              autoSkip: true,
              maxRotation: 0,
              padding: 4
            }
          },
          y: {
            beginAtZero: true,
            border: { display: false },
            ticks: {
              color: chartColor('muted-foreground'),
              font: { size: 11 },
              maxTicksLimit: 4,
              padding: 6,
              callback: (v) => `${(+v).toFixed(0)}`
            },
            grid: {
              color: chartColor('border', 0.4),
              lineWidth: 1
            }
          }
        }
      }
    };
  }

  function applyConfig() {
    if (!chart) return;
    const cfg = buildConfig();
    chart.data = cfg.data;
    chart.options = cfg.options ?? {};
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
      Chart.register(...registerables);
      if (cancelled || !canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      local = new Chart(ctx, buildConfig());
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
    transactions;
    days;
    applyConfig();
  });
</script>

<div class="h-44 w-full sm:h-48">
  <canvas bind:this={canvas}></canvas>
</div>
