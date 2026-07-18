import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  chartColor,
  cn,
  copyToClipboard,
  formatBytes,
  relTime,
  shortId
} from './utils';

describe('utils', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-18T12:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('merges class names', () => {
    expect(cn('px-2', false && 'hidden', 'px-4', 'py-1')).toBe('px-4 py-1');
  });

  it('formats byte counts across units', () => {
    expect(formatBytes(0)).toBe('0 B');
    expect(formatBytes(1024)).toBe('1.0 KB');
    expect(formatBytes(1024 ** 3, 2)).toBe('1.00 GB');
  });

  it('formats relative times for recent and older timestamps', () => {
    expect(relTime(null)).toBe('—');
    expect(relTime(new Date('2026-07-18T11:59:58Z'))).toBe('just now');
    expect(relTime('2026-07-18T11:59:30Z')).toBe('30s ago');
    expect(relTime('2026-07-18T11:30:00Z')).toBe('30m ago');
    expect(relTime('2026-07-18T09:00:00Z')).toBe('3h ago');
    expect(relTime('2026-07-15T12:00:00Z')).toBe('3d ago');
    expect(relTime('2026-07-01T12:00:00Z')).toBe('Jul 1');
  });

  it('shortens long ids and leaves short ids alone', () => {
    expect(shortId(null)).toBe('');
    expect(shortId('abcdef')).toBe('abcdef');
    expect(shortId('abcdefghijk', 5)).toBe('abcde');
  });

  it('copies to the clipboard when available', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });

    await expect(copyToClipboard('pod-123')).resolves.toBeUndefined();
    expect(writeText).toHaveBeenCalledWith('pod-123');
  });

  it('rejects clipboard writes when the API is unavailable', async () => {
    vi.stubGlobal('navigator', {});

    await expect(copyToClipboard('pod-123')).rejects.toThrow('Clipboard not available');
  });

  it('resolves chart colors on the server and in the browser', () => {
    expect(chartColor('primary')).toBe('hsl(0 0% 50%)');

    vi.stubGlobal('window', {});
    vi.stubGlobal('document', { documentElement: {} });
    vi.stubGlobal(
      'getComputedStyle',
      vi.fn(() => ({
        getPropertyValue: (name: string) => (name === '--primary' ? '210 100% 50%' : '')
      }))
    );

    expect(chartColor('primary')).toBe('hsl(210 100% 50%)');
    expect(chartColor('primary', 0.4)).toBe('hsl(210 100% 50% / 0.4)');
    expect(chartColor('missing')).toBe('hsl(0 0% 50%)');
  });
});
