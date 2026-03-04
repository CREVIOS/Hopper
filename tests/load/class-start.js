import http from 'k6/http';
import { check, sleep } from 'k6';

// Scenario: 30 students launch GPU pods simultaneously at class start
export const options = {
  scenarios: {
    class_start: {
      executor: 'shared-iterations',
      vus: 30,
      iterations: 30,
      maxDuration: '5m',
    },
  },
  thresholds: {
    'http_req_duration{scenario:class_start}': ['p(95)<2000'],
    http_req_failed: ['rate<0.01'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

export default function () {
  // Step 1: Login (get auth token)
  const loginRes = http.post(`${BASE_URL}/auth/login`, JSON.stringify({
    // TODO: Use test credentials from Keycloak
    username: `student-${__VU}@university.edu`,
    password: 'test',
  }), {
    headers: { 'Content-Type': 'application/json' },
  });

  check(loginRes, {
    'login successful': (r) => r.status === 200,
  });

  const token = loginRes.json('access_token') || 'test-token';

  // Step 2: Check credit balance
  const balanceRes = http.get(`${BASE_URL}/credits/balance`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  check(balanceRes, {
    'balance retrieved': (r) => r.status === 200,
  });

  // Step 3: Launch GPU pod
  const createRes = http.post(`${BASE_URL}/pods`, JSON.stringify({
    gpu_tier: 'standard',
    image: 'pytorch/pytorch:2.4.0-cuda12.4-cudnn9-runtime',
  }), {
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
  });

  check(createRes, {
    'pod creation accepted': (r) => r.status === 200 || r.status === 201,
    'pod creation latency < 2s': (r) => r.timings.duration < 2000,
  });

  // Step 4: Poll pod status until running
  if (createRes.status === 200 || createRes.status === 201) {
    const podId = createRes.json('id');
    let running = false;
    for (let i = 0; i < 30; i++) {
      const statusRes = http.get(`${BASE_URL}/pods/${podId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (statusRes.json('state') === 'running') {
        running = true;
        break;
      }
      sleep(2);
    }

    check(null, {
      'pod reached running state': () => running,
    });
  }
}
