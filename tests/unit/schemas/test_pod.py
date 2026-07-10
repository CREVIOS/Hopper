from datetime import datetime

from app.schemas.pod import (
    DEFAULT_TEMPLATE,
    CreatePodRequest,
    PodResponse,
    VM_TEMPLATE_IMAGES,
    VmPlan,
)


def test_create_pod_request_uses_default_template_image():
    request = CreatePodRequest(plan=VmPlan.SMALL)

    assert request.template == DEFAULT_TEMPLATE
    assert request.resolved_image() == VM_TEMPLATE_IMAGES[DEFAULT_TEMPLATE]


def test_create_pod_request_uses_template_specific_image():
    request = CreatePodRequest(plan=VmPlan.MEDIUM, template="cpp")

    assert request.resolved_image() == VM_TEMPLATE_IMAGES["cpp"]


def test_create_pod_request_prefers_explicit_image_override():
    request = CreatePodRequest(
        plan=VmPlan.LARGE,
        template="java",
        image="custom/image:latest",
    )

    assert request.resolved_image() == "custom/image:latest"


def test_create_pod_request_falls_back_for_unknown_template():
    request = CreatePodRequest(plan=VmPlan.SMALL, template="unknown-template")

    assert request.resolved_image() == VM_TEMPLATE_IMAGES[DEFAULT_TEMPLATE]


def test_pod_response_accepts_enum_state_and_optional_connection_fields():
    response = PodResponse(
        id="pod-1",
        user_id="user-1",
        state="running",
        plan="small",
        image="hopper/vm-ubuntu:22.04",
        namespace="hopper",
        ssh_port=30022,
        vscode_port=30080,
        ssh_password="secret",
        created_at=datetime(2026, 1, 1, 12, 0, 0),
        updated_at=datetime(2026, 1, 1, 12, 5, 0),
    )

    assert response.state.value == "running"
    assert response.ssh_port == 30022
    assert response.vscode_port == 30080
