import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8000';
const ACCESS_TOKEN = __ENV.ACCESS_TOKEN || 'e2e-student-1';

function headers() {
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${ACCESS_TOKEN}`,
    Cookie: `session_token=${ACCESS_TOKEN}`,
  };
}

export const options = {
  scenarios: {
    smoke: {
      executor: 'per-vu-iterations',
      vus: 1,
      iterations: 1,
      maxDuration: '1m',
    },
  },
  thresholds: {
    'http_req_duration{scenario:smoke}': ['p(95)<2000'],
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const health = http.get(`${BASE_URL}/healthz`);
  check(health, {
    'health endpoint responds': (result) => result.status === 200,
  });

  const balance = http.get(`${BASE_URL}/credits/balance`, { headers: headers() });
  check(balance, {
    'balance endpoint responds': (result) => result.status === 200,
  });

  const podsBefore = http.get(`${BASE_URL}/pods/`, { headers: headers() });
  check(podsBefore, {
    'pod list responds': (result) => result.status === 200,
  });

  const create = http.post(
    `${BASE_URL}/pods/`,
    JSON.stringify({ plan: 'small', template: 'pytorch' }),
    { headers: headers() },
  );
  check(create, {
    'pod creation accepted': (result) => [200, 201, 202].includes(result.status),
    'pod creation under 2 seconds': (result) => result.timings.duration < 2000,
  });

  if (![200, 201, 202].includes(create.status)) {
    return;
  }

  const podId = create.json('id');
  sleep(1);

  const pod = http.get(`${BASE_URL}/pods/${podId}`, { headers: headers() });
  check(pod, {
    'created pod is readable': (result) => result.status === 200,
  });

  const terminate = http.del(`${BASE_URL}/pods/${podId}`, null, { headers: headers() });
  check(terminate, {
    'pod termination accepted': (result) => [200, 202, 204].includes(result.status),
  });
}
