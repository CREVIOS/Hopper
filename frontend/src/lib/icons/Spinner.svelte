<script lang="ts">
  import { cn } from '$lib/utils';

  // Branded loading spinner — a single sweeping arc over a faint track.
  // Inherits color via currentColor and sizes via `size-*` utilities,
  // so it is a drop-in replacement for `<Loader2 class="size-4 animate-spin" />`.
  let { class: className, label = 'Loading' }: { class?: string; label?: string } = $props();
</script>

<svg
  class={cn('hopper-spin size-4', className)}
  viewBox="0 0 24 24"
  fill="none"
  role="status"
  aria-label={label}
  xmlns="http://www.w3.org/2000/svg"
>
  <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2.5" opacity="0.2" />
  <path
    d="M21 12a9 9 0 0 0-9-9"
    stroke="currentColor"
    stroke-width="2.5"
    stroke-linecap="round"
  />
</svg>

<style>
  .hopper-spin {
    animation: hopper-spin 0.7s linear infinite;
    transform-origin: center;
  }
  @keyframes hopper-spin {
    to {
      transform: rotate(360deg);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .hopper-spin {
      animation-duration: 1.6s;
    }
  }
</style>
