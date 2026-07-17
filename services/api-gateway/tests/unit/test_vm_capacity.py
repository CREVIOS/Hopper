"""Unit tests for app.services.vm_capacity (pure, no DB/gRPC/I/O).

Expected values are hand-computed against Kubernetes quantity semantics
(binary suffixes are powers of two, ``m`` is milli, bare CPU numbers are
whole cores) so a regression in the parser or the scheduling-request math is
caught rather than mirrored. The scheduling-request formulas mirror the
orchestrator's cpuRequestFor (services/orchestrator/internal/k8s/pod.go:85-92):
    cpu_request_millis = max(100, floor(cpu_limit_millis / 4))
    mem_request_bytes  = full memory limit
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.schemas.pod import VM_PLAN_RESOURCES
from app.services.vm_capacity import (
    Capacity,
    compute_capacity,
    cpu_request_millis,
    mem_request_bytes,
    parse_cpu_millis,
    parse_mem_bytes,
    plan_fits,
)

# Kubernetes binary units, computed independently of the module under test.
KIB = 1024
MIB = 1024**2
GIB = 1024**3
TIB = 1024**4


@dataclass(frozen=True)
class FakeNode:
    """Minimal stand-in for orchestrator_client.NodeInfoResponse."""

    ready: bool
    cpu_allocatable: str
    memory_allocatable: str


@dataclass(frozen=True)
class FakeVm:
    """Minimal stand-in for a live PodSession row (cpu/memory are limits)."""

    cpu: str
    memory: str


# --------------------------------------------------------------------------- #
# parse_cpu_millis
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("quantity", "expected_millis"),
    [
        ("500m", 500),          # milli suffix
        ("2", 2000),            # bare whole cores
        ("1500m", 1500),        # docstring example
        ("1", 1000),            # one core
        ("4", 4000),            # four cores
        ("250m", 250),          # small fractional core
        ("100m", 100),          # the request floor value as a limit
        ("1.5", 1500),          # decimal cores stay exact
        ("0", 0),               # zero cores
        ("  2  ", 2000),        # surrounding whitespace is tolerated
    ],
)
def test_parse_cpu_millis(quantity: str, expected_millis: int) -> None:
    assert parse_cpu_millis(quantity) == expected_millis


# --------------------------------------------------------------------------- #
# parse_mem_bytes
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("quantity", "expected_bytes"),
    [
        ("2Gi", 2 * GIB),                 # 2147483648
        ("512Mi", 512 * MIB),             # 536870912
        ("13000000Ki", 13000000 * KIB),   # 13312000000 (raw allocatable style)
        ("4Gi", 4 * GIB),
        ("8Gi", 8 * GIB),
        ("1Ki", KIB),
        ("1Mi", MIB),
        ("1Ti", TIB),
        ("1024", 1024),                   # bare bytes
        ("1M", 1_000_000),                # decimal mega (power of ten)
        ("1G", 1_000_000_000),            # decimal giga
        ("1k", 1_000),                    # decimal kilo (lowercase per K8s)
    ],
)
def test_parse_mem_bytes(quantity: str, expected_bytes: int) -> None:
    assert parse_mem_bytes(quantity) == expected_bytes


def test_binary_and_decimal_suffixes_differ() -> None:
    """Mi (2^20) must not be confused with M (10^6): K8s treats them apart."""
    assert parse_mem_bytes("1Mi") == 1_048_576
    assert parse_mem_bytes("1M") == 1_000_000
    assert parse_mem_bytes("1Mi") != parse_mem_bytes("1M")


def test_exponent_suffix_vs_scientific_notation() -> None:
    """K8s 'E' is the Exa suffix (10^18); 'e3' is scientific (x1000)."""
    assert parse_mem_bytes("1E") == 10**18
    assert parse_mem_bytes("1e3") == 1000


@pytest.mark.parametrize("bad", ["", "   ", "abc", "1Xi", "Gi", "1.2.3"])
def test_parse_rejects_invalid_quantities(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_mem_bytes(bad)


# --------------------------------------------------------------------------- #
# cpu_request_millis  (mirror of cpuRequestFor: max(100, floor(millis / 4)))
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("cpu_limit", "expected_request"),
    [
        ("1", 250),      # 1000 // 4 = 250
        ("2", 500),      # 2000 // 4 = 500
        ("4", 1000),     # 4000 // 4 = 1000
        ("500m", 125),   # 500 // 4 = 125
        ("8", 2000),     # 8000 // 4 = 2000
    ],
)
def test_cpu_request_is_a_quarter_of_the_limit(cpu_limit: str, expected_request: int) -> None:
    assert cpu_request_millis(cpu_limit) == expected_request


@pytest.mark.parametrize("cpu_limit", ["100m", "300m", "399m", "1m", "0"])
def test_cpu_request_floored_at_100m(cpu_limit: str) -> None:
    """Any limit whose quarter is below 100m clamps up to the 100m floor."""
    assert cpu_request_millis(cpu_limit) == 100


def test_cpu_request_exactly_at_floor_boundary() -> None:
    """400m // 4 == 100m: the floor and the computed value coincide."""
    assert cpu_request_millis("400m") == 100
    assert cpu_request_millis("404m") == 101  # just above the floor, not clamped


