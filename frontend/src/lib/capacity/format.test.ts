import { describe, expect, it } from 'vitest';

import { capacityTone, fmtCapacity } from './format';

describe('fmtCapacity', () => {
  it('renders an em dash when the figure is unknown', () => {
    expect(fmtCapacity(null)).toBe('—');
    expect(fmtCapacity(undefined)).toBe('—');
  });

  it('renders an em dash rather than printing a non-finite number into the card', () => {
    expect(fmtCapacity(NaN)).toBe('—');
    expect(fmtCapacity(Infinity)).toBe('—');
    expect(fmtCapacity(-Infinity)).toBe('—');
  });

  it('renders whole numbers without a decimal point', () => {
    expect(fmtCapacity(8)).toBe('8');
    expect(fmtCapacity(11)).toBe('11');
    expect(fmtCapacity(0)).toBe('0');
  });

  // The bug this guards: a VM reserves a quarter of its plan CPU, so releasing a
  // "1 CPU" VM moves free CPU by exactly 0.25. Rounding to one decimal rendered
  // 8.25 as "8.3", which read as a broken 0.3-core delta.
  it('preserves quarter-core steps instead of rounding them away', () => {
    expect(fmtCapacity(8.25)).toBe('8.25');
    expect(fmtCapacity(8.5)).toBe('8.5');
    expect(fmtCapacity(8.75)).toBe('8.75');
  });

  it('rounds beyond two decimals rather than leaking float noise', () => {
    expect(fmtCapacity(0.1 + 0.2)).toBe('0.3');
    expect(fmtCapacity(8.333333)).toBe('8.33');
    expect(fmtCapacity(15.999999999999998)).toBe('16');
  });

  it('rounds halves away from zero in both directions', () => {
    expect(fmtCapacity(2.005)).toBe('2.01');
    expect(fmtCapacity(-2.005)).toBe('-2.01');
  });

  // Free capacity is clamped at zero by the API, so a negative should never
  // reach the card. Pinned anyway so the rounding contract holds if that clamp
  // ever moves or fmtCapacity is reused for a signed delta.
  it('formats negatives symmetrically with positives', () => {
    expect(fmtCapacity(-8.25)).toBe('-8.25');
    expect(fmtCapacity(-9)).toBe('-9');
  });

  it('never renders a negative zero', () => {
    expect(fmtCapacity(-0)).toBe('0');
    expect(fmtCapacity(-0.001)).toBe('0');
  });
});

describe('capacityTone', () => {
  it('is neutral when either figure is unknown', () => {
    expect(capacityTone(null, 11)).toBe('default');
    expect(capacityTone(undefined, 11)).toBe('default');
    expect(capacityTone(8, null)).toBe('default');
  });

  it('is neutral when the total is zero rather than dividing by it', () => {
    expect(capacityTone(0, 0)).toBe('default');
  });

  it('reports healthy headroom as success', () => {
    expect(capacityTone(8, 11)).toBe('success');
    expect(capacityTone(11, 11)).toBe('success');
  });

  it('warns as headroom tightens', () => {
    expect(capacityTone(3, 11)).toBe('warning');
  });

  it('escalates to destructive when nearly full', () => {
    expect(capacityTone(1, 11)).toBe('destructive');
    expect(capacityTone(0, 11)).toBe('destructive');
  });

  // The thresholds are exclusive: a ratio sitting exactly on a boundary takes
  // the calmer tone. Pinned so a `<` -> `<=` slip can't drift the whole panel.
  it('treats an exact threshold ratio as the calmer tone', () => {
    expect(capacityTone(1.5, 10)).toBe('warning');
    expect(capacityTone(1.4999, 10)).toBe('destructive');
    expect(capacityTone(3.5, 10)).toBe('success');
    expect(capacityTone(3.4999, 10)).toBe('warning');
  });
});
