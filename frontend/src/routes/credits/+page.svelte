<script lang="ts">
  import CreditBadge from '$lib/components/CreditBadge.svelte';
  import type { CreditTransaction } from '$lib/types';

  let { data }: { data: { balance: number; transactions: CreditTransaction[] } } = $props();
</script>

<div class="space-y-6">
  <div class="flex items-center justify-between">
    <h1 class="text-2xl font-bold">Credits</h1>
    <CreditBadge balance={data.balance} />
  </div>

  <div class="rounded-lg border bg-white">
    <table class="w-full">
      <thead class="border-b bg-gray-50">
        <tr>
          <th class="px-4 py-2 text-left text-sm">Date</th>
          <th class="px-4 py-2 text-left text-sm">Type</th>
          <th class="px-4 py-2 text-right text-sm">Amount</th>
        </tr>
      </thead>
      <tbody>
        {#each data.transactions as tx (tx.id)}
          <tr class="border-b">
            <td class="px-4 py-2 text-sm">{new Date(tx.created_at).toLocaleString()}</td>
            <td class="px-4 py-2 text-sm">{tx.type}</td>
            <td class="px-4 py-2 text-right text-sm {tx.direction === 'debit' ? 'text-red-600' : 'text-green-600'}">
              {tx.direction === 'debit' ? '-' : '+'}{tx.amount.toFixed(2)}
            </td>
          </tr>
        {:else}
          <tr>
            <td colspan="3" class="px-4 py-8 text-center text-gray-500">No transactions yet.</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
</div>