def test_cpu_request_uses_floor_not_ceiling() -> None:
    """999m // 4 == 249 (floor), not 250 (ceil): mirrors Go integer division."""
    assert cpu_request_millis("999m") == 249
    assert cpu_request_millis("1001m") == 250  # 1001 // 4 == 250, not 251


# --------------------------------------------------------------------------- #
# mem_request_bytes  (== the full limit; memory is the binding constraint)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("mem_limit", ["2Gi", "4Gi", "8Gi", "512Mi", "13000000Ki"])
def test_mem_request_equals_full_limit(mem_limit: str) -> None:
    assert mem_request_bytes(mem_limit) == parse_mem_bytes(mem_limit)


# --------------------------------------------------------------------------- #
# Capacity.free_* accessors
# --------------------------------------------------------------------------- #


def test_free_capacity_subtracts_used_and_reserve() -> None:
    cap = Capacity(
        total_cpu_m=8000,
        total_mem_b=16 * GIB,
        used_cpu_m=1000,
        used_mem_b=4 * GIB,
        reserve_cpu_m=500,
        reserve_mem_b=2 * GIB,
    )
    assert cap.free_cpu_m() == 8000 - 1000 - 500
    assert cap.free_mem_b() == (16 * GIB) - (4 * GIB) - (2 * GIB)


def test_free_capacity_clamps_at_zero() -> None:
    """Over-subscription (used + reserve > total) never reports negative free."""
    cap = Capacity(
        total_cpu_m=1000,
        total_mem_b=1 * GIB,
        used_cpu_m=2000,
        used_mem_b=4 * GIB,
        reserve_cpu_m=500,
        reserve_mem_b=1 * GIB,
    )
    assert cap.free_cpu_m() == 0
    assert cap.free_mem_b() == 0


# --------------------------------------------------------------------------- #
# compute_capacity
# --------------------------------------------------------------------------- #


def test_compute_capacity_counts_only_ready_nodes() -> None:
    nodes = [
        FakeNode(ready=True, cpu_allocatable="4", memory_allocatable="8Gi"),
        FakeNode(ready=False, cpu_allocatable="16", memory_allocatable="64Gi"),
    ]
    cap = compute_capacity(nodes, live_vms=[], reserve_cpu_m=0, reserve_mem_b=0)
    # Only the Ready node contributes; the NotReady node is ignored entirely.
    assert cap.total_cpu_m == 4000
    assert cap.total_mem_b == 8 * GIB


def test_compute_capacity_sums_multiple_ready_nodes() -> None:
    nodes = [
        FakeNode(ready=True, cpu_allocatable="4", memory_allocatable="8Gi"),
        FakeNode(ready=True, cpu_allocatable="2", memory_allocatable="4Gi"),
    ]
    cap = compute_capacity(nodes, live_vms=[], reserve_cpu_m=0, reserve_mem_b=0)
    assert cap.total_cpu_m == 6000
    assert cap.total_mem_b == 12 * GIB


def test_compute_capacity_subtracts_live_vm_requests() -> None:
    nodes = [FakeNode(ready=True, cpu_allocatable="8", memory_allocatable="16Gi")]
    live = [
        FakeVm(cpu="1", memory="2Gi"),   # request: 250m,  2Gi
        FakeVm(cpu="4", memory="8Gi"),   # request: 1000m, 8Gi
    ]
    cap = compute_capacity(nodes, live_vms=live, reserve_cpu_m=0, reserve_mem_b=0)
    # used is the sum of scheduling REQUESTS, not the raw limits.
    assert cap.used_cpu_m == 250 + 1000
    assert cap.used_mem_b == (2 * GIB) + (8 * GIB)
    assert cap.free_cpu_m() == 8000 - 1250
    assert cap.free_mem_b() == (16 * GIB) - (10 * GIB)


