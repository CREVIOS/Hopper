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
    'inline-flex size-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white',
    className
  )}
  style="background: linear-gradient(135deg, hsl({hue(name)} 70% 55%) 0%, hsl({(hue(name) + 40) % 360} 70% 45%) 100%);"
>
  {initials(name)}
</div>
