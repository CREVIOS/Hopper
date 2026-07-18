import { render } from 'svelte/server';
import { describe, expect, it } from 'vitest';
import CreditBadge from './CreditBadge.svelte';

describe('CreditBadge', () => {
  it('renders a formatted accessible credit link', () => {
    const { body } = render(CreditBadge, { props: { balance: 12.34 } });
    expect(body).toContain('12.3');
    expect(body).toContain('credits');
    expect(body).toContain('href="/credits"');
  });
});