def test_compute_capacity_applies_reserve_and_clamps() -> None:
    nodes = [FakeNode(ready=True, cpu_allocatable="2", memory_allocatable="4Gi")]
    live = [FakeVm(cpu="2", memory="4Gi")]  # request 500m, 4Gi (all the memory)
    cap = compute_capacity(nodes, live_vms=live, reserve_cpu_m=1000, reserve_mem_b=2 * GIB)
    assert cap.reserve_cpu_m == 1000
    assert cap.reserve_mem_b == 2 * GIB
    # cpu: 2000 - 500 - 1000 = 500 free.
    assert cap.free_cpu_m() == 500
    # mem: 4Gi - 4Gi - 2Gi < 0 -> clamped to 0.
    assert cap.free_mem_b() == 0


def test_compute_capacity_all_nodes_not_ready_is_empty() -> None:
    nodes = [FakeNode(ready=False, cpu_allocatable="8", memory_allocatable="16Gi")]
    cap = compute_capacity(nodes, live_vms=[], reserve_cpu_m=0, reserve_mem_b=0)
    assert cap.total_cpu_m == 0
    assert cap.total_mem_b == 0
    assert cap.free_cpu_m() == 0
    assert cap.free_mem_b() == 0


# --------------------------------------------------------------------------- #
# plan_fits  (aggregate boundary behaviour)
# --------------------------------------------------------------------------- #


def _capacity_with_free(free_cpu_m: int, free_mem_b: int) -> Capacity:
    """Capacity whose free_* equals the given values (no used, no reserve)."""
    return Capacity(
        total_cpu_m=free_cpu_m,
        total_mem_b=free_mem_b,
        used_cpu_m=0,
        used_mem_b=0,
        reserve_cpu_m=0,
        reserve_mem_b=0,
    )


def test_plan_fits_when_capacity_exactly_matches_request() -> None:
    """A plan that needs exactly the free amount fits (<= boundary)."""
    cap = _capacity_with_free(free_cpu_m=250, free_mem_b=2 * GIB)  # a SMALL plan's request
    assert plan_fits(cap, cpu_limit="1", mem_limit="2Gi") is True


def test_plan_fits_false_when_memory_one_byte_short() -> None:
    cap = _capacity_with_free(free_cpu_m=250, free_mem_b=2 * GIB - 1)
    assert plan_fits(cap, cpu_limit="1", mem_limit="2Gi") is False


def test_plan_fits_false_when_cpu_one_milli_short() -> None:
    cap = _capacity_with_free(free_cpu_m=249, free_mem_b=2 * GIB)
    assert plan_fits(cap, cpu_limit="1", mem_limit="2Gi") is False


def test_plan_fits_false_when_capacity_empty() -> None:
    cap = _capacity_with_free(free_cpu_m=0, free_mem_b=0)
    assert plan_fits(cap, cpu_limit="1", mem_limit="2Gi") is False


# --------------------------------------------------------------------------- #
# Memory is the binding constraint for the real VM plans
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("plan", list(VM_PLAN_RESOURCES))
def test_memory_binds_before_cpu_for_each_plan(plan) -> None:
    """Because cpu_request is only a quarter of the limit, a balanced node
    (8 cores / 16Gi) always runs out of memory before CPU for every plan."""
    resources = VM_PLAN_RESOURCES[plan]
    cpu_req = cpu_request_millis(resources["cpu"])
    mem_req = mem_request_bytes(resources["memory"])

    node = FakeNode(ready=True, cpu_allocatable="8", memory_allocatable="16Gi")
    cap = compute_capacity([node], live_vms=[], reserve_cpu_m=0, reserve_mem_b=0)

    vms_by_cpu = cap.free_cpu_m() // cpu_req
    vms_by_mem = cap.free_mem_b() // mem_req
    # Memory admits strictly fewer VMs -> memory is the binding constraint.
    assert vms_by_mem < vms_by_cpu


def test_memory_is_the_sole_blocker_when_cpu_is_ample() -> None:
    """With abundant CPU but memory one byte short, only memory blocks the fit;
    granting the missing byte flips the decision to True."""
    large = VM_PLAN_RESOURCES[list(VM_PLAN_RESOURCES)[-1]]  # LARGE plan
    cpu_limit, mem_limit = large["cpu"], large["memory"]
    mem_req = mem_request_bytes(mem_limit)
    cpu_req = cpu_request_millis(cpu_limit)

    just_short = _capacity_with_free(free_cpu_m=cpu_req * 100, free_mem_b=mem_req - 1)
    exactly_enough = _capacity_with_free(free_cpu_m=cpu_req * 100, free_mem_b=mem_req)

    assert plan_fits(just_short, cpu_limit, mem_limit) is False
    assert plan_fits(exactly_enough, cpu_limit, mem_limit) is True


