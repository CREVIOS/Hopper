import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const ACCESS_TOKEN = __ENV.ACCESS_TOKEN || '';

function headers() {
  return {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${ACCESS_TOKEN}`,
    Cookie: `session_token=${ACCESS_TOKEN}`,
  };
}

export const options = {
  scenarios: {
    class_start: {
      executor: 'shared-iterations',
      exec: 'classStart',
      vus: 30,
      iterations: 30,
      maxDuration: '5m',
    },
    metrics_polling: {
      executor: 'constant-vus',
      exec: 'metricsPolling',
      vus: 100,
      duration: '10m',
      startTime: '5m',
    },
    spike: {
      executor: 'ramping-vus',
      exec: 'spikeTraffic',
      startVUs: 0,
      stages: [
        { duration: '1m', target: 150 },
        { duration: '5m', target: 150 },
        { duration: '1m', target: 0 },
      ],
      startTime: '15m',
    },
    class_end: {
      executor: 'shared-iterations',
      exec: 'classEnd',
      vus: 30,
      iterations: 30,
      maxDuration: '5m',
      startTime: '22m',
    },
    billing_stress: {
      executor: 'constant-vus',
      exec: 'billingStress',
      vus: 50,
      duration: '5m',
      startTime: '27m',
    },
  },
  thresholds: {
    'http_req_duration{scenario:class_start}': ['p(95)<2000'],
    'http_req_duration{scenario:metrics_polling}': ['p(95)<200'],
    'http_req_duration{scenario:spike}': ['p(95)<5000'],
    'http_req_duration{scenario:class_end}': ['p(95)<10000'],
    'http_req_duration{scenario:billing_stress}': ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
  },
};

function listPods() {
  return http.get(`${BASE_URL}/pods/`, { headers: headers() });
}

export function classStart() {
  const response = http.post(
    `${BASE_URL}/pods/`,
    JSON.stringify({ plan: 'small', template: 'pytorch' }),
    { headers: headers() },
  );
  check(response, {
    'pod creation accepted': (result) => [200, 201, 202].includes(result.status),
    'pod creation API under 2 seconds': (result) => result.timings.duration < 2000,
  });
}

export function metricsPolling() {
  const pods = listPods();
  check(pods, { 'pod list loaded': (result) => result.status === 200 });
  const podList = pods.status === 200 ? pods.json() : [];
  if (podList.length > 0) {
    const metrics = http.get(`${BASE_URL}/pods/${podList[0].id}/metrics`, {
      headers: headers(),
    });
    check(metrics, {
      'metrics endpoint responds': (result) => [200, 204].includes(result.status),
      'metrics delivered under 200ms': (result) => result.timings.duration < 200,
    });
  }
  sleep(1);
}

export function spikeTraffic() {
  const responses = http.batch([
    ['GET', `${BASE_URL}/pods/`, null, { headers: headers() }],
    ['GET', `${BASE_URL}/credits/balance`, null, { headers: headers() }],
    ['GET', `${BASE_URL}/usage/me`, null, { headers: headers() }],
  ]);
  check(responses, {
    'spike requests avoid server errors': (results) =>
      results.every((result) => result.status < 500),
  });
}

export function classEnd() {
  const pods = listPods();
  const podList = pods.status === 200 ? pods.json() : [];
  if (podList.length === 0) return;
  const response = http.del(`${BASE_URL}/pods/${podList[0].id}`, null, {
    headers: headers(),
  });
  check(response, {
    'pod termination accepted': (result) => [200, 202, 204].includes(result.status),
    'termination API under 10 seconds': (result) => result.timings.duration < 10000,
  });
}

export function billingStress() {
  const balance = http.get(`${BASE_URL}/credits/balance`, { headers: headers() });
  const history = http.get(`${BASE_URL}/credits/history`, { headers: headers() });
  check(balance, {
    'balance query succeeds': (result) => result.status === 200,
    'balance query under 500ms': (result) => result.timings.duration < 500,
  });
  check(history, { 'ledger history succeeds': (result) => result.status === 200 });
}
