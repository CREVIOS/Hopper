import { writable } from 'svelte/store';
import type { Pod, VmMetrics } from '$lib/types';

export const pods = writable<Pod[]>([]);
export const activePodMetrics = writable<VmMetrics | null>(null);
