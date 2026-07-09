from datetime import datetime

from app.models.session import PodSession
from app.routers.pods import _session_to_response, list_plans


def test_session_to_response_hides_connection_details_for_non_running_pod():
    session = PodSession(
        id="pod-1",
        user_id="user-1",
        plan="small",
        image="hopper/vm-ubuntu:22.04",
        cpu="1",
        memory="2Gi",
        namespace="hopper",
        pod_name="vm-pod-1",
        state="terminated",
        ssh_port=30022,
        vscode_port=30080,
        ssh_password="secret",
        started_at=datetime(2026, 1, 1, 12, 0, 0),
        updated_at=datetime(2026, 1, 1, 12, 5, 0),
    )

    response = _session_to_response(session)

    assert response.ssh_port is None
    assert response.vscode_port is None
    assert response.ssh_password is None


def test_session_to_response_keeps_connection_details_for_running_pod():
    session = PodSession(
        id="pod-1",
        user_id="user-1",
        plan="small",
        image="hopper/vm-ubuntu:22.04",
        cpu="1",
        memory="2Gi",
        namespace="hopper",
        pod_name="vm-pod-1",
        state="running",
        ssh_port=30022,
        vscode_port=30080,
        ssh_password="secret",
        started_at=datetime(2026, 1, 1, 12, 0, 0),
        updated_at=datetime(2026, 1, 1, 12, 5, 0),
    )

    response = _session_to_response(session)

    assert response.ssh_port == 30022
    assert response.vscode_port == 30080
    assert response.ssh_password == "secret"


async def test_list_plans_returns_all_vm_plans():
    result = await list_plans()

    assert set(result) == {"small", "medium", "large"}
    assert result["small"]["credits_per_hour"] == 1.0
