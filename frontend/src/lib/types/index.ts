export type PodState =
  | 'pending'
  | 'creating'
  | 'running'
  | 'stopping'
  | 'terminated'
  | 'failed';

export type VmPlan = 'small' | 'medium' | 'large';

export const VM_PLAN_INFO: Record<
  VmPlan,
  { cpu: string; memory: string; disk: string; rate: number; description: string }
> = {
  small: {
    cpu: '1 CPU',
    memory: '2 GB',
    disk: '5 GB',
    rate: 1,
    description: 'Lightweight tasks, scripting, prototyping'
  },
  medium: {
    cpu: '2 CPU',
    memory: '4 GB',
    disk: '10 GB',
    rate: 2,
    description: 'Compilation, web servers, mid-size workloads'
  },
  large: {
    cpu: '4 CPU',
    memory: '8 GB',
    disk: '20 GB',
    rate: 4,
    description: 'Heavy builds, training, multi-process work'
  }
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
  ssh_password?: string;
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

export type VmTemplate = 'ubuntu' | 'python-ml' | 'cpp' | 'java';

export const VM_TEMPLATE_INFO: Record<
  VmTemplate,
  { name: string; description: string; tagline: string; accent: string }
> = {
  ubuntu: {
    name: 'Ubuntu 22.04',
    description: 'Base Ubuntu with SSH',
    tagline: 'Clean slate — install whatever you want',
    accent: 'orange'
  },
  'python-ml': {
    name: 'Python / ML',
    description: 'Python 3, NumPy, Pandas, Jupyter',
    tagline: 'Pre-loaded data science stack',
    accent: 'yellow'
  },
  cpp: {
    name: 'C / C++',
    description: 'GCC, CMake, GDB, Valgrind',
    tagline: 'Native compile + debug toolchain',
    accent: 'blue'
  },
  java: {
    name: 'Java',
    description: 'OpenJDK 21, Maven',
    tagline: 'JVM environment with build tools',
    accent: 'red'
  }
};

export interface VmMetrics {
  pod_id: string;
  cpu_percent: number;
  memory_used_bytes: number;
  memory_limit_bytes: number;
}

export interface UsagePoint {
  time: string;
  cpu_percent: number;
  memory_used_bytes: number;
  memory_limit_bytes: number;
}

export interface UsageSeries {
  pod_id: string;
  range: string;
  data: UsagePoint[];
}

export interface SshKey {
  id: string;
  name: string;
  public_key: string;
  fingerprint: string;
  created_at: string;
}

export type NotificationSeverity = 'success' | 'warning' | 'error' | 'info';

export type NotificationType =
  | 'credit_warning'
  | 'credit_grace'
  | 'credits_received'
  | 'vm_ready'
  | 'vm_terminated'
  | 'vm_failed';

export interface AppNotification {
  id: string;
  type: NotificationType;
  severity: NotificationSeverity;
  title: string;
  body: string;
  action_url?: string | null;
  metadata: Record<string, unknown>;
  read_at?: string | null;
  created_at: string;
}

export interface NotificationListResponse {
  notifications: AppNotification[];
  unread_count: number;
}
