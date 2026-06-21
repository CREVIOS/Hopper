<script lang="ts">
  import { cn } from '$lib/utils';

  let {
    name,
    class: className
  }: { name: string | null | undefined; class?: string } = $props();

  function initials(n: string | null | undefined): string {
    if (!n) return '?';
    const parts = n.trim().split(/\s+/).filter(Boolean);
    if (parts.length === 0) return '?';
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  function hue(n: string | null | undefined): number {
    if (!n) return 0;
    let h = 0;
    for (let i = 0; i < n.length; i++) h = (h * 31 + n.charCodeAt(i)) >>> 0;
    return h % 360;
  }
</script>

<div
  class={cn(
    'avatar inline-flex size-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white',
    className
  )}
  style="--h1: {hue(name)}; --h2: {(hue(name) + 40) % 360};"
>
  {initials(name)}
</div>

<style>
  /* Modest, lower-saturation tint — a soft identicon, not a neon dot.
     Light and dark get their own toning so white initials stay legible. */
  .avatar {
    background: linear-gradient(
      135deg,
      hsl(var(--h1) 42% 54%) 0%,
      hsl(var(--h2) 40% 46%) 100%
    );
    /* soft top sheen + inner edge for a subtle, modern depth */
    box-shadow:
      inset 0 1px 0 hsl(0 0% 100% / 0.25),
      inset 0 0 0 1px hsl(0 0% 100% / 0.08);
  }
  :global(.dark) .avatar {
    background: linear-gradient(
      135deg,
      hsl(var(--h1) 38% 46%) 0%,
      hsl(var(--h2) 36% 38%) 100%
    );
    box-shadow:
      inset 0 1px 0 hsl(0 0% 100% / 0.15),
      inset 0 0 0 1px hsl(0 0% 0% / 0.18);
  }
</style>
