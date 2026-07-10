import httpx

from app.services import k8s_pod_lookup as lookup_module


class _FakeResponse:
    def __init__(self, status_code=200, json_body=None, text=""):
        self.status_code = status_code
        self._json_body = json_body or {}
        self.text = text

    def json(self):
        return self._json_body


class _FakeAsyncClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers):
        self.calls.append((url, headers))
        return self.response


def test_in_kubernetes_pod_requires_env_and_service_account_token(monkeypatch):
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
    monkeypatch.setattr(lookup_module._SA_TOKEN, "is_file", lambda: True)

    assert lookup_module.in_kubernetes_pod() is True


async def test_get_pod_ip_returns_none_outside_kubernetes(monkeypatch):
    monkeypatch.setattr("app.services.k8s_pod_lookup.in_kubernetes_pod", lambda: False)

    assert await lookup_module.get_pod_ip("hopper", "vm-1") is None


async def test_get_pod_ip_returns_pod_ip_on_success(monkeypatch):
    monkeypatch.setattr("app.services.k8s_pod_lookup.in_kubernetes_pod", lambda: True)
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
    monkeypatch.setenv("KUBERNETES_SERVICE_PORT", "8443")
    monkeypatch.setattr(lookup_module._SA_CA, "is_file", lambda: True)
    monkeypatch.setattr(lookup_module._SA_TOKEN, "read_text", lambda: "token-value")

    fake_client = _FakeAsyncClient(_FakeResponse(json_body={"status": {"podIP": "10.42.0.15"}}))
    monkeypatch.setattr("app.services.k8s_pod_lookup.httpx.AsyncClient", lambda **kwargs: fake_client)

    result = await lookup_module.get_pod_ip("hopper", "vm-1")

    assert result == "10.42.0.15"
    assert fake_client.calls[0][0] == "https://10.0.0.1:8443/api/v1/namespaces/hopper/pods/vm-1"
    assert fake_client.calls[0][1]["Authorization"] == "Bearer token-value"


async def test_get_pod_ip_returns_none_on_http_error(monkeypatch):
    monkeypatch.setattr("app.services.k8s_pod_lookup.in_kubernetes_pod", lambda: True)
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
    monkeypatch.setattr(lookup_module._SA_CA, "is_file", lambda: True)
    monkeypatch.setattr(lookup_module._SA_TOKEN, "read_text", lambda: "token-value")

    class _RaisingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers):
            raise httpx.HTTPError("boom")

    monkeypatch.setattr("app.services.k8s_pod_lookup.httpx.AsyncClient", lambda **kwargs: _RaisingClient())

    assert await lookup_module.get_pod_ip("hopper", "vm-1") is None


async def test_get_pod_ip_cached_uses_cache(monkeypatch):
    lookup_module._pod_ip_cache.clear()
    lookup_module._pod_ip_cache[("hopper", "vm-1")] = (100.0, "10.42.0.15")
    monkeypatch.setattr("app.services.k8s_pod_lookup.time.monotonic", lambda: 105.0)

    async def fail_lookup(namespace, pod_name):
        raise AssertionError("cache should be used")

    monkeypatch.setattr("app.services.k8s_pod_lookup.get_pod_ip", fail_lookup)

    assert await lookup_module.get_pod_ip_cached("hopper", "vm-1") == "10.42.0.15"


async def test_resolve_vm_ssh_socket_prefers_pod_ip(monkeypatch):
    monkeypatch.setattr("app.services.k8s_pod_lookup.in_kubernetes_pod", lambda: True)

    async def fake_cached_ip(namespace, pod_name):
        return "10.42.0.15"

    monkeypatch.setattr("app.services.k8s_pod_lookup.get_pod_ip_cached", fake_cached_ip)

    assert await lookup_module.resolve_vm_ssh_socket("hopper", "vm-1", 30022) == ("10.42.0.15", 22)


async def test_resolve_vm_vscode_http_base_falls_back_to_nodeport(monkeypatch):
    monkeypatch.setattr("app.services.k8s_pod_lookup.in_kubernetes_pod", lambda: False)
    monkeypatch.setattr("app.services.k8s_pod_lookup.settings.node_ip", "127.0.0.1")

    assert await lookup_module.resolve_vm_vscode_http_base("hopper", "vm-1", 30080) == "http://127.0.0.1:30080"
