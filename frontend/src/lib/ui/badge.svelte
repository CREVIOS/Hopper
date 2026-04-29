<script lang="ts" module>
  import { tv, type VariantProps } from 'tailwind-variants';

  export const badgeVariants = tv({
    base: 'inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors',
    variants: {
      variant: {
        default: 'border-transparent bg-primary text-primary-foreground',
        secondary: 'border-transparent bg-secondary text-secondary-foreground',
        outline: 'text-foreground border-border',
        success: 'border-transparent bg-success/15 text-success',
        warning: 'border-transparent bg-warning/15 text-warning',
        info: 'border-transparent bg-info/15 text-info',
        destructive: 'border-transparent bg-destructive/15 text-destructive',
        muted: 'border-transparent bg-muted text-muted-foreground'
      }
    },
    defaultVariants: { variant: 'default' }
  });

  export type BadgeVariant = VariantProps<typeof badgeVariants>['variant'];
</script>

<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { HTMLAttributes } from 'svelte/elements';
  import { cn } from '$lib/utils';

  type Props = HTMLAttributes<HTMLSpanElement> & {
    class?: string;
    variant?: BadgeVariant;
    children: Snippet;
  };

  let { class: className, variant = 'default', children, ...rest }: Props = $props();
</script>

<span class={cn(badgeVariants({ variant }), className)} {...rest}>
  {@render children()}
</span>
