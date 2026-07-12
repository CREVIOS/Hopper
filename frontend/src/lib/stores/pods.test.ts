import { get } from 'svelte/store';
import { beforeEach, describe, expect, it } from 'vitest';
import { activePodMetrics, pods } from './pods';

beforeEach(() => {
  pods.set([]);
  activePodMetrics.set(null);
});

describe('pod stores', () => {
  it('tracks deterministic pod state updates', () => {
    pods.set([{ id:'pod-1', user_id:'student-1', state:'running', plan:'small', image:'ubuntu', namespace:'hopper', created_at:'2026-01-01', updated_at:'2026-01-01' }]);
    expect(get(pods)).toHaveLength(1);
    expect(get(pods)[0].state).toBe('running');
  });

  it('tracks the latest streamed metrics', () => {
    activePodMetrics.set({ pod_id:'pod-1', cpu_percent:42, memory_used_bytes:1, memory_limit_bytes:2 });
    expect(get(activePodMetrics)?.cpu_percent).toBe(42);
  });
});
