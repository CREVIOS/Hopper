import crypto from 'node:crypto';
import http from 'node:http';

const PLAN_INFO = {
  small: { rate: 1, cpu: '1', memory: '2 Gi' },
  medium: { rate: 2, cpu: '2', memory: '4 Gi' },
  large: { rate: 4, cpu: '4', memory: '8 Gi' }
};

const TEMPLATE_IMAGE = {
  ubuntu: 'hopper/vm-ubuntu:22.04',
  'python-ml': 'hopper/vm-python-ml:latest',
  cpp: 'hopper/vm-cpp:latest',
  java: 'hopper/vm-java:latest'
};

const states = new Map();

function nowIso() {
  return new Date().toISOString();
}

function parseCookies(req) {
  const cookie = req.headers.cookie || '';
  return Object.fromEntries(
    cookie
      .split(';')
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => {
        const index = part.indexOf('=');
        return index === -1
          ? [part, '']
          : [part.slice(0, index), decodeURIComponent(part.slice(index + 1))];
      })
  );
}

function tokenForUser(user) {
  return `e2e-${user.id}`;
}

function refreshTokenForUser(user) {
  return `e2e-refresh-${user.id}`;
}

function defaultUsers() {
  return [
    {
      id: 'student-1',
      email: 'student-1@test.edu',
      name: 'E2E Student One',
      role: 'student',
      balance: 100,
      course: 'CS229',
      pending_teacher: false,
      created_at: '2026-07-01T09:00:00.000Z'
    },
    {
      id: 'student-2',
      email: 'student-2@test.edu',
      name: 'E2E Student Two',
      role: 'student',
      balance: 0,
      course: 'CS229',
      pending_teacher: false,
      created_at: '2026-07-01T09:05:00.000Z'
    },
    {
      id: 'student-3',
      email: 'student-3@test.edu',
      name: 'E2E Student Three',
      role: 'student',
      balance: 100,
      course: 'CS231N',
      pending_teacher: false,
      created_at: '2026-07-01T09:10:00.000Z'
    },
    {
      id: 'professor-1',
      email: 'professor@test.edu',
      name: 'E2E Professor',
      role: 'professor',
      balance: 500,
      course: 'CS229',
      pending_teacher: false,
      created_at: '2026-07-01T09:15:00.000Z'
    },
    {
      id: 'admin-1',
      email: 'admin@test.edu',
      name: 'E2E Admin',
      role: 'admin',
      balance: 99999,
      course: 'all',
      pending_teacher: false,
      created_at: '2026-07-01T09:20:00.000Z'
    }
  ];
}

function newState() {
  return {
    users: defaultUsers(),
    pods: [],
    queue: [],
    transactions: [],
    audit_logs: [],
    teacher_requests: [
      {
        id: 'req-1',
        email: 'teacher-pending@test.edu',
        name: 'Pending Teacher',
        created_at: '2026-07-05T10:00:00.000Z'
      }
    ],
    session: {
      expired: false,
      refresh_valid: true
    },
    availability: {
      cpu: { total_cores: 8, used_cores: 2, free_cores: 6 },
      memory: { total_gib: 32, used_gib: 8, free_gib: 24 },
      storage: { total_gib: 256, used_gib: 40, free_gib: 216 },
      nodes_ready: 1,
      queue_length: 0
    },
    next_create_failure: null,
    nextPod: 1,
    nextQueue: 1,
    nextTx: 1,
    nextAudit: 1
  };
}

function cookieValue(req, name) {
  return parseCookies(req)[name] || 'default';
}

function stateFor(req) {
  const id = cookieValue(req, 'e2e_test_id');
  if (!states.has(id)) states.set(id, newState());
  return states.get(id);
}

function json(res, code, body, headers = {}) {
  res.writeHead(code, { 'content-type': 'application/json', ...headers });
  res.end(JSON.stringify(body));
}

async function body(req) {
  let value = '';
  for await (const chunk of req) value += chunk;
  return value ? JSON.parse(value) : {};
}

function currentUser(state, req, { allowExpired = false } = {}) {
  const token = parseCookies(req).session_token;
  if (!token) return null;
  const user = state.users.find((entry) => token === tokenForUser(entry));
  if (!user) return null;
  if (state.session.expired && !allowExpired) return null;
  return user;
}

