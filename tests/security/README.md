# Infrastructure security tests

Run only against an isolated staging cluster. The suite performs server-side
admission dry runs, API authorization probes, in-pod network probes, and
optional GPU memory checks.

Required variables:

```bash
export BASE_URL=https://staging.example.edu/api
export STUDENT_TOKEN=...
export ADMIN_TOKEN=...
export OTHER_STUDENT_POD_ID=...
export STUDENT_NAMESPACE_A=student-a
export STUDENT_NAMESPACE_B=student-b
export STUDENT_POD_A=pod-a
export STUDENT_POD_B_IP=10.0.0.20
export NATS_SERVICE_IP=10.0.0.30
export POSTGRES_SERVICE_IP=10.0.0.31
./tests/security/run-security.sh
```

GPU checks additionally require `RUN_GPU_SECURITY_TESTS=true`,
`GPU_TEST_NAMESPACE`, and `GPU_TEST_POD`. The CVE fixture must be built and
attempted only in a disposable security-test namespace using the staging
runtime's normal untrusted workload path.
