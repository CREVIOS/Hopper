import http from 'node:http';

const users = {
  student: { id: 'student-1', email: 'student-1@test.edu', name: 'E2E Student', role: 'student' },
  admin: { id: 'admin-1', email: 'admin@test.edu', name: 'E2E Admin', role: 'admin' }
};
const states = new Map();
const newState = () => ({ balance: 100, pods: [], transactions: [], next: 1 });
const cookieValue = (req, name) => {
  const entry = (req.headers.cookie || '')
    .split(';')
    .map(value => value.trim())
    .find(value => value.startsWith(`${name}=`));
  return entry ? decodeURIComponent(entry.slice(name.length + 1)) : 'default';
};
const stateFor = req => {
  const id = cookieValue(req, 'e2e_test_id');
  if (!states.has(id)) states.set(id, newState());
  return states.get(id);
};
const json = (res, code, body, headers = {}) => {
  res.writeHead(code, { 'content-type': 'application/json', ...headers });
  res.end(JSON.stringify(body));
};
const body = async req => {
  let value = ''; for await (const chunk of req) value += chunk;
  return value ? JSON.parse(value) : {};
};
const session = req => {
  const cookie = req.headers.cookie || '';
  if (cookie.includes('session_token=e2e-admin')) return 'admin';
  if (cookie.includes('session_token=e2e-student')) return 'student';
  return null;
};

