<script lang="ts">
  import {
    Users,
    Server,
    Database,
    Activity,
    Coins,
    Search,
    ShieldAlert,
    HardDrive,
    Cpu,
    MemoryStick,
    ScrollText,
    ArrowRight,
    Shield,
    GraduationCap,
    User,
    ChevronDown,
    Check,
    X,
    Power,
    Inbox,
    Plus,
    Pencil,
    Gauge,
    BookOpen,
    UserPlus,
    Trash2
  } from 'lucide-svelte';
  import Spinner from '$lib/icons/Spinner.svelte';
  import { onMount, type SvelteComponent } from 'svelte';
  import { invalidateAll } from '$app/navigation';
  import { toast } from 'svelte-sonner';
  import {
    Button,
    Card,
    CardContent,
    Input,
    Label,
    Badge,
    Tabs,
    Table,
    Tooltip,
    Dialog,
    Pagination,
    Separator,
    DropdownMenu
  } from '$lib/ui';
  import StatCard from '$lib/components/StatCard.svelte';
  import StatusBadge from '$lib/components/StatusBadge.svelte';
  import SectionHeader from '$lib/components/SectionHeader.svelte';
  import PageTitle from '$lib/components/PageTitle.svelte';
  import Avatar from '$lib/ui/avatar.svelte';
  import { api, ApiError } from '$lib/api/client';
  import { relTime, shortId } from '$lib/utils';

  type ActiveVm = {
    id: string;
    state: string;
    plan: string;
    image: string;
    cpu: string | null;
    memory: string | null;
    user_email: string | null;
    user_name: string | null;
    started_at: string | null;
  };
  type AuditLog = {
    id: string;
    user_id: string | null;
    action: string;
    resource_type: string | null;
    resource_id: string | null;
    ip_address: string | null;
    status_code: number | null;
    created_at: string | null;
  };
  type Node = {
    name: string;
    cpu_capacity: string;
    memory_capacity: string;
    cpu_allocatable: string;
    memory_allocatable: string;
    pod_count: number;
    ready: boolean;
  };
  type AdminUser = {
    id: string;
    email: string;
    name: string;
    role: string;
    created_at: string | null;
  };
  type Plan = {
    name: string;
    display_name: string;
    cpu: string;
    memory: string;
    disk: string;
    credits_per_hour: number;
    workspace_gb: number;
    is_active: boolean;
  };
  type Image = {
    template: string;
    display_name: string;
    image: string;
    description: string;
    is_active: boolean;
    is_default: boolean;
  };
  type Course = {
    id: string;
    code: string;
    name: string;
    description: string;
    professor_id: string;
    professor_name: string | null;
    enrolled_count: number;
    is_active: boolean;
  };
  type RosterMember = { id: string; email: string; name: string; balance: number };

  let {
    data
  }: {
    data: {
      currentUserId: string;
      currentUserRole: string;
      stats: {
        total_users: number;
        active_vms: number;
        total_vms_created: number;
      };
      nodes: Node[];
      users: AdminUser[];
      activeVms: ActiveVm[];
      auditLogs: AuditLog[];
      teacherRequests: { id: string; email: string; name: string; created_at: string | null }[];
      issues: {
        id: string;
        user_id: string;
        pod_id: string | null;
        description: string;
        status: string;
        response: string | null;
        created_at: string | null;
        resolved_at: string | null;
      }[];
      plans: Plan[];
      images: Image[];
      courses: Course[];
    };
  } = $props();

  // Teacher-approval actions (admin only).
  let processingReq = $state<string | null>(null);
  async function approveTeacher(r: { id: string; email: string }) {
    processingReq = r.id;
    const tid = toast.loading(`Approving ${r.email}…`);
    try {
      await api.post(`/admin/teacher-requests/${r.id}/approve`);
      toast.success(`${r.email} is now a teacher`, { id: tid });
      await invalidateAll();
    } catch (e) {
      toast.error('Could not approve', { id: tid, description: e instanceof ApiError ? e.message : '' });
    } finally {
      processingReq = null;
    }
  }
  async function rejectTeacher(r: { id: string; email: string }) {
    processingReq = r.id;
    const tid = toast.loading(`Rejecting ${r.email}…`);
    try {
      await api.post(`/admin/teacher-requests/${r.id}/reject`);
      toast.success('Request rejected', { id: tid });
      await invalidateAll();
    } catch (e) {
      toast.error('Could not reject', { id: tid, description: e instanceof ApiError ? e.message : '' });
    } finally {
      processingReq = null;
    }
  }

  // VM plan catalogue management (admin CRUD).
  type PlanForm = {
    name: string;
    display_name: string;
    cpu: string;
    memory: string;
    disk: string;
    credits_per_hour: number | string;
    workspace_gb: number | string;
  };
  let planDialogOpen = $state(false);
  let planEditing = $state<string | null>(null); // plan name when editing, null = creating
  let planSaving = $state(false);
  let planBusy = $state<string | null>(null);
  let planForm = $state<PlanForm>({
    name: '',
    display_name: '',
    cpu: '',
    memory: '',
    disk: '',
    credits_per_hour: '',
    workspace_gb: ''
  });

  function openCreatePlan() {
    planEditing = null;
    planForm = { name: '', display_name: '', cpu: '2', memory: '4Gi', disk: '10Gi', credits_per_hour: 2, workspace_gb: 50 };
    planDialogOpen = true;
  }
  function openEditPlan(p: Plan) {
    planEditing = p.name;
    planForm = {
      name: p.name,
      display_name: p.display_name,
      cpu: p.cpu,
      memory: p.memory,
      disk: p.disk,
      credits_per_hour: p.credits_per_hour,
      workspace_gb: p.workspace_gb
    };
    planDialogOpen = true;
  }
  async function savePlan() {
    planSaving = true;
    const tid = toast.loading('Saving plan…');
    try {
      const payload = {
        display_name: planForm.display_name,
        cpu: String(planForm.cpu),
        memory: String(planForm.memory),
        disk: String(planForm.disk),
        credits_per_hour: Number(planForm.credits_per_hour),
        workspace_gb: Number(planForm.workspace_gb)
      };
      if (planEditing) {
        await api.put(`/admin/plans/${planEditing}`, payload);
      } else {
        await api.post('/admin/plans', { name: planForm.name, ...payload });
      }
      toast.success('Plan saved', { id: tid });
      planDialogOpen = false;
      await invalidateAll();
    } catch (e) {
      toast.error('Could not save plan', { id: tid, description: e instanceof ApiError ? e.message : '' });
    } finally {
      planSaving = false;
    }
  }
  async function deactivatePlan(p: Plan) {
    if (
      !confirm(
        `Deactivate plan "${p.name}"? It will be hidden from new VM launches. Existing VMs keep billing at their current rate.`
      )
    )
      return;
    planBusy = p.name;
    const tid = toast.loading('Deactivating…');
    try {
      await api.delete(`/admin/plans/${p.name}`);
      toast.success('Plan deactivated', { id: tid });
      await invalidateAll();
    } catch (e) {
      toast.error('Could not deactivate', { id: tid, description: e instanceof ApiError ? e.message : '' });
    } finally {
      planBusy = null;
    }
  }
  async function reactivatePlan(p: Plan) {
    planBusy = p.name;
    const tid = toast.loading('Reactivating…');
    try {
      await api.put(`/admin/plans/${p.name}`, { is_active: true });
      toast.success('Plan reactivated', { id: tid });
      await invalidateAll();
    } catch (e) {
      toast.error('Could not reactivate', { id: tid, description: e instanceof ApiError ? e.message : '' });
    } finally {
      planBusy = null;
    }
  }

  // VM image / template catalogue management (admin CRUD).
  type ImageForm = {
    template: string;
    display_name: string;
    image: string;
    description: string;
    is_default: boolean;
  };
  let imageDialogOpen = $state(false);
  let imageEditing = $state<string | null>(null);
  let imageSaving = $state(false);
  let imageBusy = $state<string | null>(null);
  let imageForm = $state<ImageForm>({
    template: '',
    display_name: '',
    image: '',
    description: '',
    is_default: false
  });

  function openCreateImage() {
    imageEditing = null;
    imageForm = { template: '', display_name: '', image: '', description: '', is_default: false };
    imageDialogOpen = true;
  }
  function openEditImage(i: Image) {
    imageEditing = i.template;
    imageForm = {
      template: i.template,
      display_name: i.display_name,
      image: i.image,
      description: i.description,
      is_default: i.is_default
    };
    imageDialogOpen = true;
  }
  async function saveImage() {
    imageSaving = true;
    const tid = toast.loading('Saving template…');
    try {
      const payload = {
        display_name: imageForm.display_name,
        image: imageForm.image,
        description: imageForm.description,
        is_default: imageForm.is_default
      };
      if (imageEditing) {
        await api.put(`/admin/images/${imageEditing}`, payload);
      } else {
        await api.post('/admin/images', { template: imageForm.template, ...payload });
      }
      toast.success('Template saved', { id: tid });
      imageDialogOpen = false;
      await invalidateAll();
    } catch (e) {
      toast.error('Could not save template', { id: tid, description: e instanceof ApiError ? e.message : '' });
    } finally {
      imageSaving = false;
    }
  }
  async function deactivateImage(i: Image) {
    if (!confirm(`Deactivate template "${i.template}"? It will be hidden from new VM launches.`)) return;
    imageBusy = i.template;
    const tid = toast.loading('Deactivating…');
    try {
      await api.delete(`/admin/images/${i.template}`);
      toast.success('Template deactivated', { id: tid });
      await invalidateAll();
    } catch (e) {
      toast.error('Could not deactivate', { id: tid, description: e instanceof ApiError ? e.message : '' });
    } finally {
      imageBusy = null;
    }
  }
  async function reactivateImage(i: Image) {
    imageBusy = i.template;
    const tid = toast.loading('Reactivating…');
    try {
      await api.put(`/admin/images/${i.template}`, { is_active: true });
      toast.success('Template reactivated', { id: tid });
      await invalidateAll();
    } catch (e) {
      toast.error('Could not reactivate', { id: tid, description: e instanceof ApiError ? e.message : '' });
    } finally {
      imageBusy = null;
    }
  }
  const imageFormValid = $derived(
    (imageEditing !== null || /^[a-z0-9][a-z0-9-]*$/.test(imageForm.template)) &&
      imageForm.display_name.trim().length > 0 &&
      imageForm.image.trim().length > 0
  );

  const planFormValid = $derived(
    (planEditing !== null || /^[a-z0-9][a-z0-9-]*$/.test(planForm.name)) &&
      planForm.display_name.trim().length > 0 &&
      String(planForm.cpu).trim().length > 0 &&
      String(planForm.memory).trim().length > 0 &&
      String(planForm.disk).trim().length > 0 &&
      Number(planForm.credits_per_hour) > 0 &&
      Number(planForm.workspace_gb) > 0
  );

  // Course catalogue (admin CRUD). Admins create the course and assign the
  // owning professor; that professor manages the roster from /teacher.
  type CourseForm = { code: string; name: string; description: string; professor_id: string };
  let courseDialogOpen = $state(false);
  let courseEditing = $state<string | null>(null); // course id when editing, null = creating
  let courseSaving = $state(false);
  let courseBusy = $state<string | null>(null);
  let courseForm = $state<CourseForm>({ code: '', name: '', description: '', professor_id: '' });

  // Only professors can own a course — mirrors the backend's 400 guard.
  const professors = $derived(data.users.filter((u) => u.role === 'professor'));

  function openCreateCourse() {
    courseEditing = null;
    courseForm = { code: '', name: '', description: '', professor_id: professors[0]?.id ?? '' };
    courseDialogOpen = true;
  }
  function openEditCourse(c: Course) {
    courseEditing = c.id;
    courseForm = {
      code: c.code,
      name: c.name,
      description: c.description,
      professor_id: c.professor_id
    };
    courseDialogOpen = true;
  }
  async function saveCourse() {
    courseSaving = true;
    const tid = toast.loading('Saving course…');
    try {
      const payload = {
        name: courseForm.name,
        description: courseForm.description,
        professor_id: courseForm.professor_id
      };
      if (courseEditing) {
        await api.put(`/admin/courses/${courseEditing}`, payload);
      } else {
        await api.post('/admin/courses', { code: courseForm.code, ...payload });
      }
      toast.success('Course saved', { id: tid });
      courseDialogOpen = false;
      await invalidateAll();
    } catch (e) {
      toast.error('Could not save course', {
        id: tid,
        description: e instanceof ApiError ? e.message : ''
      });
    } finally {
      courseSaving = false;
    }
  }
  async function deactivateCourse(c: Course) {
    if (
      !confirm(
        `Deactivate course "${c.code}"?\nThe roster is preserved and existing allocations are untouched.`
      )
    )
      return;
    courseBusy = c.id;
    const tid = toast.loading('Deactivating…');
    try {
      await api.delete(`/admin/courses/${c.id}`);
      toast.success('Course deactivated', { id: tid });
      await invalidateAll();
    } catch (e) {
      toast.error('Could not deactivate', {
        id: tid,
        description: e instanceof ApiError ? e.message : ''
      });
    } finally {
      courseBusy = null;
    }
  }
  async function reactivateCourse(c: Course) {
    courseBusy = c.id;
    const tid = toast.loading('Reactivating…');
    try {
      await api.put(`/admin/courses/${c.id}`, { is_active: true });
      toast.success('Course reactivated', { id: tid });
      await invalidateAll();
    } catch (e) {
      toast.error('Could not reactivate', {
        id: tid,
        description: e instanceof ApiError ? e.message : ''
      });
    } finally {
      courseBusy = null;
    }
  }
  const courseFormValid = $derived(
    (courseEditing !== null || /^[A-Za-z0-9][A-Za-z0-9-]*$/.test(courseForm.code)) &&
      courseForm.name.trim().length > 0 &&
      courseForm.professor_id.trim().length > 0
  );

  // Roster dialog — the enrolled students for one course. Loaded lazily on open
  // (same shape as the per-user quota dialog).
  let rosterOpen = $state(false);
  let rosterCourse = $state<Course | null>(null);
  let rosterLoading = $state(false);
  let roster = $state<RosterMember[]>([]);
  let rosterBusy = $state<string | null>(null);
  let enrollId = $state('');

  // Students not already on this roster — the only valid enrolment candidates.
  const enrollCandidates = $derived(
    data.users.filter((u) => u.role === 'student' && !roster.some((r) => r.id === u.id))
  );

  async function loadRoster(courseId: string) {
    rosterLoading = true;
    try {
      roster = await api.get<RosterMember[]>(`/courses/${courseId}/roster`);
    } catch (e) {
      toast.error('Could not load roster', {
        description: e instanceof ApiError ? e.message : ''
      });
      roster = [];
    } finally {
      rosterLoading = false;
    }
  }
  async function openRoster(c: Course) {
    rosterCourse = c;
    rosterOpen = true;
    roster = [];
    enrollId = '';
    await loadRoster(c.id);
  }
  async function enrollStudent() {
    if (!rosterCourse || !enrollId) return;
    rosterBusy = enrollId;
    const tid = toast.loading('Enrolling…');
    try {
      await api.post(`/courses/${rosterCourse.id}/enrollments`, { user_id: enrollId });
      toast.success('Student enrolled', { id: tid });
      enrollId = '';
      await loadRoster(rosterCourse.id);
      await invalidateAll(); // refresh enrolled_count in the table behind the dialog
    } catch (e) {
      toast.error('Could not enroll', {
        id: tid,
        description: e instanceof ApiError ? e.message : ''
      });
    } finally {
      rosterBusy = null;
    }
  }
  async function unenrollStudent(member: RosterMember) {
    if (!rosterCourse) return;
    rosterBusy = member.id;
    const tid = toast.loading('Removing…');
    try {
      await api.delete(`/courses/${rosterCourse.id}/enrollments/${member.id}`);
      toast.success(`${member.name} removed`, { id: tid });
      await loadRoster(rosterCourse.id);
      await invalidateAll();
    } catch (e) {
      toast.error('Could not remove', {
        id: tid,
        description: e instanceof ApiError ? e.message : ''
      });
    } finally {
      rosterBusy = null;
    }
  }

  // Admin force-terminate any user's VM (FR-HC-20).
  let terminatingVm = $state<string | null>(null);
  async function forceTerminateVm(vm: { id: string; user_email?: string | null }) {
    if (
      !confirm(
        `Force-terminate VM ${vm.id.slice(0, 8)} (owner: ${vm.user_email ?? 'unknown'})?\nThis stops the VM immediately and cannot be undone.`
      )
    )
      return;
    terminatingVm = vm.id;
    const tid = toast.loading('Terminating VM…');
    try {
      await api.delete(`/pods/${vm.id}`);
      toast.success('VM terminated', { id: tid });
      await invalidateAll();
    } catch (e) {
      toast.error('Could not terminate VM', {
        id: tid,
        description: e instanceof ApiError ? e.message : ''
      });
    } finally {
      terminatingVm = null;
    }
  }

  // Issue triage (admin only): resolve with an optional reply shown to the reporter.
  let resolvingIssue = $state<string | null>(null);
  let issueResponses = $state<Record<string, string>>({});
  async function resolveIssue(id: string) {
    resolvingIssue = id;
    const tid = toast.loading('Resolving issue…');
    try {
      await api.post(`/issues/admin/${id}/resolve`, { response: issueResponses[id] || null });
      toast.success('Issue resolved', { id: tid });
      await invalidateAll();
    } catch (e) {
      toast.error('Could not resolve issue', {
        id: tid,
        description: e instanceof ApiError ? e.message : ''
      });
    } finally {
      resolvingIssue = null;
    }
  }

  let tab = $state('overview');
  let hydrated = $state(false);
  let userQuery = $state('');
  let vmQuery = $state('');

  // Role mutation state — kept local so the dropdown updates instantly
  // before invalidateAll() refreshes the list from the server.
  let users = $derived(data.users);
  let pendingRoleChange = $state<string | null>(null);

  onMount(() => {
    hydrated = true;
  });

  async function changeRole(u: AdminUser, newRole: string) {
    if (newRole === u.role) return;
    if (data.currentUserRole !== 'admin') return;
    if (u.id === data.currentUserId && newRole !== 'admin') {
      toast.error('You cannot demote yourself');
      return;
    }
    const previous = u.role;
    pendingRoleChange = u.id;
    u.role = newRole;
    const tid = toast.loading(`Changing role for ${u.email}…`);
    try {
      await api.patch(`/admin/users/${u.id}/role`, { role: newRole });
      toast.success(`${u.email} → ${newRole}`, { id: tid });
      await invalidateAll();
    } catch (e) {
      u.role = previous;
      const msg = e instanceof ApiError ? e.message : 'Role change failed';
      toast.error('Could not change role', { id: tid, description: msg });
    } finally {
      pendingRoleChange = null;
    }
  }

  // Credit allocation dialog state
  let allocOpen = $state(false);
  let allocUser = $state<AdminUser | null>(null);
  let allocAmount = $state(10);
  let allocDescription = $state('Manual allocation');
  let allocating = $state(false);

  function openAlloc(u: AdminUser) {
    allocUser = u;
    allocAmount = 10;
    allocDescription = `Allocation for ${u.name || u.email}`;
    allocOpen = true;
  }

  async function allocate() {
    if (!allocUser || allocating) return;
    if (!Number.isFinite(allocAmount) || allocAmount <= 0) {
      toast.error('Amount must be a positive number');
      return;
    }
    allocating = true;
    const id = toast.loading(
      `Allocating ${allocAmount} credit${allocAmount === 1 ? '' : 's'}…`
    );
    try {
      await api.post('/credits/allocate', {
        user_id: allocUser.id,
        amount: allocAmount,
        description: allocDescription || 'allocation'
      });
      toast.success(`Allocated ${allocAmount.toFixed(2)} credits`, {
        id,
        description: `${allocUser.name || allocUser.email}`
      });
      allocOpen = false;
      await invalidateAll();
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : 'Allocation failed';
      toast.error('Could not allocate credits', { id, description: msg });
    } finally {
      allocating = false;
    }
  }

  // Per-user quota dialog.
  let quotaOpen = $state(false);
  let quotaUser = $state<AdminUser | null>(null);
  let quotaLoading = $state(false);
  let quotaSaving = $state(false);
  let quotaMaxVms = $state<number | string>(3);
  let quotaMaxGb = $state<number | string>(100);
  let quotaIsCustom = $state(false);

  async function openQuota(u: AdminUser) {
    quotaUser = u;
    quotaOpen = true;
    quotaLoading = true;
    try {
      const q = await api.get<{ max_concurrent_vms: number; max_workspace_gb: number; is_custom: boolean }>(
        `/admin/users/${u.id}/quota`
      );
      quotaMaxVms = q.max_concurrent_vms;
      quotaMaxGb = q.max_workspace_gb;
      quotaIsCustom = q.is_custom;
    } catch (e) {
      toast.error('Could not load quota', { description: e instanceof ApiError ? e.message : '' });
    } finally {
      quotaLoading = false;
    }
  }

  async function saveQuota() {
    if (!quotaUser) return;
    quotaSaving = true;
    const tid = toast.loading('Saving quota…');
    try {
      await api.put(`/admin/users/${quotaUser.id}/quota`, {
        max_concurrent_vms: Number(quotaMaxVms),
        max_workspace_gb: Number(quotaMaxGb)
      });
      toast.success('Quota updated', { id: tid });
      quotaOpen = false;
    } catch (e) {
      toast.error('Could not save quota', { id: tid, description: e instanceof ApiError ? e.message : '' });
    } finally {
      quotaSaving = false;
    }
  }

  async function resetQuota() {
    if (!quotaUser) return;
    quotaSaving = true;
    const tid = toast.loading('Resetting to default…');
    try {
      const q = await api.delete<{ max_concurrent_vms: number; max_workspace_gb: number; is_custom: boolean }>(
        `/admin/users/${quotaUser.id}/quota`
      );
      quotaMaxVms = q.max_concurrent_vms;
      quotaMaxGb = q.max_workspace_gb;
      quotaIsCustom = q.is_custom;
      toast.success('Reverted to default quota', { id: tid });
    } catch (e) {
      toast.error('Could not reset quota', { id: tid, description: e instanceof ApiError ? e.message : '' });
    } finally {
      quotaSaving = false;
    }
  }

  function memoryToGb(s: string | null | undefined): number | null {
    if (!s) return null;
    const m = s.match(/^(\d+)(Ki|Mi|Gi)?$/);
    if (!m) return null;
    const v = parseInt(m[1]);
    if (m[2] === 'Ki') return v / (1024 * 1024);
    if (m[2] === 'Mi') return v / 1024;
    if (m[2] === 'Gi') return v;
    return v / (1024 * 1024 * 1024);
  }

  function fmtMem(s: string | null | undefined): string {
    const gb = memoryToGb(s);
    if (gb === null) return s ?? '-';
    return `${gb.toFixed(1)} GB`;
  }

  const filteredUsers = $derived(
    userQuery
      ? users.filter(
          (u) =>
            u.email.toLowerCase().includes(userQuery.toLowerCase()) ||
            u.name.toLowerCase().includes(userQuery.toLowerCase()) ||
            u.role.toLowerCase().includes(userQuery.toLowerCase())
        )
      : users
  );

  const filteredVms = $derived(
    vmQuery
      ? data.activeVms.filter(
          (v) =>
            v.id.toLowerCase().includes(vmQuery.toLowerCase()) ||
            (v.user_email ?? '').toLowerCase().includes(vmQuery.toLowerCase()) ||
            (v.user_name ?? '').toLowerCase().includes(vmQuery.toLowerCase())
        )
      : data.activeVms
  );

  // ---- Pagination: cap table height; 20 rows per page, each with inner scroll.
  const ADMIN_PER_PAGE = 20;
  let usersPage = $state(1);
  let vmsPage = $state(1);
  let nodesPage = $state(1);
  let auditPage = $state(1);

  // Reset to page 1 whenever a search narrows the result set.
  $effect(() => {
    userQuery; // track
    usersPage = 1;
  });
  $effect(() => {
    vmQuery; // track
    vmsPage = 1;
  });

  const pagedUsers = $derived(
    filteredUsers.slice((usersPage - 1) * ADMIN_PER_PAGE, usersPage * ADMIN_PER_PAGE)
  );
  const pagedVms = $derived(
    filteredVms.slice((vmsPage - 1) * ADMIN_PER_PAGE, vmsPage * ADMIN_PER_PAGE)
  );
  // Node status filter — nodes report a boolean `ready`, so the meaningful
  // statuses are Ready / Not ready (plus "All").
  const nodeStatusOptions = [
    { value: 'all', label: 'All' },
    { value: 'ready', label: 'Ready' },
    { value: 'notready', label: 'Not ready' }
  ] as const;
  let nodeStatus = $state<(typeof nodeStatusOptions)[number]['value']>('all');

  $effect(() => {
    nodeStatus; // track
    nodesPage = 1;
  });

  const filteredNodes = $derived(
    nodeStatus === 'all'
      ? data.nodes
      : data.nodes.filter((n) => (nodeStatus === 'ready' ? n.ready : !n.ready))
  );

  const pagedNodes = $derived(
    filteredNodes.slice((nodesPage - 1) * ADMIN_PER_PAGE, nodesPage * ADMIN_PER_PAGE)
  );
  const pagedAudit = $derived(
    data.auditLogs.slice((auditPage - 1) * ADMIN_PER_PAGE, auditPage * ADMIN_PER_PAGE)
  );

  // Latest events for the Overview timeline.
  const recentActivity = $derived(data.auditLogs.slice(0, 5));

  // Role identity — icon + modest tint, color-coded and consistent everywhere.
  const roleMeta: Record<string, { icon: typeof Shield; tint: string }> = {
    admin: { icon: Shield, tint: 'bg-primary/10 text-primary ring-primary/20' },
    professor: { icon: GraduationCap, tint: 'bg-info/10 text-info ring-info/20' },
    student: { icon: User, tint: 'bg-muted text-muted-foreground ring-border' }
  };
  const ROLES = ['student', 'professor', 'admin'] as const;

  // Tinted chip (bg + text) for an HTTP status code.
  function statusChipClass(code: number | null): string {
    if (!code) return 'bg-muted text-muted-foreground';
    if (code >= 500) return 'bg-destructive/10 text-destructive ring-destructive/20';
    if (code >= 400) return 'bg-warning/10 text-warning ring-warning/20';
    if (code >= 200 && code < 300) return 'bg-success/10 text-success ring-success/20';
    return 'bg-info/10 text-info ring-info/20';
  }

  // Split an audit action like "post:/auth/refresh" into a method + path.
  function parseAction(action: string): { method: string | null; path: string } {
    const i = action.indexOf(':');
    if (i > 0 && i < 8) {
      return { method: action.slice(0, i).toUpperCase(), path: action.slice(i + 1) };
    }
    return { method: null, path: action };
  }

  // Color a REST method (and the synthetic "EVENT" tag) consistently.
  function methodTone(method: string | null): string {
    switch (method) {
      case 'GET':
        return 'bg-info/10 text-info ring-info/20';
      case 'POST':
        return 'bg-success/10 text-success ring-success/20';
      case 'PUT':
      case 'PATCH':
        return 'bg-warning/10 text-warning ring-warning/20';
      case 'DELETE':
        return 'bg-destructive/10 text-destructive ring-destructive/20';
      default:
        return 'bg-primary/10 text-primary ring-primary/20';
    }
  }

  // Reserved fraction (capacity − allocatable) for a node resource, 0–100.
  function reservedPct(capacity: number, allocatable: number): number {
    if (!capacity) return 0;
    return Math.max(0, Math.min(100, ((capacity - allocatable) / capacity) * 100));
  }

  // Small icon-chip tone for the activity feed, derived from the status code.
  function activityTone(code: number | null | undefined): {
    dot: string;
    chip: string;
  } {
    if (code && code >= 500)
      return { dot: 'bg-destructive', chip: 'bg-destructive/10 text-destructive' };
    if (code && code >= 400)
      return { dot: 'bg-warning', chip: 'bg-warning/10 text-warning' };
    return { dot: 'bg-success', chip: 'bg-success/10 text-success' };
  }
