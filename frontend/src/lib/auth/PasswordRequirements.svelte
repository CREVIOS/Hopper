<script lang="ts">
  import { Check, X } from 'lucide-svelte';
  import { PASSWORD_RULES } from './passwordPolicy';

  let {
    password,
    username = '',
    showErrors = false
  }: {
    password: string;
    /** The email being signed up with — the realm forbids reusing it as the password. */
    username?: string;
    /** After a rejected submit, mark the unmet rules instead of leaving them neutral. */
    showErrors?: boolean;
  } = $props();

  // Rendered before the user types anything, so the requirements are known up
  // front rather than arriving as a server error after a failed submit.
  const results = $derived(
    PASSWORD_RULES.map((rule) => ({
      id: rule.id,
      text: rule.text,
      met: rule.test(password, username)
    }))
  );
</script>

<ul class="mt-2 space-y-1" aria-label="Password requirements">
  {#each results as rule (rule.id)}
    <li
      class={`flex items-center gap-1.5 text-[11px] leading-tight transition-colors ${
        rule.met
          ? 'text-foreground/70'
          : showErrors
            ? 'text-destructive'
            : 'text-muted-foreground'
      }`}
    >
      <span class="flex size-3.5 shrink-0 items-center justify-center">
        {#if rule.met}
          <Check class="size-3 text-primary" strokeWidth={3} />
        {:else if showErrors}
          <X class="size-3" strokeWidth={3} />
        {:else}
          <span class="size-1 rounded-full bg-current opacity-50"></span>
        {/if}
      </span>
      <span>{rule.text}</span>
    </li>
  {/each}
</ul>
