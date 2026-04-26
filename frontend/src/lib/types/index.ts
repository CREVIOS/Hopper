export type PodState =
  | 'pending'
  | 'creating'
  | 'running'
  | 'stopping'
  | 'terminated'
  | 'failed';

export type VmPlan = 'small' | 'medium' | 'large';

export const VM_PLAN_INFO: Record<VmPlan, { cpu: string; memory: string; rate: number }> = {
  small: { cpu: '1 CPU', memory: '2 GB', rate: 1 },
  medium: { cpu: '2 CPU', memory: '4 GB', rate: 2 },
  large: { cpu: '4 CPU', memory: '8 GB', rate: 4 }
};

export type UserRole = 'admin' | 'professor' | 'student';

export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
}

export interface Pod {
  id: string;
  user_id: string;
  state: PodState;
  plan: string;
  image: string;
  cpu?: string;
  memory?: string;
  node_name?: string;
  namespace: string;
  ssh_port?: number;
  vscode_port?: number;
  created_at: string;
  updated_at: string;
}

export interface Credit {
  account_id: string;
  balance: number;
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

export interface VmMetrics {
  pod_id: string;
  cpu_percent: number;
  memory_used_bytes: number;
  memory_limit_bytes: number;
}
