<script lang="ts">
  import { Skeleton } from '$lib/ui';

  let { variant = 'dashboard' }: { variant?: 'dashboard' | 'admin' | 'teacher' | 'credits' } = $props();
</script>

<div class="space-y-6" aria-hidden="true">
  <div class="space-y-3">
    <Skeleton class="h-4 w-28" />
    <Skeleton class="h-11 w-56 sm:w-72" />
    <Skeleton class="h-4 w-full max-w-2xl" />
  </div>

  <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
    <Skeleton class="h-28 rounded-2xl" />
    <Skeleton class="h-28 rounded-2xl" />
    <Skeleton class="h-28 rounded-2xl" />
    <Skeleton class="h-28 rounded-2xl" />
  </div>

  {#if variant === 'dashboard'}
    <div class="grid gap-4 lg:grid-cols-[1fr_340px]">
      <Skeleton class="h-[22rem] rounded-2xl" />
      <Skeleton class="h-[22rem] rounded-2xl" />
    </div>
    <Skeleton class="h-[26rem] rounded-2xl" />
    <div class="grid gap-4 lg:grid-cols-2">
      <Skeleton class="h-[20rem] rounded-2xl" />
      <Skeleton class="h-[20rem] rounded-2xl" />
    </div>
  {:else if variant === 'admin'}
    <div class="grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
      <Skeleton class="h-[28rem] rounded-2xl" />
      <Skeleton class="h-[28rem] rounded-2xl" />
    </div>
    <Skeleton class="h-[32rem] rounded-2xl" />
  {:else if variant === 'teacher'}
    <div class="space-y-3">
      <div class="flex justify-end">
        <Skeleton class="h-9 w-48 rounded-md" />
      </div>
      <Skeleton class="h-[30rem] rounded-2xl" />
    </div>
  {:else if variant === 'credits'}
    <div class="grid gap-4 lg:grid-cols-[1.05fr_1.4fr]">
      <Skeleton class="h-[18rem] rounded-2xl" />
      <div class="grid gap-4 sm:grid-cols-2">
        <Skeleton class="h-[8.5rem] rounded-2xl" />
        <Skeleton class="h-[8.5rem] rounded-2xl" />
        <Skeleton class="h-[8.5rem] rounded-2xl" />
        <Skeleton class="h-[8.5rem] rounded-2xl" />
      </div>
    </div>
    <Skeleton class="h-[24rem] rounded-2xl" />
    <Skeleton class="h-[28rem] rounded-2xl" />
  {/if}
</div>
