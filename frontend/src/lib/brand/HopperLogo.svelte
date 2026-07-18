<script lang="ts">
  import { Rabbit } from 'lucide-svelte';
  import { cn } from '$lib/utils';

  let {
    size = 28,
    class: className,
    /** Accepted for API compatibility; the mark is calm by default. */
    idle = false
  }: { size?: number; class?: string; idle?: boolean } = $props();

  // Rabbit glyph scales with the tile; radius tracks size for a squircle feel.
  const glyph = $derived(Math.round(size * 0.58));
  const radius = $derived(Math.round(size * 0.3));
</script>

<span
  class={cn('hopper-mark relative inline-grid shrink-0 place-items-center', idle && 'is-idle', className)}
  style="width:{size}px;height:{size}px;border-radius:{radius}px"
  aria-hidden="true"
>
  <span class="hopper-base absolute inset-0" style="border-radius:{radius}px"></span>
  <span class="hopper-gloss pointer-events-none absolute inset-0" style="border-radius:{radius}px"></span>
  <span class="hopper-ring pointer-events-none absolute inset-0" style="border-radius:{radius}px"></span>
  <Rabbit class="hopper-glyph relative text-white" size={glyph} strokeWidth={2.25} />
</span>

<style>
  .hopper-mark {
    box-shadow:
      0 1px 2px hsl(224 50% 8% / 0.2),
      0 6px 16px -6px hsl(var(--primary) / 0.5),
      inset 0 1px 0 hsl(0 0% 100% / 0.4);
    transition:
      transform 0.25s cubic-bezier(0.16, 1, 0.3, 1),
      box-shadow 0.25s ease;
  }
  .hopper-mark:hover {
    transform: scale(1.05) translateY(-0.5px);
    box-shadow:
      0 2px 4px hsl(224 50% 8% / 0.24),
      0 12px 26px -8px hsl(var(--primary) / 0.65),
      inset 0 1px 0 hsl(0 0% 100% / 0.45);
  }
  .hopper-base {
    background: linear-gradient(
      150deg,
      hsl(var(--info)) 0%,
      hsl(var(--primary)) 52%,
      hsl(252 80% 48%) 100%
    );
  }
  .hopper-gloss {
    background:
      radial-gradient(120% 90% at 28% 10%, hsl(0 0% 100% / 0.45), transparent 55%),
      linear-gradient(180deg, hsl(0 0% 100% / 0.16) 0%, transparent 38%);
  }
  .hopper-ring {
    box-shadow:
      inset 0 0 0 1px hsl(0 0% 100% / 0.16),
      inset 0 -1px 2px hsl(252 80% 16% / 0.3);
  }
  .hopper-glyph {
    filter: drop-shadow(0 1px 1px hsl(252 70% 12% / 0.4));
  }
</style>
