"""Pure cluster-capacity math for the CPU/RAM admission queue.

No DB, no gRPC, no I/O -- every function here is a pure transform over
Kubernetes quantity strings, so the whole module is unit-testable in
isolation. The gateway computes free capacity itself (no orchestrator
change) by summing Ready nodes' allocatable and subtracting the
scheduling requests of live VMs plus a configurable system reserve.

Scheduling requests mirror the orchestrator's own bin-packing math
(services/orchestrator/internal/k8s/pod.go:cpuRequestFor):
    cpu_request = max(100m, floor(cpu_limit_millis / 4))
    mem_request = full memory limit (the binding constraint)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Iterable, Protocol

# Minimum scheduling request for CPU, in millicores. Mirrors the orchestrator
# floor in cpuRequestFor (services/orchestrator/internal/k8s/pod.go:85-92).
_CPU_REQUEST_FLOOR_MILLIS = 100
# The orchestrator requests a quarter of the CPU limit so VMs bin-pack.
_CPU_REQUEST_DIVISOR = 4

# Kubernetes quantity suffix -> multiplier (base unit: cores for CPU, bytes
# for memory). Binary suffixes are powers of two; the rest are powers of ten,
# including the sub-unit fractions used by CPU ("m" = milli).
_SUFFIX_MULTIPLIER: dict[str, Fraction] = {
    # Binary (power of two)
    "Ki": Fraction(1024),
    "Mi": Fraction(1024**2),
    "Gi": Fraction(1024**3),
    "Ti": Fraction(1024**4),
    "Pi": Fraction(1024**5),
    "Ei": Fraction(1024**6),
    # Decimal fractions
    "n": Fraction(1, 10**9),
    "u": Fraction(1, 10**6),
    "m": Fraction(1, 10**3),
    # Decimal (power of ten)
    "": Fraction(1),
    "k": Fraction(10**3),
    "M": Fraction(10**6),
    "G": Fraction(10**9),
    "T": Fraction(10**12),
    "P": Fraction(10**15),
    "E": Fraction(10**18),
}

# <signedNumber>[<scientific>][<suffix>], e.g. "500m", "2", "2Gi", "1.5e3".
_QUANTITY_RE = re.compile(
    r"^\s*([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)\s*([A-Za-z]*)\s*$"
)


def _parse_quantity(q: str) -> Fraction:
    """Parse a Kubernetes quantity string into an exact Fraction of base units.

    Uses Decimal for the mantissa so decimals and scientific notation stay
    exact, then Fraction so large integer byte counts never lose precision.
    """
    match = _QUANTITY_RE.match(q)
    if match is None:
        raise ValueError(f"invalid Kubernetes quantity: {q!r}")
    number, suffix = match.group(1), match.group(2)
    multiplier = _SUFFIX_MULTIPLIER.get(suffix)
    if multiplier is None:
        raise ValueError(f"unknown quantity suffix {suffix!r} in {q!r}")
    return Fraction(Decimal(number)) * multiplier


def parse_cpu_millis(q: str) -> int:
    """CPU quantity -> millicores. "500m"->500, "2"->2000, "1.5"->1500."""
    return int(_parse_quantity(q) * 1000)


def parse_mem_bytes(q: str) -> int:
    """Memory quantity -> bytes. "2Gi"->2147483648, "13000000Ki"->13312000000."""
    return int(_parse_quantity(q))


def cpu_request_millis(cpu_limit: str) -> int:
    """Scheduling CPU request in millicores for a VM with the given CPU limit.

    Mirrors the orchestrator's cpuRequestFor: integer floor of the limit's
    millicores divided by four, floored at 100m.
    """
    return max(_CPU_REQUEST_FLOOR_MILLIS, parse_cpu_millis(cpu_limit) // _CPU_REQUEST_DIVISOR)


def mem_request_bytes(mem_limit: str) -> int:
    """Scheduling memory request in bytes: the full memory limit."""
    return parse_mem_bytes(mem_limit)


class _NodeLike(Protocol):
    ready: bool
    cpu_allocatable: str
    memory_allocatable: str


# Effectively-unlimited default storage pool: when a caller does not supply a
# storage total (e.g. pure capacity math without disk), storage never constrains.
_STORAGE_UNLIMITED = 2**62


class _VmLike(Protocol):
    cpu: str
    memory: str
    # Optional: a VM's workspace disk size (plan limit). Accessed via getattr so
    # callers that only track cpu/mem still satisfy the protocol.


@dataclass(frozen=True)
class Capacity:
    """Aggregate cluster capacity snapshot, all values already reduced to
    scheduling units (CPU millicores, memory bytes, storage bytes)."""

    total_cpu_m: int
    total_mem_b: int
    used_cpu_m: int
    used_mem_b: int
    reserve_cpu_m: int
    reserve_mem_b: int
    total_storage_b: int = _STORAGE_UNLIMITED
    used_storage_b: int = 0
    reserve_storage_b: int = 0

    def free_cpu_m(self) -> int:
        return max(0, self.total_cpu_m - self.used_cpu_m - self.reserve_cpu_m)

    def free_mem_b(self) -> int:
        return max(0, self.total_mem_b - self.used_mem_b - self.reserve_mem_b)

    def free_storage_b(self) -> int:
        return max(0, self.total_storage_b - self.used_storage_b - self.reserve_storage_b)


_GIB = 1024 ** 3


def aggregate_workspace_demand_b(
    workspace_rows: Iterable[tuple[str, int]],
    live_user_plan_gb: Iterable[tuple[str, int]],
) -> int:
    """Real cluster workspace-storage demand, in bytes.

    Every user_workspaces row is a provisioned PVC that consumes disk even when
    the VM is stopped, so the base is the sum of all row capacities. On top of
    that, a LIVE user whose current plan is larger than their row (a pending
    grow) — or who has no row yet (about to be provisioned) — adds the marginal
    difference, counted once per user via their largest live plan. This closes
    the reserve-before-provision window without double-counting a plain relaunch.
    """
    rows = {uid: gb for uid, gb in workspace_rows}
    base_gb = sum(rows.values())

    live_max: dict[str, int] = {}
    for uid, plan_gb in live_user_plan_gb:
        if plan_gb:
            live_max[uid] = max(live_max.get(uid, 0), plan_gb)
    delta_gb = sum(max(0, plan_gb - rows.get(uid, 0)) for uid, plan_gb in live_max.items())

    return (base_gb + delta_gb) * _GIB


def marginal_workspace_demand_b(plan_gb: int, existing_capacity_gb: int | None) -> int:
    """Extra workspace storage a new launch needs, in bytes: the full plan size
    when the user has no PVC yet, else only the grow delta (0 for a same-plan
    relaunch, since the PVC already exists and is already counted in the pool)."""
    if existing_capacity_gb is None:
        return max(0, plan_gb) * _GIB
    return max(0, plan_gb - existing_capacity_gb) * _GIB


def compute_capacity(
    nodes: Iterable[_NodeLike],
    live_vms: Iterable[_VmLike],
    reserve_cpu_m: int,
    reserve_mem_b: int,
    *,
    total_storage_b: int = _STORAGE_UNLIMITED,
    reserve_storage_b: int = 0,
    used_storage_b: int | None = None,
) -> Capacity:
    """Sum Ready nodes' allocatable and subtract live-VM requests + reserve.

    Totals for CPU/memory come only from Ready nodes. Storage is a configured
    pool (node ephemeral-storage is not reported by ListNodes). Pass
    ``used_storage_b`` to supply the real workspace demand (see
    ``aggregate_workspace_demand_b``); when omitted, storage falls back to the
    legacy per-live-VM ``disk`` fold so pure cpu/mem callers are unaffected.
    """
    total_cpu_m = 0
    total_mem_b = 0
    for node in nodes:
        if not node.ready:
            continue
        total_cpu_m += parse_cpu_millis(node.cpu_allocatable)
        total_mem_b += parse_mem_bytes(node.memory_allocatable)

    used_cpu_m = 0
    used_mem_b = 0
    legacy_storage_b = 0
    for vm in live_vms:
        used_cpu_m += cpu_request_millis(vm.cpu)
        used_mem_b += mem_request_bytes(vm.memory)
        disk = getattr(vm, "disk", None)
        if disk:
            legacy_storage_b += parse_mem_bytes(disk)
    resolved_storage_b = used_storage_b if used_storage_b is not None else legacy_storage_b

    return Capacity(
        total_cpu_m=total_cpu_m,
        total_mem_b=total_mem_b,
        used_cpu_m=used_cpu_m,
        used_mem_b=used_mem_b,
        reserve_cpu_m=reserve_cpu_m,
        reserve_mem_b=reserve_mem_b,
        total_storage_b=total_storage_b,
        used_storage_b=resolved_storage_b,
        reserve_storage_b=reserve_storage_b,
    )


def plan_fits(cap: Capacity, cpu_limit: str, mem_limit: str, disk_limit: str | None = None) -> bool:
    """Whether a VM plan's scheduling request fits the free aggregate capacity
    (CPU, memory, and -- when ``disk_limit`` is given -- workspace storage).

    This is an AGGREGATE fit only: it does not model per-node bin-packing, so a
    plan can pass here yet fail to schedule on any single node due to
    fragmentation. Per-node placement is a documented v2 limitation.
    """
    if cpu_request_millis(cpu_limit) > cap.free_cpu_m():
        return False
    if mem_request_bytes(mem_limit) > cap.free_mem_b():
        return False
    if disk_limit and parse_mem_bytes(disk_limit) > cap.free_storage_b():
        return False
    return True
