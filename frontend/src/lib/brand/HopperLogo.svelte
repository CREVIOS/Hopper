<script lang="ts">
  import { cn } from '$lib/utils';

  let {
    size = 28,
    class: className,
    /** Gentle continuous bob when idle. Hover always triggers the full hop. */
    idle = false
  }: { size?: number; class?: string; idle?: boolean } = $props();

  // Glyph scales with the tile; tuned so strokes stay crisp from 16px to 48px.
  const glyph = $derived(Math.round(size * 0.62));
  // Corner radius tracks size for a true app-icon "squircle" feel.
  const radius = $derived(Math.round(size * 0.28));
</script>

<span
  class={cn('hopper-mark relative inline-grid shrink-0 place-items-center', idle && 'is-idle', className)}
  style="width:{size}px;height:{size}px;border-radius:{radius}px"
  aria-hidden="true"
>
  <!-- base gradient tile -->
  <span class="hopper-base absolute inset-0" style="border-radius:{radius}px"></span>
  <!-- top-left light source: glossy highlight -->
  <span class="hopper-gloss pointer-events-none absolute inset-0" style="border-radius:{radius}px"></span>
  <!-- bottom inner shadow for depth -->
  <span class="hopper-vignette pointer-events-none absolute inset-0" style="border-radius:{radius}px"></span>
  <!-- inset bevel ring -->
  <span class="hopper-ring pointer-events-none absolute inset-0" style="border-radius:{radius}px"></span>
  <!-- specular sweep on hover -->
  <span class="hopper-sheen pointer-events-none absolute inset-0" style="border-radius:{radius}px"></span>

  <svg
    class="hopper-glyph relative"
    width={glyph}
    height={glyph}
    viewBox="0 0 24 24"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
  >
    <!-- soft cast shadow on the ground; shrinks as the hopper leaps -->
    <ellipse class="hopper-cast" cx="12" cy="19.4" rx="3.4" ry="0.85" fill="#000" opacity="0.22" />

    <!-- hop trajectory -->
    <path
      d="M5 17.2C7 9.8 17 9.8 19 17.2"
      stroke="#fff"
      stroke-width="2"
      stroke-linecap="round"
      opacity="0.5"
    />
    <!-- landing pads -->
    <path
      d="M4.3 18.6h2.4M17.3 18.6h2.4"
      stroke="#fff"
      stroke-width="2"
      stroke-linecap="round"
      opacity="0.42"
    />

    <!-- the hopper: a glossy bead, caught mid-leap above the arc -->
    <g class="hopper-dot">
      <circle cx="12" cy="7.2" r="2.9" fill="url(#hopperBead)" />
      <circle cx="12" cy="7.2" r="2.9" fill="none" stroke="#fff" stroke-width="0.5" opacity="0.7" />
      <!-- tiny specular highlight makes the bead read as 3D -->
      <circle cx="11.1" cy="6.2" r="0.85" fill="#fff" opacity="0.9" />
    </g>

    <defs>
      <radialGradient id="hopperBead" cx="0.38" cy="0.32" r="0.85">
        <stop offset="0%" stop-color="#ffffff" />
        <stop offset="55%" stop-color="#ffffff" />
        <stop offset="100%" stop-color="#dfe3ff" />
      </radialGradient>
    </defs>
  </svg>
</span>

<style>
  .hopper-mark {
    /* layered depth: outer cast + colored glow + crisp top light line */
    box-shadow:
      0 1px 2px hsl(224 50% 8% / 0.22),
      0 6px 16px -6px hsl(var(--primary) / 0.55),
      inset 0 1px 0 hsl(0 0% 100% / 0.4);
    transition:
      transform 0.25s cubic-bezier(0.16, 1, 0.3, 1),
      box-shadow 0.25s ease;
  }
  .hopper-mark:hover {
    transform: scale(1.05) translateY(-0.5px);
    box-shadow:
      0 2px 4px hsl(224 50% 8% / 0.24),
      0 12px 26px -8px hsl(var(--primary) / 0.7),
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
  /* glossy upper highlight, light from top-left */
  .hopper-gloss {
    background:
      radial-gradient(120% 90% at 28% 10%, hsl(0 0% 100% / 0.5), transparent 55%),
      linear-gradient(180deg, hsl(0 0% 100% / 0.18) 0%, transparent 38%);
  }
  /* grounded bottom for dimensionality */
  .hopper-vignette {
    background: linear-gradient(to top, hsl(252 80% 20% / 0.35) 0%, transparent 46%);
  }
  /* fine inset bevel ring */
  .hopper-ring {
    box-shadow:
      inset 0 0 0 1px hsl(0 0% 100% / 0.16),
      inset 0 -1px 2px hsl(252 80% 16% / 0.3);
  }

  .hopper-glyph {
    /* lifts the white glyph off the tile */
    filter: drop-shadow(0 1px 1.2px hsl(252 70% 12% / 0.45));
  }

  .hopper-dot {
    transform-box: fill-box;
    transform-origin: center;
  }
  .hopper-cast {
    transform-box: fill-box;
    transform-origin: center;
  }

  /* Full squash-and-stretch hop on hover; the cast shadow reacts. */
  .hopper-mark:hover .hopper-dot {
    animation: hop 0.62s cubic-bezier(0.5, 0.05, 0.3, 1);
  }
  .hopper-mark:hover .hopper-cast {
    animation: cast 0.62s cubic-bezier(0.5, 0.05, 0.3, 1);
  }
  @keyframes hop {
    0% {
      transform: translateY(0) scale(1, 1);
    }
    18% {
      transform: translateY(1.5px) scale(1.18, 0.82);
    }
    52% {
      transform: translateY(-6px) scale(0.88, 1.14);
    }
    82% {
      transform: translateY(1.5px) scale(1.14, 0.86);
    }
    100% {
      transform: translateY(0) scale(1, 1);
    }
  }
  @keyframes cast {
    0%,
    100% {
      transform: scale(1);
      opacity: 0.22;
    }
    52% {
      transform: scale(0.55);
      opacity: 0.1;
    }
  }

  /* Calm idle bob (only when not hovering, so the hop wins). */
  .hopper-mark.is-idle:not(:hover) .hopper-dot {
    animation: bob 3.2s ease-in-out infinite;
  }
  @keyframes bob {
    0%,
    100% {
      transform: translateY(0);
    }
    50% {
      transform: translateY(-1.6px);
    }
  }

  .hopper-sheen {
    background: linear-gradient(
      120deg,
      transparent 35%,
      hsl(0 0% 100% / 0.45) 50%,
      transparent 65%
    );
    transform: translateX(-130%);
  }
  .hopper-mark:hover .hopper-sheen {
    animation: sheen 0.7s ease;
  }
  @keyframes sheen {
    to {
      transform: translateX(130%);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .hopper-mark:hover {
      transform: none;
    }
    .hopper-dot,
    .hopper-cast,
    .hopper-sheen {
      animation: none !important;
    }
  }
</style>