def test_storage_is_a_capacity_dimension():
    """Storage: configured total, live-VM disk consumed, plan_fits gates on it."""
    from types import SimpleNamespace
    nodes = [SimpleNamespace(ready=True, cpu_allocatable="16", memory_allocatable="64Gi")]
    vms = [SimpleNamespace(cpu="1", memory="2Gi", disk="20Gi"),
           SimpleNamespace(cpu="1", memory="2Gi", disk="20Gi")]
    cap = compute_capacity(
        nodes, vms, 0, 0,
        total_storage_b=parse_mem_bytes("50Gi"),
        reserve_storage_b=parse_mem_bytes("5Gi"),
    )
    # 50 total - 5 reserve - 40 used (2x20) = 5 GiB free storage.
    assert cap.free_storage_b() == parse_mem_bytes("5Gi")
    # A 5Gi-disk VM fits (cpu/mem abundant); a 10Gi-disk VM does not (storage-bound).
    assert plan_fits(cap, "1", "2Gi", "5Gi") is True
    assert plan_fits(cap, "1", "2Gi", "10Gi") is False
    # Without a disk_limit, storage never constrains (back-compat).
    assert plan_fits(cap, "1", "2Gi") is True


# --------------------------------------------------------------------------- #
# Per-node fit (multi-node fragmentation)
# --------------------------------------------------------------------------- #

from types import SimpleNamespace  # noqa: E402

from app.services.vm_capacity import (  # noqa: E402
    NodeCapacity,
    compute_node_capacities,
    fits_on_some_node,
)


def _node(name: str, cpu: str, mem: str, ready: bool = True):
    return SimpleNamespace(
        name=name, ready=ready, cpu_allocatable=cpu, memory_allocatable=mem
    )


def test_compute_node_capacities_subtracts_placed_vms_and_per_node_reserve():
    nodes = [_node("w1", "16", "16Gi"), _node("w2", "16", "16Gi")]
    # w1 hosts a 4Gi VM (request = full 4Gi mem, cpu 1//4 -> 250m); w2 is empty.
    vms_by_node = {"w1": [FakeVm(cpu="1", memory="4Gi")]}
    caps = compute_node_capacities(nodes, vms_by_node, reserve_cpu_m=1000, reserve_mem_b=2 * GIB)
    by_name = {c.name: c for c in caps}
    # w1: 16Gi - 4Gi used - 2Gi reserve = 10Gi; cpu 16000m - 250m - 1000m = 14750m.
    assert by_name["w1"].free_mem_b == 10 * GIB
    assert by_name["w1"].free_cpu_m == 14750
    # w2: 16Gi - 0 - 2Gi reserve = 14Gi.
    assert by_name["w2"].free_mem_b == 14 * GIB


def test_not_ready_node_contributes_zero():
    nodes = [_node("w1", "16", "16Gi", ready=False)]
    caps = compute_node_capacities(nodes, {}, 0, 0)
    assert caps[0].ready is False
    assert caps[0].free_cpu_m == 0 and caps[0].free_mem_b == 0


def test_fits_on_some_node_rejects_fragmentation():
    # The live incident: two nodes, 3.3Gi and 5.5Gi free, an 8Gi VM requested.
    node_caps = [
        NodeCapacity(name="w1", ready=True, free_cpu_m=15000, free_mem_b=int(3.3 * GIB)),
        NodeCapacity(name="w2", ready=True, free_cpu_m=15000, free_mem_b=int(5.5 * GIB)),
    ]
    # Aggregate free (8.8Gi) > 8Gi, but no single node fits -> reject.
    assert fits_on_some_node(node_caps, "4", "8Gi") is False
    # A 4Gi VM fits on w2.
    assert fits_on_some_node(node_caps, "2", "4Gi") is True


def test_fits_on_some_node_ignores_not_ready_and_empty():
    assert fits_on_some_node([], "1", "2Gi") is False
    node_caps = [NodeCapacity(name="w1", ready=False, free_cpu_m=99000, free_mem_b=99 * GIB)]
    assert fits_on_some_node(node_caps, "1", "2Gi") is False
