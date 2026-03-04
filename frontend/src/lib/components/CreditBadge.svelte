<script lang="ts">
  let { balance = 0 }: { balance: number } = $props();
</script>

<div class="inline-flex items-center gap-1 rounded-full bg-indigo-100 px-3 py-1 text-sm font-medium text-indigo-800">
  <span>{balance.toFixed(1)}</span>
  <span class="text-indigo-500">credits</span>
</div>