function requireUser(state, req, res) {
  const user = currentUser(state, req);
  if (!user) {
    json(res, 401, { detail: 'Not authenticated' });
    return null;
  }
  return user;
}

function addAudit(state, action, extra = {}) {
  state.audit_logs.unshift({
    id: `audit-${state.nextAudit++}`,
    action,
    created_at: nowIso(),
    status_code: 200,
    ...extra
  });
}

function planDetails(plan) {
  return PLAN_INFO[plan] || PLAN_INFO.small;
}

function normalizePod(state, pod) {
  const owner = state.users.find((user) => user.id === pod.user_id);
  const details = planDetails(pod.plan);
  return {
    namespace: 'hopper',
    image: TEMPLATE_IMAGE[pod.template || 'ubuntu'] || TEMPLATE_IMAGE.ubuntu,
    ssh_port: 30022,
    ssh_password: 'e2e-secret',
    vscode_port: 30080,
    state: 'running',
    cpu: details.cpu,
    memory: details.memory,
    template: 'ubuntu',
    created_at: nowIso(),
    updated_at: nowIso(),
    started_at: nowIso(),
    node_name: 'mock-node',
    user_name: owner?.name,
    user_email: owner?.email,
    ...pod
  };
}

function syncAvailability(state) {
  state.availability.queue_length = state.queue.length;
}

function findUser(state, id) {
  return state.users.find((user) => user.id === id);
}

function applySetup(state, payload) {
  if (payload.session) {
    state.session = { ...state.session, ...payload.session };
  }
  if (payload.balances) {
    for (const [userId, balance] of Object.entries(payload.balances)) {
      const user = findUser(state, userId);
      if (user) user.balance = Number(balance);
    }
  }
  if (Array.isArray(payload.users)) {
    for (const patch of payload.users) {
      const existing = findUser(state, patch.id);
      if (existing) Object.assign(existing, patch);
    }
  }
  if (payload.availability) {
    state.availability = {
      ...state.availability,
      ...payload.availability,
      cpu: { ...state.availability.cpu, ...(payload.availability.cpu || {}) },
      memory: { ...state.availability.memory, ...(payload.availability.memory || {}) },
      storage: { ...state.availability.storage, ...(payload.availability.storage || {}) }
    };
  }
  if (Array.isArray(payload.pods)) {
    state.pods = payload.pods.map((pod, index) =>
      normalizePod(state, {
        id: pod.id || `e2e-pod-${index + 1}`,
        user_id: pod.user_id || 'student-1',
        plan: pod.plan || 'small',
        template: pod.template || 'ubuntu',
        ...pod
      })
    );
    state.nextPod = state.pods.length + 1;
  }
  if (Array.isArray(payload.queue)) {
    state.queue = payload.queue.map((entry, index) => ({
      id: entry.id || `queue-${index + 1}`,
      user_id: entry.user_id || 'student-1',
      plan: entry.plan || 'small',
      template: entry.template || 'ubuntu',
      state: entry.state || 'queued',
      position: index + 1,
      created_at: entry.created_at || nowIso()
    }));
    state.nextQueue = state.queue.length + 1;
  }
  if (Array.isArray(payload.teacher_requests)) {
    state.teacher_requests = payload.teacher_requests.map((entry, index) => ({
      id: entry.id || `req-${index + 1}`,
      email: entry.email || `teacher-${index + 1}@test.edu`,
      name: entry.name || `Teacher ${index + 1}`,
      created_at: entry.created_at || nowIso()
    }));
  }
  if (Array.isArray(payload.transactions)) {
    state.transactions = payload.transactions.map((entry, index) => ({
      id: entry.id || `tx-${index + 1}`,
      account_id: entry.account_id || entry.user_id || 'student-1',
      user_id: entry.user_id || entry.account_id || 'student-1',
      amount: entry.amount ?? 0,
      direction: entry.direction || 'debit',
      type: entry.type || 'allocation',
      pod_id: entry.pod_id,
      created_at: entry.created_at || nowIso()
    }));
    state.nextTx = state.transactions.length + 1;
  }
  if (payload.next_create_failure !== undefined) {
    state.next_create_failure = payload.next_create_failure;
  }
  syncAvailability(state);
}