</script>

<!-- Color-coded role pill — static, or interactive (trigger) inside a dropdown. -->
{#snippet roleChip(role: string, interactive: boolean, pending: boolean)}
  {@const m = roleMeta[role] ?? roleMeta.student}
  {@const RoleIcon = m.icon}
  <span
    class={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold capitalize ring-1 ring-inset ${m.tint} ${interactive ? 'transition-shadow hover:shadow-sm' : ''}`}
  >
    <RoleIcon class="size-3.5 shrink-0" />
    {role}
    {#if pending}
      <Spinner class="size-3 shrink-0 opacity-70" />
    {:else if interactive}
      <ChevronDown class="size-3 shrink-0 opacity-60" />
    {/if}
  </span>
{/snippet}

<div class="space-y-8" data-admin-hydrated={hydrated}>
  <PageTitle
    title="Admin"
    eyebrow="Admin console"
    eyebrowIcon={ShieldAlert}
    description="Platform overview, user management, and audit trail."
  />

  <!-- Stats -->
  <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
    <StatCard
      compact
      label="Total users"
      value={data.stats.total_users}
      icon={Users}
      tone="primary"
      class="animate-fade-up"
    />
    <StatCard
      compact
      label="Active VMs"
      value={data.stats.active_vms}
      icon={Server}
      tone="success"
      class="animate-fade-up [animation-delay:70ms]"
    />
    <StatCard
      compact
      label="VMs all-time"
      value={data.stats.total_vms_created}
      icon={Database}
      tone="info"
      class="animate-fade-up [animation-delay:140ms]"
    />
    <StatCard
      compact
      label="Compute nodes"
      value={data.nodes.length}
      sub={`${data.nodes.filter((n) => n.ready).length} ready`}
      icon={Activity}
      tone="default"
      class="animate-fade-up [animation-delay:210ms]"
    />
  </div>

  <!-- Tabs -->
  <Tabs.Root bind:value={tab}>
    <Tabs.List
      class="max-w-full justify-start overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      <Tabs.Trigger value="overview"><Activity /> Overview</Tabs.Trigger>
      <Tabs.Trigger value="users"><Users /> Users</Tabs.Trigger>
      {#if data.currentUserRole === 'admin'}
        <Tabs.Trigger value="requests">
          <GraduationCap /> Requests
          {#if data.teacherRequests.length}
            <span class="ml-1 inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-warning/15 px-1.5 text-[11px] font-semibold text-warning">
              {data.teacherRequests.length}
            </span>
          {/if}
        </Tabs.Trigger>
      {/if}
      <Tabs.Trigger value="vms"><Server /> Active VMs</Tabs.Trigger>
      <Tabs.Trigger value="nodes"><HardDrive /> Nodes</Tabs.Trigger>
      <Tabs.Trigger value="plans"><Coins /> Plans</Tabs.Trigger>
      <Tabs.Trigger value="images"><Database /> Images</Tabs.Trigger>
      <Tabs.Trigger value="courses"><BookOpen /> Courses</Tabs.Trigger>
      <Tabs.Trigger value="audit"><ScrollText /> Audit log</Tabs.Trigger>
      <Tabs.Trigger value="issues"><Inbox /> Issues</Tabs.Trigger>
    </Tabs.List>

    <!-- Overview -->
    <Tabs.Content value="overview" class="mt-5">
      <div class="grid gap-4 lg:grid-cols-2">
        <!-- Recent activity — vertical timeline -->
        <Card class="animate-fade-up">
          <CardContent class="space-y-3 p-4">
            <SectionHeader title="Recent activity" icon={Activity}>
              {#snippet action()}
                <button
                  type="button"
                  onclick={() => (tab = 'audit')}
                  class="group inline-flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
                >
                  View all
                  <ArrowRight class="size-3 transition-transform group-hover:translate-x-0.5" />
                </button>
              {/snippet}
            </SectionHeader>
            <Separator />
            {#if recentActivity.length === 0}
              <div class="flex flex-col items-center gap-2 py-10 text-center">
                <span class="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
                  <ScrollText class="size-5" />
                </span>
                <p class="text-sm text-muted-foreground">No events yet.</p>
              </div>
            {:else}
              <ol class="pt-1">
                {#each recentActivity as log, i (log.id)}
                  {@const tone = activityTone(log.status_code)}
                  {@const last = i === recentActivity.length - 1}
                  <li class="group flex gap-3.5">
                    <!-- rail: bead + connector -->
                    <div class="flex flex-col items-center">
                      <span
                        class={`relative z-10 mt-0.5 size-3 rounded-full shadow-sm ring-4 ring-card transition-transform duration-200 group-hover:scale-125 ${tone.dot}`}
                      ></span>
                      {#if !last}
                        <span class="mt-0.5 w-px flex-1 bg-gradient-to-b from-border to-border/30"></span>
                      {/if}
                    </div>
                    <!-- content -->
                    <div class={`min-w-0 flex-1 ${last ? '' : 'pb-4'}`}>
                      <div class="flex items-start justify-between gap-2">
                        <span class="truncate text-sm font-medium leading-tight">{log.action}</span>
                        <span class="shrink-0 text-xs tabular-nums text-muted-foreground">
                          {relTime(log.created_at)}
                        </span>
                      </div>
                      <div class="mt-1 flex flex-wrap items-center gap-1.5">
                        {#if log.resource_type}
                          <span class="truncate text-xs text-muted-foreground">
                            {log.resource_type}{log.resource_id ? ` · ${shortId(log.resource_id, 8)}` : ''}
                          </span>
                        {/if}
                        {#if log.status_code}
                          <span
                            class={`inline-flex items-center rounded-full px-1.5 py-0 font-mono text-[10px] font-semibold ${tone.chip}`}
                          >
                            {log.status_code}
                          </span>
                        {/if}
                      </div>
                    </div>
                  </li>
                {/each}
              </ol>
            {/if}
          </CardContent>
        </Card>

        <!-- Cluster pressure — radial gauges -->
        <Card class="animate-fade-up [animation-delay:80ms]">
          <CardContent class="space-y-3 p-4">
            <SectionHeader title="Cluster pressure" icon={Server} />
            <Separator />
            {#if data.nodes.length === 0}
              <div class="flex flex-col items-center gap-2 py-10 text-center">
                <span class="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
                  <HardDrive class="size-5" />
                </span>
                <p class="text-sm text-muted-foreground">No nodes reporting.</p>
              </div>
            {:else}
              {@const totalCpu = data.nodes.reduce((a, n) => a + (parseFloat(n.cpu_capacity) || 0), 0)}
              {@const allocCpu = data.nodes.reduce((a, n) => a + (parseFloat(n.cpu_allocatable) || 0), 0)}
              {@const totalMem = data.nodes.reduce((a, n) => a + (memoryToGb(n.memory_capacity) || 0), 0)}
              {@const allocMem = data.nodes.reduce((a, n) => a + (memoryToGb(n.memory_allocatable) || 0), 0)}
              {@const cpuUsedPct = totalCpu ? ((totalCpu - allocCpu) / totalCpu) * 100 : 0}
              {@const memUsedPct = totalMem ? ((totalMem - allocMem) / totalMem) * 100 : 0}

              {#snippet gauge(g: {
                id: string;
                label: string;
                icon: unknown;
                tint: string;
                pct: number;
                detail: string;
                from: string;
                to: string;
              })}
                {@const Icon = g.icon as unknown as typeof SvelteComponent}
                <div class="flex flex-col items-center gap-2.5 rounded-xl border border-border/60 bg-muted/20 p-3">
                  <div class="relative size-24">
                    <svg viewBox="0 0 36 36" class="size-24 -rotate-90">
                      <circle cx="18" cy="18" r="15.9155" fill="none" class="stroke-muted" stroke-width="3.4" />
                      <circle
                        cx="18"
                        cy="18"
                        r="15.9155"
                        fill="none"
                        stroke={`url(#${g.id})`}
                        stroke-width="3.4"
                        stroke-linecap="round"
                        stroke-dasharray={`${Math.max(0, Math.min(100, g.pct))} 100`}
                        class="transition-[stroke-dasharray] duration-700 ease-out"
                      />
                      <defs>
                        <linearGradient id={g.id} x1="0" y1="0" x2="1" y2="1">
                          <stop offset="0%" class={g.from} />
                          <stop offset="100%" class={g.to} />
                        </linearGradient>
                      </defs>
                    </svg>
                    <div class="absolute inset-0 flex flex-col items-center justify-center">
                      <span class="text-xl font-bold leading-none tabular-nums">{g.pct.toFixed(0)}%</span>
                      <span class="mt-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                        reserved
                      </span>
                    </div>
                  </div>
                  <div class="text-center">
                    <div class="flex items-center justify-center gap-1.5 text-sm font-semibold">
                      <Icon class={`size-3.5 ${g.tint}`} /> {g.label}
                    </div>
                    <div class="mt-0.5 text-[11px] text-muted-foreground">{g.detail}</div>
                  </div>
                </div>
              {/snippet}

              <div class="grid grid-cols-2 gap-3">
                {@render gauge({
                  id: 'gaugeCpu',
                  label: 'CPU',
                  icon: Cpu,
                  tint: 'text-primary',
                  pct: cpuUsedPct,
                  detail: `${(totalCpu - allocCpu).toFixed(1)} / ${totalCpu.toFixed(1)} cores`,
                  from: '[stop-color:hsl(var(--primary))]',
                  to: '[stop-color:hsl(var(--info))]'
                })}
                {@render gauge({
                  id: 'gaugeMem',
                  label: 'Memory',
                  icon: MemoryStick,
                  tint: 'text-info',
                  pct: memUsedPct,
                  detail: `${(totalMem - allocMem).toFixed(1)} / ${totalMem.toFixed(1)} GB`,
                  from: '[stop-color:hsl(var(--info))]',
                  to: '[stop-color:hsl(var(--primary))]'
                })}
              </div>

              <div class="rounded-xl border border-border/60 bg-muted/20 px-3.5 py-2.5">
                <div class="flex items-center justify-between text-sm">
                  <span class="flex items-center gap-2 font-medium">
                    <span
                      class={`size-2 animate-pulse rounded-full ${data.nodes.every((n) => n.ready) ? 'bg-success' : 'bg-warning'}`}
                    ></span>
                    Nodes ready
                  </span>
                  <span class="font-semibold tabular-nums">
                    {data.nodes.filter((n) => n.ready).length} / {data.nodes.length}
                  </span>
                </div>
                <div class="mt-2 flex flex-wrap gap-1">
                  {#each data.nodes as n (n.name)}
                    <span
                      class={`h-1.5 min-w-[0.5rem] flex-1 rounded-full ${n.ready ? 'bg-success/70' : 'bg-destructive/70'}`}
                      title={n.name}
                    ></span>
                  {/each}
                </div>
              </div>
            {/if}
          </CardContent>
        </Card>
      </div>
    </Tabs.Content>

    <!-- Users -->
    <Tabs.Content value="users" class="mt-5">
      <div class="animate-fade-up space-y-3">
        <SectionHeader title="Users" icon={Users}>
          {#snippet badge()}
            <Badge variant="muted">{data.users.length} registered</Badge>
          {/snippet}
          {#snippet action()}
            <div class="relative">
              <Search
                class="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
              />
              <Input
                type="search"
                placeholder="Search users…"
                bind:value={userQuery}
                class="h-9 w-40 pl-8 sm:w-64"
              />
            </div>
          {/snippet}
        </SectionHeader>

        <Card class="overflow-hidden">
          <Table.Root class="table-fixed" containerClass="[scrollbar-gutter:stable]">
            <Table.Header class="bg-muted/40">
              <Table.Row class="hover:bg-transparent">
                <Table.Head>User</Table.Head>
                <Table.Head class="hidden w-56 md:table-cell">Email</Table.Head>
                <Table.Head class="w-36">Role</Table.Head>
                <Table.Head class="hidden w-28 sm:table-cell">Joined</Table.Head>
                <Table.Head class="w-32 text-right">Actions</Table.Head>
              </Table.Row>
            </Table.Header>
          </Table.Root>
          <Table.Root class="table-fixed" containerClass="max-h-[34rem] [scrollbar-gutter:stable]">
            <Table.Body>
              {#each pagedUsers as u (u.id)}
                <Table.Row class="group">
                  <Table.Cell>
                    <div class="flex items-center gap-2.5">
                      <Avatar name={u.name || u.email} class="size-8 shrink-0 ring-1 ring-border/60" />
                      <div class="min-w-0">
                        <div class="truncate font-medium">{u.name || '—'}</div>
                        <div class="truncate text-xs text-muted-foreground md:hidden">{u.email}</div>
                      </div>
                    </div>
                  </Table.Cell>
                  <Table.Cell class="hidden w-56 truncate text-muted-foreground md:table-cell">{u.email}</Table.Cell>
                  <Table.Cell class="w-36">
                    {#if data.currentUserRole === 'admin' && u.id !== data.currentUserId}
                      <DropdownMenu.Root>
                        <DropdownMenu.Trigger
                          disabled={pendingRoleChange === u.id}
                          class="rounded-full outline-none transition focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
                          aria-label={`Change role for ${u.email}`}
                        >
                          {@render roleChip(u.role, true, pendingRoleChange === u.id)}
                        </DropdownMenu.Trigger>
                        <DropdownMenu.Content align="start" class="min-w-[11rem]">
                          <DropdownMenu.Label>Change role</DropdownMenu.Label>
                          {#each ROLES as r (r)}
                            {@const m = roleMeta[r]}
                            {@const RoleIcon = m.icon}
                            <DropdownMenu.Item onclick={() => changeRole(u, r)}>
                              <span
                                class={`flex size-5 items-center justify-center rounded-md ring-1 ring-inset ${m.tint}`}
                              >
                                <RoleIcon class="size-3" />
                              </span>
                              <span class="capitalize">{r}</span>
                              {#if u.role === r}
                                <Check class="ml-auto size-3.5 text-primary" />
                              {/if}
                            </DropdownMenu.Item>
                          {/each}
                        </DropdownMenu.Content>
                      </DropdownMenu.Root>
                    {:else}
                      {@render roleChip(u.role, false, false)}
                    {/if}
                  </Table.Cell>
                  <Table.Cell class="hidden w-28 text-muted-foreground sm:table-cell">
                    {u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}
                  </Table.Cell>
                  <Table.Cell class="w-32 text-right">
                    <div class="flex items-center justify-end gap-1">
                      <Tooltip content="Edit resource quota">
                        {#snippet children(props)}
                        <Button
                          {...props}
                          variant="ghost"
                          size="sm"
                          class="opacity-70 transition-opacity group-hover:opacity-100"
                          onclick={() => openQuota(u)}
                          aria-label={`Quota for ${u.email}`}
                        >
                          <Gauge class="size-3.5" />
                        </Button>
                        {/snippet}
                      </Tooltip>
                      <Tooltip content="Allocate credits to this user">
                        {#snippet children(props)}
                        <Button
                          {...props}
                          variant="outline"
                          size="sm"
                          class="opacity-70 transition-opacity group-hover:opacity-100"
                          onclick={() => openAlloc(u)}
                        >
                          <Coins class="size-3.5" /> Allocate
                        </Button>
                        {/snippet}
                      </Tooltip>
                    </div>

                  </Table.Cell>
                </Table.Row>
              {/each}
              {#if filteredUsers.length === 0}
                <Table.Row class="hover:bg-transparent">
                  <Table.Cell colspan={5} class="py-10 text-center text-sm text-muted-foreground">
                    No users match your search.
                  </Table.Cell>
                </Table.Row>
              {/if}
            </Table.Body>
          </Table.Root>
          <div class="border-t border-border bg-muted/20 px-4 py-3">
            <Pagination
              count={filteredUsers.length}
              perPage={ADMIN_PER_PAGE}
              bind:page={usersPage}
              itemLabel="user"
            />
          </div>
        </Card>
      </div>
    </Tabs.Content>

    <!-- Teacher requests -->
    {#if data.currentUserRole === 'admin'}
      <Tabs.Content value="requests" class="mt-5">
        <div class="animate-fade-up space-y-3">
          <SectionHeader title="Teacher requests" icon={GraduationCap}>
            {#snippet badge()}
              <Badge variant="muted">{data.teacherRequests.length} pending</Badge>
            {/snippet}
          </SectionHeader>
          <Card class="overflow-hidden">
            <Table.Root class="table-fixed">
              <Table.Header class="bg-muted/40">
                <Table.Row class="hover:bg-transparent">
                  <Table.Head>User</Table.Head>
                  <Table.Head class="hidden w-56 md:table-cell">Email</Table.Head>
                  <Table.Head class="hidden w-28 sm:table-cell">Requested</Table.Head>
                  <Table.Head class="w-44 text-right">Decision</Table.Head>
                </Table.Row>
              </Table.Header>
              <Table.Body>
                {#each data.teacherRequests as r (r.id)}
                  <Table.Row class="group">
                    <Table.Cell>
                      <div class="flex items-center gap-2.5">
                        <Avatar name={r.name || r.email} class="size-8 shrink-0 ring-1 ring-border/60" />
                        <div class="min-w-0">
                          <div class="truncate font-medium">{r.name || '—'}</div>
                          <div class="truncate text-xs text-muted-foreground md:hidden">{r.email}</div>
                        </div>
                      </div>
                    </Table.Cell>
                    <Table.Cell class="hidden w-56 truncate text-muted-foreground md:table-cell">{r.email}</Table.Cell>
                    <Table.Cell class="hidden w-28 text-muted-foreground sm:table-cell">
                      {r.created_at ? new Date(r.created_at).toLocaleDateString() : '—'}
                    </Table.Cell>
                    <Table.Cell class="w-44 text-right">
                      <div class="flex items-center justify-end gap-2">
                        <Button variant="outline" size="sm" disabled={processingReq === r.id} onclick={() => rejectTeacher(r)}>
                          <X class="size-3.5" /> Reject
                        </Button>
                        <Button size="sm" disabled={processingReq === r.id} onclick={() => approveTeacher(r)}>
                          {#if processingReq === r.id}<Spinner class="size-3.5" />{:else}<Check class="size-3.5" />{/if} Approve
                        </Button>
                      </div>
                    </Table.Cell>
                  </Table.Row>
                {/each}
                {#if data.teacherRequests.length === 0}
                  <Table.Row class="hover:bg-transparent">
                    <Table.Cell colspan={4} class="py-12 text-center text-sm text-muted-foreground">
                      <GraduationCap class="mx-auto mb-2 size-5 opacity-50" />
                      No pending teacher requests.
                    </Table.Cell>
                  </Table.Row>
                {/if}
              </Table.Body>
            </Table.Root>
          </Card>
        </div>
      </Tabs.Content>
    {/if}

    <!-- Active VMs -->
    <Tabs.Content value="vms" class="mt-5">
      <div class="animate-fade-up space-y-3">
        <SectionHeader title="Active VMs" icon={Server}>
          {#snippet badge()}
            <Badge variant="muted">{data.activeVms.length} running</Badge>
          {/snippet}
          {#snippet action()}
            <div class="relative">
              <Search
                class="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
              />
              <Input
                type="search"
                placeholder="Search VMs or owners…"
                bind:value={vmQuery}
                class="h-9 w-40 pl-8 sm:w-64"
              />
            </div>
          {/snippet}
        </SectionHeader>

        <Card class="overflow-hidden">
          <Table.Root class="table-fixed" containerClass="[scrollbar-gutter:stable]">
            <Table.Header class="bg-muted/40">
              <Table.Row class="hover:bg-transparent">
                <Table.Head class="w-40">VM</Table.Head>
                <Table.Head>Owner</Table.Head>
                <Table.Head class="hidden w-24 sm:table-cell">Plan</Table.Head>
                <Table.Head class="hidden w-44 lg:table-cell">Resources</Table.Head>
                <Table.Head class="w-32">State</Table.Head>
                <Table.Head class="w-24 text-right">Started</Table.Head>
                <Table.Head class="w-24 text-right">Actions</Table.Head>
              </Table.Row>
            </Table.Header>
          </Table.Root>
          <Table.Root class="table-fixed" containerClass="max-h-[34rem] [scrollbar-gutter:stable]">
            <Table.Body>
              {#each pagedVms as vm (vm.id)}
                <Table.Row class="group">
                  <Table.Cell class="w-40">
                    <div class="flex items-center gap-2.5">
                      <span
                        class="flex size-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-primary/15 to-info/15 text-primary ring-1 ring-inset ring-primary/10 transition-transform group-hover:scale-105"
                      >
                        <Server class="size-4" />
                      </span>
                      <span class="truncate font-mono text-xs font-medium">{shortId(vm.id, 8)}</span>
                    </div>
                  </Table.Cell>
                  <Table.Cell>
                    <div class="flex items-center gap-2">
                      <Avatar name={vm.user_name || vm.user_email} class="size-7 shrink-0 ring-1 ring-border/60" />
                      <div class="min-w-0">
                        <div class="truncate font-medium">{vm.user_name ?? '—'}</div>
                        <div class="truncate text-xs text-muted-foreground">
                          {vm.user_email ?? ''}
                        </div>
                      </div>
                    </div>
                  </Table.Cell>
                  <Table.Cell class="hidden w-24 sm:table-cell">
                    <span
                      class="inline-flex items-center rounded-md border border-border bg-muted/50 px-2 py-0.5 text-xs font-medium capitalize"
                    >
                      {vm.plan}
                    </span>
                  </Table.Cell>
                  <Table.Cell class="hidden w-44 lg:table-cell">
                    <div class="flex items-center gap-1.5 text-[11px] font-medium">
                      <span class="inline-flex items-center gap-1 rounded-md bg-muted/60 px-1.5 py-0.5">
                        <Cpu class="size-3 text-primary" />
                        {vm.cpu ?? '—'}
                      </span>
                      <span class="inline-flex items-center gap-1 rounded-md bg-muted/60 px-1.5 py-0.5">
                        <MemoryStick class="size-3 text-info" />
                        {vm.memory ?? '—'}
                      </span>
                    </div>
                  </Table.Cell>
                  <Table.Cell class="w-32">
                    <StatusBadge state={vm.state} />
                  </Table.Cell>
                  <Table.Cell class="w-24 text-right text-xs text-muted-foreground">
                    {relTime(vm.started_at)}
                  </Table.Cell>
                  <Table.Cell class="w-24 text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      class="text-muted-foreground hover:text-destructive"
                      title="Force-terminate this VM"
                      disabled={terminatingVm === vm.id || vm.state === 'terminated'}
                      onclick={() => forceTerminateVm(vm)}
                    >
                      {#if terminatingVm === vm.id}
                        <Spinner class="size-4" />
                      {:else}
                        <Power class="size-4" />
                      {/if}
                    </Button>
                  </Table.Cell>
                </Table.Row>
              {/each}
              {#if filteredVms.length === 0}
                <Table.Row class="hover:bg-transparent">
                  <Table.Cell colspan={7} class="py-12 text-center text-sm text-muted-foreground">
                    <Server class="mx-auto mb-2 size-5 opacity-50" />
                    No active VMs.
                  </Table.Cell>
                </Table.Row>
              {/if}
            </Table.Body>
          </Table.Root>
          <div class="border-t border-border bg-muted/20 px-4 py-3">
            <Pagination
              count={filteredVms.length}
              perPage={ADMIN_PER_PAGE}
              bind:page={vmsPage}
              itemLabel="VM"
            />
          </div>
        </Card>
      </div>
    </Tabs.Content>

    <!-- Nodes -->
    <Tabs.Content value="nodes" class="mt-5">
      <div class="animate-fade-up space-y-3">
        <SectionHeader title="Compute nodes" icon={HardDrive}>
          {#snippet action()}
            <div class="inline-flex items-center gap-0.5 rounded-lg border border-border bg-muted/40 p-0.5">
              {#each nodeStatusOptions as opt (opt.value)}
                <button
                  type="button"
                  onclick={() => (nodeStatus = opt.value)}
                  class={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                    nodeStatus === opt.value
                      ? 'bg-card text-foreground shadow-sm ring-1 ring-border/50'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {opt.label}
                </button>
              {/each}
            </div>
          {/snippet}
        </SectionHeader>
        <Card class="overflow-hidden">
          <Table.Root class="table-fixed" containerClass="[scrollbar-gutter:stable]">
            <Table.Header class="bg-muted/40">
              <Table.Row class="hover:bg-transparent">
                <Table.Head>Node</Table.Head>
                <Table.Head class="w-32">Status</Table.Head>
                <Table.Head class="hidden w-40 sm:table-cell">CPU</Table.Head>
                <Table.Head class="hidden w-44 sm:table-cell">Memory</Table.Head>
                <Table.Head class="w-20 text-right">Pods</Table.Head>
              </Table.Row>
            </Table.Header>
          </Table.Root>
          <Table.Root class="table-fixed" containerClass="max-h-[34rem] [scrollbar-gutter:stable]">
            <Table.Body>
              {#each pagedNodes as n (n.name)}
                {@const cpuPct = reservedPct(parseFloat(n.cpu_capacity) || 0, parseFloat(n.cpu_allocatable) || 0)}
                {@const memPct = reservedPct(memoryToGb(n.memory_capacity) || 0, memoryToGb(n.memory_allocatable) || 0)}
                <Table.Row class="group">
                  <Table.Cell>
                    <div class="flex items-center gap-2.5">
                      <span
                        class={`flex size-8 shrink-0 items-center justify-center rounded-lg transition-transform group-hover:scale-105 ${n.ready ? 'bg-success/10 text-success' : 'bg-destructive/10 text-destructive'}`}
                      >
                        <HardDrive class="size-4" />
                      </span>
                      <span class="truncate font-mono text-xs">{n.name}</span>
                    </div>
                  </Table.Cell>
                  <Table.Cell class="w-32">
                    <Badge variant={n.ready ? 'success' : 'destructive'}>
                      <span
                        class={`size-1.5 rounded-full ${n.ready ? 'animate-pulse bg-success' : 'bg-destructive'}`}
                      ></span>
                      {n.ready ? 'Ready' : 'Not ready'}
                    </Badge>
                  </Table.Cell>
                  <Table.Cell class="hidden w-40 sm:table-cell">
                    <div class="space-y-1">
                      <div class="flex items-center justify-between text-[11px] tabular-nums text-muted-foreground">
                        <span>{n.cpu_allocatable} / {n.cpu_capacity}</span>
                        <span class="font-medium">{cpuPct.toFixed(0)}%</span>
                      </div>
                      <div class="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                        <div
                          class="h-full rounded-full bg-gradient-to-r from-primary to-info transition-[width] duration-500"
                          style="width: {cpuPct}%"
                        ></div>
                      </div>
                    </div>
                  </Table.Cell>
                  <Table.Cell class="hidden w-44 sm:table-cell">
                    <div class="space-y-1">
                      <div class="flex items-center justify-between text-[11px] tabular-nums text-muted-foreground">
                        <span>{fmtMem(n.memory_allocatable)} / {fmtMem(n.memory_capacity)}</span>
                        <span class="font-medium">{memPct.toFixed(0)}%</span>
                      </div>
                      <div class="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                        <div
                          class="h-full rounded-full bg-gradient-to-r from-info to-primary transition-[width] duration-500"
                          style="width: {memPct}%"
                        ></div>
                      </div>
                    </div>
                  </Table.Cell>
                  <Table.Cell class="w-20 text-right">
                    <span
                      class="inline-flex items-center justify-center rounded-md bg-muted px-2 py-0.5 text-xs font-semibold tabular-nums"
                    >
                      {n.pod_count}
                    </span>
                  </Table.Cell>
                </Table.Row>
              {/each}
              {#if filteredNodes.length === 0}
                <Table.Row class="hover:bg-transparent">
                  <Table.Cell colspan={5} class="py-12 text-center text-sm text-muted-foreground">
                    <HardDrive class="mx-auto mb-2 size-5 opacity-50" />
                    {data.nodes.length === 0
                      ? 'No nodes are reporting yet.'
                      : 'No nodes match this filter.'}
                  </Table.Cell>
                </Table.Row>
              {/if}
            </Table.Body>
          </Table.Root>
          <div class="border-t border-border bg-muted/20 px-4 py-3">
            <Pagination
              count={filteredNodes.length}
              perPage={ADMIN_PER_PAGE}
              bind:page={nodesPage}
              itemLabel="node"
            />
          </div>
        </Card>
      </div>
    </Tabs.Content>

    <!-- Audit -->
    <Tabs.Content value="plans" class="mt-5">
      <Card>
        <div class="flex flex-wrap items-center justify-between gap-3 px-5 pb-3 pt-5">
          <SectionHeader icon={Coins} title="VM plans" description="Resources + pricing for every plan. Changes take effect on the next VM launch." />
          <Button size="sm" onclick={openCreatePlan}>
            <Plus class="size-4" /> New plan
          </Button>
        </div>
        <CardContent class="pt-0">
          <Table.Root class="table-fixed" containerClass="[scrollbar-gutter:stable]">
            <Table.Header class="bg-muted/40">
              <Table.Row class="hover:bg-transparent">
                <Table.Head class="w-40">Plan</Table.Head>
                <Table.Head class="hidden w-48 md:table-cell">Resources</Table.Head>
                <Table.Head class="w-28">Credits/hr</Table.Head>
                <Table.Head class="hidden w-28 sm:table-cell">Workspace</Table.Head>
                <Table.Head class="w-24">Status</Table.Head>
                <Table.Head class="w-32 text-right">Actions</Table.Head>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {#each data.plans as p (p.name)}
                <Table.Row class="group {p.is_active ? '' : 'opacity-60'}">
                  <Table.Cell>
                    <div class="font-medium">{p.display_name}</div>
                    <div class="font-mono text-xs text-muted-foreground">{p.name}</div>
                  </Table.Cell>
                  <Table.Cell class="hidden font-mono text-xs text-muted-foreground md:table-cell">
                    {p.cpu} CPU · {p.memory} · {p.disk}
                  </Table.Cell>
                  <Table.Cell class="font-mono">{p.credits_per_hour}</Table.Cell>
                  <Table.Cell class="hidden font-mono text-xs sm:table-cell">{p.workspace_gb} GB</Table.Cell>
                  <Table.Cell>
                    {#if p.is_active}
                      <Badge variant="outline" class="border-success/30 text-success">Active</Badge>
                    {:else}
                      <Badge variant="outline" class="text-muted-foreground">Inactive</Badge>
                    {/if}
                  </Table.Cell>
                  <Table.Cell class="text-right">
                    <div class="flex items-center justify-end gap-1">
                      <Button variant="ghost" size="sm" onclick={() => openEditPlan(p)} aria-label={`Edit ${p.name}`}>
                        <Pencil class="size-3.5" />
                      </Button>
                      {#if p.is_active}
                        <Button
                          variant="ghost"
                          size="sm"
                          onclick={() => deactivatePlan(p)}
                          disabled={planBusy === p.name}
                          aria-label={`Deactivate ${p.name}`}
                        >
                          {#if planBusy === p.name}
                            <Spinner class="size-3.5" />
                          {:else}
                            <Power class="size-3.5 text-destructive" />
                          {/if}
                        </Button>
                      {:else}
                        <Button
                          variant="ghost"
                          size="sm"
                          onclick={() => reactivatePlan(p)}
                          disabled={planBusy === p.name}
                        >
                          {#if planBusy === p.name}
                            <Spinner class="size-3.5" />
                          {:else}
                            <Check class="size-3.5 text-success" />
                          {/if}
                        </Button>
                      {/if}
                    </div>
                  </Table.Cell>
                </Table.Row>
              {:else}
                <Table.Row>
                  <Table.Cell colspan={6} class="py-10 text-center text-sm text-muted-foreground">
                    No plans yet. Create one to let students launch VMs.
                  </Table.Cell>
                </Table.Row>
              {/each}
            </Table.Body>
          </Table.Root>
        </CardContent>
      </Card>
    </Tabs.Content>

    <Tabs.Content value="images" class="mt-5">
      <Card>
        <div class="flex flex-wrap items-center justify-between gap-3 px-5 pb-3 pt-5">
          <SectionHeader icon={Database} title="VM templates" description="Base images students can launch. The default is used when a launch omits a template." />
          <Button size="sm" onclick={openCreateImage}>
            <Plus class="size-4" /> New template
          </Button>
        </div>
        <CardContent class="pt-0">
          <Table.Root class="table-fixed" containerClass="[scrollbar-gutter:stable]">
            <Table.Header class="bg-muted/40">
              <Table.Row class="hover:bg-transparent">
                <Table.Head class="w-40">Template</Table.Head>
                <Table.Head class="hidden md:table-cell">Image</Table.Head>
                <Table.Head class="w-24">Default</Table.Head>
                <Table.Head class="w-24">Status</Table.Head>
                <Table.Head class="w-32 text-right">Actions</Table.Head>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {#each data.images as im (im.template)}
                <Table.Row class="group {im.is_active ? '' : 'opacity-60'}">
                  <Table.Cell>
                    <div class="font-medium">{im.display_name}</div>
                    <div class="font-mono text-xs text-muted-foreground">{im.template}</div>
                  </Table.Cell>
                  <Table.Cell class="hidden truncate font-mono text-xs text-muted-foreground md:table-cell">
                    {im.image}
                  </Table.Cell>
                  <Table.Cell>
                    {#if im.is_default}
                      <Badge variant="outline" class="border-primary/30 text-primary">Default</Badge>
                    {/if}
                  </Table.Cell>
                  <Table.Cell>
                    {#if im.is_active}
                      <Badge variant="outline" class="border-success/30 text-success">Active</Badge>
                    {:else}
                      <Badge variant="outline" class="text-muted-foreground">Inactive</Badge>
                    {/if}
                  </Table.Cell>
                  <Table.Cell class="text-right">
                    <div class="flex items-center justify-end gap-1">
                      <Button variant="ghost" size="sm" onclick={() => openEditImage(im)} aria-label={`Edit ${im.template}`}>
                        <Pencil class="size-3.5" />
                      </Button>
                      {#if im.is_active}
                        <Button variant="ghost" size="sm" onclick={() => deactivateImage(im)} disabled={imageBusy === im.template} aria-label={`Deactivate ${im.template}`}>
                          {#if imageBusy === im.template}<Spinner class="size-3.5" />{:else}<Power class="size-3.5 text-destructive" />{/if}
                        </Button>
                      {:else}
                        <Button variant="ghost" size="sm" onclick={() => reactivateImage(im)} disabled={imageBusy === im.template}>
                          {#if imageBusy === im.template}<Spinner class="size-3.5" />{:else}<Check class="size-3.5 text-success" />{/if}
                        </Button>
                      {/if}
                    </div>
                  </Table.Cell>
                </Table.Row>
              {:else}
                <Table.Row>
                  <Table.Cell colspan={5} class="py-10 text-center text-sm text-muted-foreground">
                    No templates yet.
                  </Table.Cell>
                </Table.Row>
              {/each}
            </Table.Body>
          </Table.Root>
        </CardContent>
      </Card>
    </Tabs.Content>

    <Tabs.Content value="courses" class="mt-5">
      <Card>
        <div class="flex flex-wrap items-center justify-between gap-3 px-5 pb-3 pt-5">
          <SectionHeader
            icon={BookOpen}
            title="Courses"
            description="Each course is owned by a professor, who manages its roster and can fund the whole class at once."
          />
          <Button size="sm" onclick={openCreateCourse} disabled={professors.length === 0}>
            <Plus class="size-4" /> New course
          </Button>
        </div>
        <CardContent class="pt-0">
          {#if professors.length === 0}
            <p class="mb-4 rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning">
              No professors yet — approve a teacher request before creating a course.
            </p>
          {/if}
          <Table.Root class="table-fixed" containerClass="[scrollbar-gutter:stable]">
            <Table.Header class="bg-muted/40">
              <Table.Row class="hover:bg-transparent">
                <Table.Head class="w-40">Course</Table.Head>
                <Table.Head class="hidden w-48 md:table-cell">Professor</Table.Head>
                <Table.Head class="w-28">Students</Table.Head>
                <Table.Head class="w-24">Status</Table.Head>
                <Table.Head class="w-36 text-right">Actions</Table.Head>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {#each data.courses as c (c.id)}
                <Table.Row class="group {c.is_active ? '' : 'opacity-60'}">
                  <Table.Cell>
                    <div class="font-medium">{c.name}</div>
                    <div class="font-mono text-xs text-muted-foreground">{c.code}</div>
                  </Table.Cell>
                  <Table.Cell class="hidden text-sm text-muted-foreground md:table-cell">
                    {c.professor_name ?? '—'}
                  </Table.Cell>
                  <Table.Cell class="font-mono">{c.enrolled_count}</Table.Cell>
                  <Table.Cell>
                    {#if c.is_active}
                      <Badge variant="outline" class="border-success/30 text-success">Active</Badge>
                    {:else}
                      <Badge variant="outline" class="text-muted-foreground">Inactive</Badge>
                    {/if}
                  </Table.Cell>
                  <Table.Cell class="text-right">
                    <div class="flex items-center justify-end gap-1">
                      <Tooltip content="Manage roster">
                        <Button
                          variant="ghost"
                          size="sm"
                          onclick={() => openRoster(c)}
                          aria-label={`Manage roster for ${c.code}`}
                        >
                          <Users class="size-3.5" />
                        </Button>
                      </Tooltip>
                      <Button
                        variant="ghost"
                        size="sm"
                        onclick={() => openEditCourse(c)}
                        aria-label={`Edit ${c.code}`}
                      >
                        <Pencil class="size-3.5" />
                      </Button>
                      {#if c.is_active}
                        <Button
                          variant="ghost"
                          size="sm"
                          onclick={() => deactivateCourse(c)}
                          disabled={courseBusy === c.id}
                          aria-label={`Deactivate ${c.code}`}
                        >
                          {#if courseBusy === c.id}
                            <Spinner class="size-3.5" />
                          {:else}
                            <Power class="size-3.5 text-destructive" />
                          {/if}
                        </Button>
                      {:else}
                        <Button
                          variant="ghost"
                          size="sm"
                          onclick={() => reactivateCourse(c)}
                          disabled={courseBusy === c.id}
                          aria-label={`Reactivate ${c.code}`}
                        >
                          {#if courseBusy === c.id}
                            <Spinner class="size-3.5" />
                          {:else}
                            <Check class="size-3.5 text-success" />
                          {/if}
                        </Button>
                      {/if}
                    </div>
                  </Table.Cell>
                </Table.Row>
              {:else}
                <Table.Row>
                  <Table.Cell colspan={5} class="py-10 text-center text-sm text-muted-foreground">
                    No courses yet. Create one to give a professor a roster to fund.
                  </Table.Cell>
                </Table.Row>
              {/each}
            </Table.Body>
          </Table.Root>
        </CardContent>
      </Card>
    </Tabs.Content>

    <Tabs.Content value="audit" class="mt-5">
      <div class="animate-fade-up space-y-3">
        <SectionHeader title="Audit log" icon={ScrollText} />
        <Card class="overflow-hidden">
          <Table.Root class="table-fixed" containerClass="[scrollbar-gutter:stable]">
            <Table.Header class="bg-muted/40">
              <Table.Row class="hover:bg-transparent">
                <Table.Head class="w-24">Time</Table.Head>
                <Table.Head>Action</Table.Head>
                <Table.Head class="hidden w-44 md:table-cell">Resource</Table.Head>
                <Table.Head class="hidden w-28 lg:table-cell">User</Table.Head>
                <Table.Head class="hidden w-32 lg:table-cell">IP</Table.Head>
                <Table.Head class="w-20 text-right">Status</Table.Head>
              </Table.Row>
            </Table.Header>
          </Table.Root>
          <Table.Root class="table-fixed" containerClass="max-h-[34rem] [scrollbar-gutter:stable]">
            <Table.Body>
              {#each pagedAudit as log (log.id)}
                {@const act = parseAction(log.action)}
                <Table.Row class="group">
                  <Table.Cell class="w-24 whitespace-nowrap text-xs text-muted-foreground">
                    {relTime(log.created_at)}
                  </Table.Cell>
                  <Table.Cell>
                    <div class="flex min-w-0 items-center gap-2">
                      <span
                        class={`shrink-0 rounded-md px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-wide ring-1 ring-inset ${methodTone(act.method)}`}
                      >
                        {act.method ?? 'EVENT'}
                      </span>
                      <span class="truncate font-mono text-xs text-foreground">{act.path}</span>
                    </div>
                  </Table.Cell>
                  <Table.Cell class="hidden w-44 md:table-cell">
                    {#if log.resource_type}
                      <span
                        class="inline-flex max-w-full items-center gap-1 truncate rounded-md border border-border/60 bg-muted/50 px-2 py-0.5 text-[11px] text-muted-foreground"
                      >
                        {log.resource_type}{#if log.resource_id}<span class="font-mono">· {shortId(log.resource_id, 8)}</span>{/if}
                      </span>
                    {:else}
                      <span class="text-muted-foreground/40">—</span>
                    {/if}
                  </Table.Cell>
                  <Table.Cell class="hidden w-28 truncate font-mono text-xs text-muted-foreground lg:table-cell">
                    {log.user_id ? shortId(log.user_id, 8) : '—'}
                  </Table.Cell>
                  <Table.Cell class="hidden w-32 truncate font-mono text-xs text-muted-foreground lg:table-cell">
                    {log.ip_address ?? '—'}
                  </Table.Cell>
                  <Table.Cell class="w-20 text-right">
                    <span
                      class={`inline-flex items-center rounded-md px-1.5 py-0.5 font-mono text-xs font-semibold ring-1 ring-inset ${statusChipClass(log.status_code)}`}
                    >
                      {log.status_code ?? '—'}
                    </span>
                  </Table.Cell>
                </Table.Row>
              {/each}
              {#if data.auditLogs.length === 0}
                <Table.Row class="hover:bg-transparent">
                  <Table.Cell colspan={6} class="py-12 text-center text-sm text-muted-foreground">
                    <ScrollText class="mx-auto mb-2 size-5 opacity-50" />
                    No audit events recorded yet.
                  </Table.Cell>
                </Table.Row>
              {/if}
            </Table.Body>
          </Table.Root>
          <div class="border-t border-border bg-muted/20 px-4 py-3">
            <Pagination
              count={data.auditLogs.length}
              perPage={ADMIN_PER_PAGE}
              bind:page={auditPage}
              itemLabel="event"
            />
          </div>
        </Card>
      </div>
    </Tabs.Content>

    <!-- Issues -->
    <Tabs.Content value="issues" class="mt-5">
      <Card class="overflow-hidden">
        <CardContent class="space-y-3 p-4">
          <SectionHeader title="Issue reports" icon={Inbox}>
            {#snippet action()}
              <Badge variant="muted">
                {data.issues.filter((i) => i.status === 'open').length} open
              </Badge>
            {/snippet}
          </SectionHeader>
          {#if data.issues.length === 0}
            <p class="py-10 text-center text-sm text-muted-foreground">No issue reports.</p>
          {:else}
            <div class="space-y-3">
              {#each data.issues as issue (issue.id)}
                <div class="rounded-lg border border-border p-3">
                  <div class="mb-1 flex items-center justify-between gap-2">
                    <span class="truncate font-mono text-xs text-muted-foreground">
                      {shortId(issue.id, 8)}{issue.pod_id ? ` · pod ${shortId(issue.pod_id, 8)}` : ''}
                    </span>
                    <Badge variant={issue.status === 'resolved' ? 'success' : 'muted'}>
                      {issue.status}
                    </Badge>
                  </div>
                  <p class="whitespace-pre-wrap text-sm">{issue.description}</p>
                  {#if issue.status === 'open'}
                    <div class="mt-2 flex items-start gap-2">
                      <textarea
                        bind:value={issueResponses[issue.id]}
                        placeholder="Reply (optional) — shown to the reporter…"
                        rows="2"
                        class="flex-1 rounded-md border border-input bg-background px-2 py-1 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      ></textarea>
                      <Button
                        size="sm"
                        disabled={resolvingIssue === issue.id}
                        onclick={() => resolveIssue(issue.id)}
                      >
                        {#if resolvingIssue === issue.id}<Spinner class="size-4" />{:else}Resolve{/if}
                      </Button>
                    </div>
                  {:else if issue.response}
                    <p class="mt-2 rounded-md bg-muted/50 px-2 py-1 text-sm">
                      <span class="font-medium">Response:</span>
                      {issue.response}
                    </p>
                  {/if}
                </div>
              {/each}
            </div>
          {/if}
        </CardContent>
      </Card>
    </Tabs.Content>
  </Tabs.Root>
</div>

<!-- Allocate credits dialog -->
<Dialog
  bind:open={allocOpen}
  title="Allocate credits"
  description={allocUser
    ? `to ${allocUser.name || allocUser.email}`
    : ''}
>
  <div class="space-y-4">
    <div>
      <Label for="alloc-amount">Amount</Label>
      <div class="relative mt-1">
        <Coins
          class="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          id="alloc-amount"
          type="number"
          step="0.5"
          min="0.5"
          bind:value={allocAmount}
          class="pl-8"
        />
      </div>
      <p class="mt-1 text-xs text-muted-foreground">
        1 credit ≈ 1 hour of a "small" plan VM.
      </p>
    </div>
    <div>
      <Label for="alloc-desc">Description</Label>
      <Input
        id="alloc-desc"
        bind:value={allocDescription}
        placeholder="What is this for?"
        class="mt-1"
      />
    </div>
  </div>

  {#snippet footer()}
    <Button variant="outline" onclick={() => (allocOpen = false)}>Cancel</Button>
    <Button onclick={allocate} disabled={allocating}>
      {#if allocating}
        <Spinner class="size-4" /> Allocating…
      {:else}
        <Coins class="size-4" /> Allocate
      {/if}
    </Button>
  {/snippet}
</Dialog>

<Dialog
  bind:open={planDialogOpen}
  title={planEditing ? `Edit plan “${planEditing}”` : 'New plan'}
  description="Resources and pricing apply to VMs launched after saving."
>
  <div class="space-y-4">
    {#if !planEditing}
      <div>
        <Label for="plan-name">Key</Label>
        <Input id="plan-name" bind:value={planForm.name} placeholder="gpu-large" class="mt-1 font-mono" />
        <p class="mt-1 text-xs text-muted-foreground">
          Lowercase letters, digits and hyphens. Immutable once created.
        </p>
      </div>
    {/if}
    <div>
      <Label for="plan-display">Display name</Label>
      <Input id="plan-display" bind:value={planForm.display_name} placeholder="GPU Large" class="mt-1" />
    </div>
    <div class="grid grid-cols-3 gap-3">
      <div>
        <Label for="plan-cpu">CPU</Label>
        <Input id="plan-cpu" bind:value={planForm.cpu} placeholder="4" class="mt-1 font-mono" />
      </div>
      <div>
        <Label for="plan-mem">Memory</Label>
        <Input id="plan-mem" bind:value={planForm.memory} placeholder="8Gi" class="mt-1 font-mono" />
      </div>
      <div>
        <Label for="plan-disk">Disk</Label>
        <Input id="plan-disk" bind:value={planForm.disk} placeholder="20Gi" class="mt-1 font-mono" />
      </div>
    </div>
    <div class="grid grid-cols-2 gap-3">
      <div>
        <Label for="plan-rate">Credits / hour</Label>
        <Input id="plan-rate" type="number" step="0.5" min="0.5" bind:value={planForm.credits_per_hour} class="mt-1 font-mono" />
      </div>
      <div>
        <Label for="plan-ws">Workspace (GB)</Label>
        <Input id="plan-ws" type="number" step="1" min="1" bind:value={planForm.workspace_gb} class="mt-1 font-mono" />
      </div>
    </div>
  </div>

  {#snippet footer()}
    <Button variant="outline" onclick={() => (planDialogOpen = false)}>Cancel</Button>
    <Button onclick={savePlan} disabled={planSaving || !planFormValid}>
      {#if planSaving}
        <Spinner class="size-4" /> Saving…
      {:else}
        <Check class="size-4" /> Save plan
      {/if}
    </Button>
  {/snippet}
</Dialog>

<Dialog
  bind:open={imageDialogOpen}
  title={imageEditing ? `Edit template “${imageEditing}”` : 'New template'}
  description="Maps a template key to a container image students can launch."
>
  <div class="space-y-4">
    {#if !imageEditing}
      <div>
        <Label for="img-template">Key</Label>
        <Input id="img-template" bind:value={imageForm.template} placeholder="rust" class="mt-1 font-mono" />
        <p class="mt-1 text-xs text-muted-foreground">Lowercase letters, digits and hyphens. Immutable once created.</p>
      </div>
    {/if}
    <div>
      <Label for="img-display">Display name</Label>
      <Input id="img-display" bind:value={imageForm.display_name} placeholder="Rust" class="mt-1" />
    </div>
    <div>
      <Label for="img-image">Container image</Label>
      <Input id="img-image" bind:value={imageForm.image} placeholder="hopper/vm-rust:1.0" class="mt-1 font-mono" />
    </div>
    <div>
      <Label for="img-desc">Description</Label>
      <Input id="img-desc" bind:value={imageForm.description} placeholder="Cargo + rustc toolchain" class="mt-1" />
    </div>
    <label class="flex items-center gap-2 text-sm">
      <input type="checkbox" bind:checked={imageForm.is_default} class="size-4 rounded border-border" />
      Make this the default template
    </label>
  </div>

  {#snippet footer()}
    <Button variant="outline" onclick={() => (imageDialogOpen = false)}>Cancel</Button>
    <Button onclick={saveImage} disabled={imageSaving || !imageFormValid}>
      {#if imageSaving}
        <Spinner class="size-4" /> Saving…
      {:else}
        <Check class="size-4" /> Save template
      {/if}
    </Button>
  {/snippet}
</Dialog>

<Dialog
  bind:open={quotaOpen}
  title="Resource quota"
  description={quotaUser ? (quotaUser.name || quotaUser.email) : ''}
>
  {#if quotaLoading}
    <div class="flex items-center gap-2 py-6 text-sm text-muted-foreground">
      <Spinner class="size-4" /> Loading current quota…
    </div>
  {:else}
    <div class="space-y-4">
      <p class="text-xs text-muted-foreground">
        {quotaIsCustom
          ? 'This user has a custom quota override.'
          : 'This user is on the global default quota. Saving creates an override.'}
      </p>
      <div class="grid grid-cols-2 gap-3">
        <div>
          <Label for="q-vms">Max concurrent VMs</Label>
          <Input id="q-vms" type="number" min="0" step="1" bind:value={quotaMaxVms} class="mt-1 font-mono" />
        </div>
        <div>
          <Label for="q-gb">Max workspace (GB)</Label>
          <Input id="q-gb" type="number" min="0" step="1" bind:value={quotaMaxGb} class="mt-1 font-mono" />
        </div>
      </div>
    </div>
  {/if}

  {#snippet footer()}
    <Button variant="outline" onclick={resetQuota} disabled={quotaSaving || quotaLoading || !quotaIsCustom}>
      Reset to default
    </Button>
    <Button onclick={saveQuota} disabled={quotaSaving || quotaLoading}>
      {#if quotaSaving}
        <Spinner class="size-4" /> Saving…
      {:else}
        <Check class="size-4" /> Save quota
      {/if}
    </Button>
  {/snippet}
</Dialog>

<Dialog
  bind:open={courseDialogOpen}
  title={courseEditing ? 'Edit course' : 'New course'}
  description="Courses are owned by a professor, who manages the roster and funds the class."
>
  <div class="space-y-4">
    {#if !courseEditing}
      <div>
        <Label for="course-code">Course code</Label>
        <Input id="course-code" bind:value={courseForm.code} placeholder="CSE-4108" class="mt-1 font-mono" />
        <p class="mt-1 text-xs text-muted-foreground">
          Letters, digits and hyphens. Immutable once created.
        </p>
      </div>
    {/if}
    <div>
      <Label for="course-name">Name</Label>
      <Input id="course-name" bind:value={courseForm.name} placeholder="Operating Systems" class="mt-1" />
    </div>
    <div>
      <Label for="course-desc">Description</Label>
      <Input id="course-desc" bind:value={courseForm.description} placeholder="Optional" class="mt-1" />
    </div>
    <div>
      <Label for="course-prof">Professor</Label>
      <select
        id="course-prof"
        bind:value={courseForm.professor_id}
        class="mt-1 h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
      >
        {#each professors as p (p.id)}
          <option value={p.id}>{p.name} · {p.email}</option>
        {/each}
      </select>
      <p class="mt-1 text-xs text-muted-foreground">
        Only this professor (and admins) can manage the roster.
      </p>
    </div>
  </div>

  {#snippet footer()}
    <Button variant="outline" onclick={() => (courseDialogOpen = false)}>Cancel</Button>
    <Button onclick={saveCourse} disabled={courseSaving || !courseFormValid}>
      {#if courseSaving}
        <Spinner class="size-4" /> Saving…
      {:else}
        <Check class="size-4" /> Save course
      {/if}
    </Button>
  {/snippet}
</Dialog>

<Dialog
  bind:open={rosterOpen}
  title={rosterCourse ? `Roster — ${rosterCourse.code}` : 'Roster'}
  description="Students enrolled in this course. Removing a student does not claw back credits already allocated."
>
  {#if rosterLoading}
    <div class="flex justify-center py-8"><Spinner class="size-5" /></div>
  {:else}
    <div class="space-y-4">
      <div class="flex items-end gap-2">
        <div class="flex-1">
          <Label for="enroll-student">Add a student</Label>
          <select
            id="enroll-student"
            bind:value={enrollId}
            class="mt-1 h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="">Select a student…</option>
            {#each enrollCandidates as s (s.id)}
              <option value={s.id}>{s.name} · {s.email}</option>
            {/each}
          </select>
        </div>
        <Button onclick={enrollStudent} disabled={!enrollId || rosterBusy !== null}>
          {#if rosterBusy === enrollId && enrollId}
            <Spinner class="size-4" />
          {:else}
            <UserPlus class="size-4" />
          {/if}
          Enroll
        </Button>
      </div>

      {#if roster.length}
        <div class="max-h-72 overflow-y-auto rounded-md border border-border">
          {#each roster as m (m.id)}
            <div class="flex items-center justify-between gap-3 border-b border-border px-3 py-2 last:border-b-0">
              <div class="min-w-0">
                <div class="truncate text-sm font-medium">{m.name}</div>
                <div class="truncate text-xs text-muted-foreground">{m.email}</div>
              </div>
              <div class="flex shrink-0 items-center gap-2">
                <span class="font-mono text-xs text-muted-foreground">{m.balance} cr</span>
                <Button
                  variant="ghost"
                  size="sm"
                  onclick={() => unenrollStudent(m)}
                  disabled={rosterBusy === m.id}
                  aria-label={`Remove ${m.name}`}
                >
                  {#if rosterBusy === m.id}
                    <Spinner class="size-3.5" />
                  {:else}
                    <Trash2 class="size-3.5 text-destructive" />
                  {/if}
                </Button>
              </div>
            </div>
          {/each}
        </div>
      {:else}
        <p class="py-6 text-center text-sm text-muted-foreground">
          No students enrolled yet.
        </p>
      {/if}
    </div>
  {/if}

  {#snippet footer()}
    <Button variant="outline" onclick={() => (rosterOpen = false)}>Done</Button>
  {/snippet}
</Dialog>