http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://mock');
  let state = stateFor(req);
  if (req.method === 'POST' && url.pathname === '/__test/reset') {
    state = newState();
    states.set(cookieValue(req, 'e2e_test_id'), state);
    return json(res, 200, state);
  }
  if (req.method === 'POST' && url.pathname === '/__test/balance') { state.balance = Number((await body(req)).balance); return json(res, 200, { balance: state.balance }); }
  if (url.pathname.includes('/protocol/openid-connect/token')) {
    const raw = await new Promise(resolve => { let v=''; req.on('data', c => v+=c); req.on('end', () => resolve(v)); });
    const admin = String(raw).includes('username=admin');
    return json(res, 200, { access_token: admin ? 'e2e-admin' : 'e2e-student', refresh_token: 'e2e-refresh', expires_in: 3600, refresh_expires_in: 3600 });
  }
  if (req.method === 'POST' && url.pathname === '/auth/login') {
    const input = await body(req);
    const matched = Object.values(users).find(user => user.email === input.email);
    if (!matched || input.password !== 'e2e') {
      return json(res, 401, { detail: 'Invalid email or password.' });
    }
    const token = matched.role === 'admin' ? 'e2e-admin' : 'e2e-student';
    return json(res, 200, matched, {
      'set-cookie': `session_token=${token}; HttpOnly; SameSite=Lax; Path=/`
    });
  }
  if (url.pathname === '/auth/me') {
    const authenticatedRole = session(req);
    return authenticatedRole
      ? json(res, 200, users[authenticatedRole])
      : json(res, 401, { detail: 'Not authenticated' });
  }
  if (url.pathname === '/auth/logout') {
    res.writeHead(200, {
      'content-type': 'application/json',
      'set-cookie': [
        'session_token=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/',
        'refresh_token=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/',
        'id_token=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/'
      ]
    });
    return res.end(JSON.stringify({ ok: true }));
  }
  if (url.pathname === '/credits/balance') return json(res, 200, { account_id: 'acct-student-1', balance: state.balance });
  if (url.pathname === '/credits/history') return json(res, 200, state.transactions);
  if (url.pathname === '/healthz') return json(res, 200, { status: 'ok' });
  if (url.pathname === '/readyz') return json(res, 200, { status: 'ready' });
  if (req.method === 'POST' && url.pathname === '/credits/allocate') {
    const input = await body(req); state.balance += Number(input.amount || 0);
    state.transactions.push({ id: `tx-${Date.now()}`, amount: Number(input.amount), direction: 'credit', type: 'allocation', created_at: new Date().toISOString() });
    return json(res, 201, { balance: state.balance });
  }
  if (url.pathname === '/pods/plans') return json(res, 200, { small:{credits_per_hour:1}, medium:{credits_per_hour:2}, large:{credits_per_hour:4} });
  // Admission-queue endpoints (PR #78): a roomy cluster with an empty queue,
  // so the sync-create fast path stays the default in specs. Includes the
  // multi-node availability fields (largest_node_free, nodes).
  if (url.pathname === '/pods/availability') {
    return json(res, 200, {
      cpu: { total_cores: 8, used_cores: state.pods.filter(p=>p.state==='running').length, free_cores: 8 - state.pods.filter(p=>p.state==='running').length },
      memory: { total_gib: 32, used_gib: 2, free_gib: 30 },
      storage: { total_gib: 150, used_gib: 5, free_gib: 145 },
      nodes_ready: 1,
      largest_node_free: { cpu_cores: 8, memory_gib: 30 },
      nodes: [{ name: 'node-1', ready: true, free_cores: 8, free_gib: 30 }],
      queue_length: 0
    });
  }
  if (req.method === 'GET' && url.pathname === '/pods/queue') return json(res, 200, []);
  const queueMatch = url.pathname.match(/^\/pods\/queue\/([^/]+)$/);
  if (req.method === 'DELETE' && queueMatch) return json(res, 404, { detail: 'Queue entry not found' });
  if (req.method === 'GET' && url.pathname === '/pods/') return json(res, 200, state.pods);
  if (req.method === 'POST' && url.pathname === '/pods/') {
    const input = await body(req); const rates = { small:1, medium:2, large:4 };
    if (state.balance < rates[input.plan || 'small']) return json(res, 402, { detail: 'Insufficient credits' });
    if (state.pods.filter(p => p.state === 'running').length >= 3) return json(res, 429, { detail: 'Maximum concurrent pods reached (3/3)' });
    const id = `e2e-pod-${state.next++}`;
    const pod = { id, user_id:'student-1', state:'running', plan:input.plan || 'small', image:'hopper/vm-ubuntu:22.04', namespace:'hopper', ssh_port:30022, vscode_port:30080, ssh_password:'e2e-secret', created_at:new Date().toISOString(), updated_at:new Date().toISOString() };
    state.pods.push(pod); return json(res, 201, pod);
  }
  const podMatch = url.pathname.match(/^\/pods\/([^/]+)$/);
  if (podMatch) {
    const pod = state.pods.find(p => p.id === podMatch[1]);
    if (!pod) return json(res, 404, { detail:'Not found' });
    if (req.method === 'DELETE') { pod.state='terminated'; return json(res, 200, { message:'terminated', pod_id:pod.id }); }
    return json(res, 200, pod);
  }
  if (/^\/pods\/[^/]+\/metrics$/.test(url.pathname)) {
    res.writeHead(200, { 'content-type':'text/event-stream', 'cache-control':'no-cache' });
    res.end(`event: metrics\ndata: ${JSON.stringify({pod_id:'e2e-pod-1',cpu_percent:42,memory_used_bytes:1073741824,memory_limit_bytes:2147483648})}\n\n`); return;
  }
  if (url.pathname === '/admin/stats') return json(res, 200, { total_users:2, active_vms:state.pods.filter(p=>p.state==='running').length, total_vms_created:state.pods.length });
  if (url.pathname === '/admin/users') return json(res, 200, Object.values(users));
  if (url.pathname === '/admin/active-vms') return json(res, 200, state.pods.filter(p=>p.state==='running'));
  if (url.pathname === '/admin/nodes') return json(res, 200, [{name:'mock-node',cpu_capacity:'8',memory_capacity:'32Gi',cpu_allocatable:'7',memory_allocatable:'30Gi',pod_count:state.pods.length,ready:true}]);
  if (url.pathname === '/admin/audit-logs' || url.pathname === '/admin/teacher-requests') return json(res, 200, []);
  if (url.pathname === '/usage/summary/me') return json(res, 200, { pod_count:state.pods.length, avg_cpu_percent:42, avg_memory_bytes:1073741824 });
  if (url.pathname.startsWith('/usage/')) return json(res, 200, []);
  json(res, 404, { detail:`No mock route for ${req.method} ${url.pathname}` });
}).listen(8000, '0.0.0.0');