function limitedTransactions(state, user, limit) {
  const transactions = state.transactions.filter(
    (entry) => entry.account_id === user.id || entry.user_id === user.id
  );
  return Number.isFinite(limit) ? transactions.slice(0, limit) : transactions;
}

function writeTerminalFrame(socket, text) {
  const payload = Buffer.from(text);
  const header = payload.length < 126 ? Buffer.from([0x81, payload.length]) : Buffer.from([0x81, 126, payload.length >> 8, payload.length & 0xff]);
  socket.write(Buffer.concat([header, payload]));
}

function decodeWsFrame(buffer) {
  const length = buffer[1] & 0x7f;
  let offset = 2;
  let actualLength = length;
  if (length === 126) {
    actualLength = buffer.readUInt16BE(offset);
    offset += 2;
  }
  const mask = buffer.subarray(offset, offset + 4);
  offset += 4;
  const payload = buffer.subarray(offset, offset + actualLength);
  const decoded = Buffer.alloc(actualLength);
  for (let i = 0; i < actualLength; i += 1) {
    decoded[i] = payload[i] ^ mask[i % 4];
  }
  return decoded.toString('utf8');
}

function terminalOutput(command, podId) {
  if (command === 'pwd') return '/workspace';
  if (command === 'whoami') return 'root';
  if (command === 'nvidia-smi') return `GPU 0  Hopper Mock  ${podId}`;
  return `${command}: command completed`;
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://mock');
  let state = stateFor(req);

  if (req.method === 'POST' && url.pathname === '/__test/reset') {
    state = newState();
    states.set(cookieValue(req, 'e2e_test_id'), state);
    return json(res, 200, { ok: true });
  }

  if (req.method === 'POST' && url.pathname === '/__test/setup') {
    applySetup(state, await body(req));
    return json(res, 200, { ok: true });
  }

  if (url.pathname.includes('/protocol/openid-connect/token')) {
    const raw = await new Promise((resolve) => {
      let value = '';
      req.on('data', (chunk) => {
        value += chunk;
      });
      req.on('end', () => resolve(value));
    });
    const user =
      raw.includes('username=admin')
        ? state.users.find((entry) => entry.role === 'admin')
        : state.users.find((entry) => entry.email === 'student-1@test.edu');
    return json(res, 200, {
      access_token: tokenForUser(user),
      refresh_token: refreshTokenForUser(user),
      expires_in: 300,
      refresh_expires_in: 3600
    });
  }

  if (req.method === 'POST' && url.pathname === '/auth/login') {
    const input = await body(req);
    const matched = state.users.find((user) => user.email === input.email);
    if (!matched || input.password !== 'e2e') {
      return json(res, 401, { detail: 'Invalid email or password.' });
    }
    state.session.expired = false;
    return json(
      res,
      200,
      {
        id: matched.id,
        email: matched.email,
        name: matched.name,
        role: matched.role,
        pending_teacher: matched.pending_teacher
      },
      {
        'set-cookie': [
          `session_token=${tokenForUser(matched)}; HttpOnly; SameSite=Lax; Path=/`,
          `refresh_token=${refreshTokenForUser(matched)}; HttpOnly; SameSite=Lax; Path=/`
        ]
      }
    );
  }

  if (req.method === 'POST' && url.pathname === '/auth/refresh') {
    const refreshToken = parseCookies(req).refresh_token;
    const matched = state.users.find((user) => refreshToken === refreshTokenForUser(user));
    if (!matched || !state.session.refresh_valid) {
      return json(res, 401, { detail: 'Refresh token expired' });
    }
    state.session.expired = false;
    return json(
      res,
      200,
      { ok: true },
      {
        'set-cookie': [
          `session_token=${tokenForUser(matched)}; HttpOnly; SameSite=Lax; Path=/`,
          `refresh_token=${refreshTokenForUser(matched)}; HttpOnly; SameSite=Lax; Path=/`
        ]
      }
    );
  }

  if (url.pathname === '/auth/me') {
    const authenticated = currentUser(state, req);
    return authenticated
      ? json(res, 200, authenticated)
      : json(res, 401, { detail: 'Not authenticated' });
  }

  if (url.pathname === '/auth/logout') {
    return json(
      res,
      200,
      { ok: true },
      {
        'set-cookie': [
          'session_token=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/',
          'refresh_token=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/',
          'id_token=; Max-Age=0; HttpOnly; SameSite=Lax; Path=/'
        ]
      }
    );
  }

  if (url.pathname === '/healthz') return json(res, 200, { status: 'ok' });
  if (url.pathname === '/readyz') return json(res, 200, { status: 'ready' });

  const user = requireUser(state, req, res);
  if (!user) return;

  if (url.pathname === '/credits/balance') {
    return json(res, 200, { account_id: user.id, balance: findUser(state, user.id)?.balance ?? 0 });
  }

  if (url.pathname === '/credits/history') {
    const limit = Number(url.searchParams.get('limit'));
    return json(res, 200, limitedTransactions(state, user, limit));
  }

  if (url.pathname === '/credits/students') {
    if (user.role !== 'professor') return json(res, 403, { detail: 'Forbidden' });
    return json(
      res,
      200,
      state.users
        .filter((entry) => entry.role === 'student' && entry.course === user.course)
        .map((entry) => ({
          id: entry.id,
          email: entry.email,
          name: entry.name,
          balance: entry.balance
        }))
    );
  }

  if (req.method === 'POST' && url.pathname === '/credits/allocate') {
    if (!['admin', 'professor'].includes(user.role)) {
      return json(res, 403, { detail: 'Forbidden' });
    }
    const input = await body(req);
    const target = findUser(state, input.user_id);
    const amount = Number(input.amount || 0);
    if (!target || !Number.isFinite(amount) || amount <= 0) {
      return json(res, 400, { detail: 'Invalid allocation request' });
    }
    if (user.role === 'professor' && user.balance < amount) {
      return json(res, 400, { detail: 'Not enough credits' });
    }
    target.balance += amount;
    state.transactions.unshift({
      id: `tx-${state.nextTx++}`,
      account_id: target.id,
      user_id: target.id,
      amount,
      direction: 'credit',
      type: input.description || 'allocation',
      created_at: nowIso()
    });
    if (user.role === 'professor') {
      const actor = findUser(state, user.id);
      actor.balance -= amount;
      state.transactions.unshift({
        id: `tx-${state.nextTx++}`,
        account_id: actor.id,
        user_id: actor.id,
        amount: -amount,
        direction: 'debit',
        type: 'teacher_allocation',
        created_at: nowIso()
      });
    }
    addAudit(state, 'post:/credits/allocate', { resource_id: target.id, resource_type: 'credit' });
    return json(res, 201, { ok: true });
  }

  if (url.pathname === '/pods/plans') {
    return json(res, 200, {
      small: { credits_per_hour: 1 },
      medium: { credits_per_hour: 2 },
      large: { credits_per_hour: 4 }
    });
  }

  if (url.pathname === '/pods/availability') {
    syncAvailability(state);
    return json(res, 200, state.availability);
  }

  if (url.pathname === '/pods/queue') {
    return json(
      res,
      200,
      state.queue
        .filter((entry) => entry.user_id === user.id)
        .map((entry, index) => ({ ...entry, position: index + 1 }))
    );
  }

  const queueMatch = url.pathname.match(/^\/pods\/queue\/([^/]+)$/);
  if (queueMatch && req.method === 'DELETE') {
    const index = state.queue.findIndex((entry) => entry.id === queueMatch[1] && entry.user_id === user.id);
    if (index === -1) return json(res, 404, { detail: 'Queue entry not found' });
    if (state.queue[index].state !== 'queued') return json(res, 409, { detail: 'Request is already being admitted' });
    state.queue.splice(index, 1);
    syncAvailability(state);
    addAudit(state, 'delete:/pods/queue', { resource_id: queueMatch[1], resource_type: 'queue' });
    return json(res, 200, { ok: true });
  }

  if (req.method === 'GET' && url.pathname === '/pods/') {
    return json(res, 200, state.pods.filter((pod) => pod.user_id === user.id));
  }

  if (req.method === 'POST' && url.pathname === '/pods/') {
    const input = await body(req);
    const rate = planDetails(input.plan || 'small').rate;
    if (user.balance < rate) return json(res, 402, { detail: 'Insufficient credits' });
    if (state.next_create_failure) {
      const detail = state.next_create_failure;
      state.next_create_failure = null;
      return json(res, 500, { detail });
    }
    const activeCount = state.pods.filter(
      (pod) => pod.user_id === user.id && ['running', 'pending', 'creating', 'stopping'].includes(pod.state)
    ).length;
    if (activeCount >= 3) {
      return json(res, 429, { detail: 'Maximum concurrent pods reached (3/3)' });
    }
    if ((state.availability.cpu.free_cores ?? 1) <= 0) {
      const entry = {
        id: `queue-${state.nextQueue++}`,
        user_id: user.id,
        plan: input.plan || 'small',
        template: input.template || 'ubuntu',
        state: 'queued',
        position: state.queue.length + 1,
        created_at: nowIso()
      };
      state.queue.push(entry);
      syncAvailability(state);
      addAudit(state, 'post:/pods/queue', { resource_id: entry.id, resource_type: 'queue' });
      return json(res, 202, { queued: true, id: entry.id, state: 'queued', plan: entry.plan, position: entry.position });
    }
    const pod = normalizePod(state, {
      id: `e2e-pod-${state.nextPod++}`,
      user_id: user.id,
      plan: input.plan || 'small',
      template: input.template || 'ubuntu'
    });
    state.pods.unshift(pod);
    state.transactions.unshift({
      id: `tx-${state.nextTx++}`,
      account_id: user.id,
      user_id: user.id,
      amount: -rate,
      direction: 'debit',
      type: 'pod_launch_hold',
      pod_id: pod.id,
      created_at: nowIso()
    });
    addAudit(state, 'post:/pods/', { resource_id: pod.id, resource_type: 'pod' });
    return json(res, 201, pod);
  }

  const podMatch = url.pathname.match(/^\/pods\/([^/]+)$/);
  if (podMatch) {
    const pod = state.pods.find((entry) => entry.id === podMatch[1]);
    if (!pod) return json(res, 404, { detail: 'Not found' });
    if (user.role !== 'admin' && pod.user_id !== user.id) {
      return json(res, 403, { detail: 'Forbidden' });
    }
    if (req.method === 'DELETE') {
      pod.state = 'terminated';
      pod.updated_at = nowIso();
      addAudit(state, 'delete:/pods/', { resource_id: pod.id, resource_type: 'pod' });
      return json(res, 200, { message: 'terminated', pod_id: pod.id });
    }
    return json(res, 200, pod);
  }

  if (/^\/pods\/[^/]+\/metrics$/.test(url.pathname)) {
    const podId = url.pathname.split('/')[2];
    const pod = state.pods.find((entry) => entry.id === podId);
    if (!pod) return json(res, 404, { detail: 'Not found' });
    if (user.role !== 'admin' && pod.user_id !== user.id) {
      return json(res, 403, { detail: 'Forbidden' });
    }
    res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' });
    res.end(
      `event: metrics\ndata: ${JSON.stringify({
        pod_id: pod.id,
        cpu_percent: 42,
        memory_used_bytes: 1073741824,
        memory_limit_bytes: 2147483648
      })}\n\n`
    );
    return;
  }

  if (req.method === 'POST' && url.pathname === '/issues/') {
    const input = await body(req);
    addAudit(state, 'post:/issues/', { resource_id: input.pod_id, resource_type: 'issue' });
    return json(res, 201, { ok: true });
  }

  if (url.pathname === '/usage/summary/me') {
    return json(res, 200, {
      pod_count: state.pods.filter((pod) => pod.user_id === user.id).length,
      avg_cpu_percent: 42,
      avg_memory_bytes: 1073741824
    });
  }

  if (url.pathname.startsWith('/usage/')) {
    return json(res, 200, []);
  }

  if (url.pathname === '/admin/stats') {
    if (user.role !== 'admin') return json(res, 403, { detail: 'Forbidden' });
    return json(res, 200, {
      total_users: state.users.length,
      active_vms: state.pods.filter((pod) => pod.state === 'running').length,
      total_vms_created: state.pods.length
    });
  }

  if (url.pathname === '/admin/users') {
    if (user.role !== 'admin') return json(res, 403, { detail: 'Forbidden' });
    return json(res, 200, state.users);
  }

  if (url.pathname === '/admin/active-vms') {
    if (user.role !== 'admin') return json(res, 403, { detail: 'Forbidden' });
    return json(
      res,
      200,
      state.pods
        .filter((pod) => pod.state === 'running')
        .map((pod) => normalizePod(state, pod))
    );
  }

  if (url.pathname === '/admin/nodes') {
    if (user.role !== 'admin') return json(res, 403, { detail: 'Forbidden' });
    return json(res, 200, [
      {
        name: 'mock-node',
        cpu_capacity: '8',
        memory_capacity: '32Gi',
        cpu_allocatable: '7',
        memory_allocatable: '30Gi',
        pod_count: state.pods.length,
        ready: true
      }
    ]);
  }

  if (url.pathname === '/admin/audit-logs') {
    if (user.role !== 'admin') return json(res, 403, { detail: 'Forbidden' });
    return json(res, 200, state.audit_logs);
  }

  if (url.pathname === '/admin/teacher-requests') {
    if (user.role !== 'admin') return json(res, 403, { detail: 'Forbidden' });
    return json(res, 200, state.teacher_requests);
  }

  const teacherRequestMatch = url.pathname.match(/^\/admin\/teacher-requests\/([^/]+)\/(approve|reject)$/);
  if (teacherRequestMatch && req.method === 'POST') {
    if (user.role !== 'admin') return json(res, 403, { detail: 'Forbidden' });
    const index = state.teacher_requests.findIndex((entry) => entry.id === teacherRequestMatch[1]);
    if (index === -1) return json(res, 404, { detail: 'Request not found' });
    const requestEntry = state.teacher_requests[index];
    state.teacher_requests.splice(index, 1);
    addAudit(state, `post:/admin/teacher-requests/${teacherRequestMatch[2]}`, {
      resource_id: requestEntry.id,
      resource_type: 'teacher_request'
    });
    return json(res, 200, { ok: true });
  }

  const roleMatch = url.pathname.match(/^\/admin\/users\/([^/]+)\/role$/);
  if (roleMatch && req.method === 'PATCH') {
    if (user.role !== 'admin') return json(res, 403, { detail: 'Forbidden' });
    const target = findUser(state, roleMatch[1]);
    if (!target) return json(res, 404, { detail: 'User not found' });
    const input = await body(req);
    target.role = input.role || target.role;
    addAudit(state, 'patch:/admin/users/role', { resource_id: target.id, resource_type: 'user' });
    return json(res, 200, target);
  }

  json(res, 404, { detail: `No mock route for ${req.method} ${url.pathname}` });
});

