import { afterEach, describe, expect, it } from 'vitest';

import { _resolveConfirm, confirm, confirmStore } from './confirm.svelte';

afterEach(() => {
  _resolveConfirm(false);
});

describe('confirm store', () => {
  it('opens with defaults and resolves when confirmed', async () => {
    const pending = confirm({ title: 'Terminate pod?' });

    expect(confirmStore.open).toBe(true);
    expect(confirmStore.title).toBe('Terminate pod?');
    expect(confirmStore.confirmLabel).toBe('Continue');
    expect(confirmStore.cancelLabel).toBe('Cancel');
    expect(confirmStore.variant).toBe('default');

    _resolveConfirm(true);

    await expect(pending).resolves.toBe(true);
    expect(confirmStore.open).toBe(false);
    expect(confirmStore.resolve).toBeNull();
  });

  it('cancels the previous pending confirmation when a new one starts', async () => {
    const first = confirm({ title: 'First dialog' });
    const second = confirm({
      title: 'Second dialog',
      description: 'New description',
      confirmLabel: 'Launch',
      cancelLabel: 'Stay here',
      variant: 'destructive'
    });

    await expect(first).resolves.toBe(false);
    expect(confirmStore.title).toBe('Second dialog');
    expect(confirmStore.description).toBe('New description');
    expect(confirmStore.confirmLabel).toBe('Launch');
    expect(confirmStore.cancelLabel).toBe('Stay here');
    expect(confirmStore.variant).toBe('destructive');

    _resolveConfirm(false);

    await expect(second).resolves.toBe(false);
  });
});
