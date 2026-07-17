import pytest

from app.services import vm_capacity


class FakeNode:
    def __init__(self, ready, cpu_allocatable, memory_allocatable):
        self.ready = ready
        self.cpu_allocatable = cpu_allocatable
        self.memory_allocatable = memory_allocatable


class FakeVm:
    def __init__(self, cpu, memory, disk=None):
        self.cpu = cpu
        self.memory = memory
        self.disk = disk


@pytest.mark.parametrize(
    ("quantity", "expected"),
    [
        ("500m", 500),
        ("2", 2000),
        ("1.5", 1500),
    ],
)
def test_parse_cpu_millis(quantity, expected):
    assert vm_capacity.parse_cpu_millis(quantity) == expected


@pytest.mark.parametrize(
    ("quantity", "expected"),
    [
        ("2Gi", 2 * 1024**3),
        ("13000000Ki", 13000000 * 1024),
        ("1e3", 1000),
    ],
)
def test_parse_mem_bytes(quantity, expected):
    assert vm_capacity.parse_mem_bytes(quantity) == expected


@pytest.mark.parametrize("quantity", ["", "bad", "1Zi"])
def test_parse_quantity_rejects_invalid_values(quantity):
    with pytest.raises(ValueError):
        vm_capacity.parse_mem_bytes(quantity)


def test_cpu_request_millis_mirrors_orchestrator_floor():
    assert vm_capacity.cpu_request_millis("200m") == 100
    assert vm_capacity.cpu_request_millis("4") == 1000


def test_mem_request_bytes_returns_full_limit():
    assert vm_capacity.mem_request_bytes("4Gi") == 4 * 1024**3


def test_compute_capacity_uses_only_ready_nodes_and_tracks_storage():
    capacity = vm_capacity.compute_capacity(
        nodes=[
            FakeNode(True, "4", "8Gi"),
            FakeNode(False, "99", "99Gi"),
            FakeNode(True, "2", "4Gi"),
        ],
        live_vms=[
            FakeVm("1", "2Gi", "5Gi"),
            FakeVm("500m", "1Gi"),
        ],
        reserve_cpu_m=250,
        reserve_mem_b=512 * 1024**2,
        total_storage_b=50 * 1024**3,
        reserve_storage_b=5 * 1024**3,
    )

    assert capacity.total_cpu_m == 6000
    assert capacity.total_mem_b == 12 * 1024**3
    assert capacity.used_cpu_m == 375
    assert capacity.used_mem_b == 3 * 1024**3
    assert capacity.used_storage_b == 5 * 1024**3
    assert capacity.free_cpu_m() == 5375
    assert capacity.free_mem_b() == int(8.5 * 1024**3)
    assert capacity.free_storage_b() == 40 * 1024**3


def test_plan_fits_checks_cpu_memory_and_optional_disk():
    capacity = vm_capacity.Capacity(
        total_cpu_m=4000,
        total_mem_b=8 * 1024**3,
        used_cpu_m=1000,
        used_mem_b=2 * 1024**3,
        reserve_cpu_m=500,
        reserve_mem_b=1 * 1024**3,
        total_storage_b=20 * 1024**3,
        used_storage_b=5 * 1024**3,
        reserve_storage_b=1 * 1024**3,
    )

    assert vm_capacity.plan_fits(capacity, "2", "2Gi", "5Gi") is True
    assert vm_capacity.plan_fits(capacity, "20", "2Gi", "5Gi") is False
    assert vm_capacity.plan_fits(capacity, "2", "20Gi", "5Gi") is False
    assert vm_capacity.plan_fits(capacity, "2", "2Gi", "99Gi") is False
