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
            backgroundColor: chartColor('destructive', 0.75),
            hoverBackgroundColor: chartColor('destructive'),
            borderRadius: 6,
            maxBarThickness: 28,
            stack: 's'
          },
          {
            label: 'Received',
            data: buckets.map((b) => b.credit),
            backgroundColor: chartColor('success', 0.75),
            hoverBackgroundColor: chartColor('success'),
            borderRadius: 6,
            maxBarThickness: 28,
            stack: 's'
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              color: chartColor('muted-foreground'),
              boxWidth: 10,
              boxHeight: 10,
              usePointStyle: true,
              pointStyle: 'circle',
              padding: 16
            }
          },
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
              autoSkip: true,
              maxRotation: 0
            }
          },
          y: {
            beginAtZero: true,
            border: { display: false },
            ticks: {
              color: chartColor('muted-foreground'),
              callback: (v) => `${(+v).toFixed(0)}`
            },
            grid: { color: chartColor('border', 0.5) }
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
