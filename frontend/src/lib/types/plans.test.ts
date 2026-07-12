import { describe, expect, it } from 'vitest';
import { VM_PLAN_INFO } from './index';

describe('VM plan catalogue', () => {
  it('uses the production small, medium, and large prices', () => {
    expect(Object.keys(VM_PLAN_INFO)).toEqual(['small', 'medium', 'large']);
    expect(Object.values(VM_PLAN_INFO).map(plan => plan.rate)).toEqual([1, 2, 4]);
  });
});