server.on('upgrade', (req, socket) => {
  const url = new URL(req.url, 'http://mock');
  const path = url.pathname.replace(/^\/api/, '');
  const state = stateFor(req);
  const user = currentUser(state, req, { allowExpired: true });
  const match = path.match(/^\/pods\/([^/]+)\/terminal$/);
  if (!user || !match) {
    socket.end('HTTP/1.1 401 Unauthorized\r\n\r\n');
    return;
  }
  const pod = state.pods.find((entry) => entry.id === match[1]);
  if (!pod || (user.role !== 'admin' && pod.user_id !== user.id)) {
    socket.end('HTTP/1.1 403 Forbidden\r\n\r\n');
    return;
  }

  const key = req.headers['sec-websocket-key'];
  const accept = crypto
    .createHash('sha1')
    .update(`${key}258EAFA5-E914-47DA-95CA-C5AB0DC85B11`)
    .digest('base64');

  socket.write(
    [
      'HTTP/1.1 101 Switching Protocols',
      'Upgrade: websocket',
      'Connection: Upgrade',
      `Sec-WebSocket-Accept: ${accept}`,
      '\r\n'
    ].join('\r\n')
  );

  let buffer = '';
  writeTerminalFrame(socket, 'Connected!\r\nroot@hopper:/workspace# ');

  socket.on('data', (chunk) => {
    const input = decodeWsFrame(chunk);
    if (!input || input.startsWith('{"type":"ping"') || input.startsWith('{"type":"resize"')) {
      return;
    }
    buffer += input;
    writeTerminalFrame(socket, input);
    if (buffer.includes('\r')) {
      const command = buffer.replace(/\r/g, '').trim();
      buffer = '';
      if (command) {
        writeTerminalFrame(socket, `\r\n${terminalOutput(command, pod.id)}\r\nroot@hopper:/workspace# `);
      } else {
        writeTerminalFrame(socket, '\r\nroot@hopper:/workspace# ');
      }
    }
  });
});

server.listen(8000, '0.0.0.0');
