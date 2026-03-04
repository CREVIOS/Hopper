export type PodState =
  | 'pending'
  | 'creating'
  | 'running'
  | 'stopping'
  | 'terminated'
  | 'failed';

export type GpuTier = 'premium' | 'standard' | 'budget' | 'scavenger';

export const GPU_TIER_RATES: Record<GpuTier, number> = {
  premium: 15,
  standard: 10,
  budget: 5,
  scavenger: 0
};

export type UserRole =
  | 'platform_admin'
  | 'university_admin'
  | 'department_admin'
  | 'professor'
  | 'ta'
  | 'student';

export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  university_id: string;
}

export interface Pod {
  id: string;
  user_id: string;
  state: PodState;
  gpu_tier: GpuTier;
  image: string;
  node_name?: string;
  namespace: string;
  created_at: string;
  updated_at: string;
}

export interface Credit {
  account_id: string;
  balance: number;
  as_of: string;
}

export interface CreditTransaction {
  id: string;
  account_id: string;
  amount: number;
  direction: 'debit' | 'credit';
  type: string;
  pod_id?: string;
  created_at: string;
}

export interface GpuMetrics {
  pod_id: string;
  gpu_utilization: number;
  memory_used: number;
  memory_total: number;
  temperature: number;
  power_usage: number;
  timestamp: string;
}
