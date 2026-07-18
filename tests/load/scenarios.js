import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const ACCESS_TOKEN = __ENV.ACCESS_TOKEN || 'e2e-student-1';
const MAX_LIVE_PODS = Number(__ENV.K6_MAX_LIVE_PODS || 2);
const CLASS_START_VUS = Number(__ENV.K6_CLASS_START_VUS || 6);
const CLASS_START_ITERATIONS = Number(__ENV.K6_CLASS_START_ITERATIONS || 6);
const METRICS_VUS = Number(__ENV.K6_METRICS_VUS || 12);
const METRICS_DURATION = __ENV.K6_METRICS_DURATION || '45s';
const SPIKE_PEAK_VUS = Number(__ENV.K6_SPIKE_PEAK_VUS || 20);
const SPIKE_UP_DURATION = __ENV.K6_SPIKE_UP_DURATION || '20s';
const SPIKE_HOLD_DURATION = __ENV.K6_SPIKE_HOLD_DURATION || '40s';
const SPIKE_DOWN_DURATION = __ENV.K6_SPIKE_DOWN_DURATION || '20s';
const CLASS_END_VUS = Number(__ENV.K6_CLASS_END_VUS || 6);
const CLASS_END_ITERATIONS = Number(__ENV.K6_CLASS_END_ITERATIONS || 6);
const BILLING_VUS = Number(__ENV.K6_BILLING_VUS || 10);
const BILLING_DURATION = __ENV.K6_BILLING_DURATION || '30s';
const METRICS_START_TIME = __ENV.K6_METRICS_START_TIME || '20s';
const SPIKE_START_TIME = __ENV.K6_SPIKE_START_TIME || '1m10s';
const CLASS_END_START_TIME = __ENV.K6_CLASS_END_START_TIME || '2m30s';
const BILLING_START_TIME = __ENV.K6_BILLING_START_TIME || '3m';

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
      vus: CLASS_START_VUS,
      iterations: CLASS_START_ITERATIONS,
      maxDuration: '2m',
    },
    metrics_polling: {
      executor: 'constant-vus',
      exec: 'metricsPolling',
      vus: METRICS_VUS,
      duration: METRICS_DURATION,
      startTime: METRICS_START_TIME,
    },
    spike: {
      executor: 'ramping-vus',
      exec: 'spikeTraffic',
      startVUs: 0,
      stages: [
        { duration: SPIKE_UP_DURATION, target: SPIKE_PEAK_VUS },
        { duration: SPIKE_HOLD_DURATION, target: SPIKE_PEAK_VUS },
        { duration: SPIKE_DOWN_DURATION, target: 0 },
      ],
      startTime: SPIKE_START_TIME,
    },
    class_end: {
      executor: 'shared-iterations',
      exec: 'classEnd',
      vus: CLASS_END_VUS,
      iterations: CLASS_END_ITERATIONS,
      maxDuration: '2m',
      startTime: CLASS_END_START_TIME,
    },
    billing_stress: {
      executor: 'constant-vus',
      exec: 'billingStress',
      vus: BILLING_VUS,
      duration: BILLING_DURATION,
      startTime: BILLING_START_TIME,
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

function parseJson(response, fallback) {
  try {
    return response.json();
  } catch (_) {
    return fallback;
  }
}

function isLivePod(pod) {
  return pod && ['pending', 'creating', 'running'].includes(pod.state);
}

function getPodList() {
  const response = listPods();
  check(response, { 'pod list loaded': (result) => result.status === 200 });
  if (response.status !== 200) {
    return [];
  }

  const body = parseJson(response, []);
  return Array.isArray(body) ? body : [];
}

function terminatePod(podId) {
  const response = http.del(`${BASE_URL}/pods/${podId}`, null, {
    headers: headers(),
  });
  check(response, {
    'pod termination accepted': (result) => [200, 202, 204, 404].includes(result.status),
  });
  return response;
}

function trimLivePods() {
  const livePods = getPodList().filter(isLivePod);
  if (livePods.length < MAX_LIVE_PODS) {
    return livePods;
  }

  for (let index = MAX_LIVE_PODS - 1; index < livePods.length; index += 1) {
    terminatePod(livePods[index].id);
  }

  return getPodList().filter(isLivePod);
}

export function classStart() {
  const livePods = trimLivePods();
  if (livePods.length >= MAX_LIVE_PODS) {
    return;
  }

  const response = http.post(
    `${BASE_URL}/pods/`,
    JSON.stringify({ plan: 'small', template: 'pytorch' }),
    { headers: headers() },
  );
  check(response, {
    'pod creation accepted': (result) => [200, 201, 202].includes(result.status),
    'pod creation API under 2 seconds': (result) => result.timings.duration < 2000,
  });

  if (![200, 201, 202].includes(response.status)) {
    return;
  }

  const createdPod = parseJson(response, null);
  if (response.status === 202 || !createdPod || !createdPod.id) {
    return;
  }

  const pod = http.get(`${BASE_URL}/pods/${createdPod.id}`, { headers: headers() });
  check(pod, {
    'created pod is readable': (result) => result.status === 200,
  });
}

export function metricsPolling() {
  const podList = getPodList().filter(isLivePod);
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
  const podList = getPodList().filter(isLivePod);
  if (podList.length === 0) return;
  const response = terminatePod(podList[0].id);
  check(response, {
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
