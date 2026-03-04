import { writable } from 'svelte/store';
import type { Pod, GpuMetrics } from '$lib/types';

export const pods = writable<Pod[]>([]);
export const activePodMetrics = writable<GpuMetrics | null>(null);
