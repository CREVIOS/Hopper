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


def compute_capacity(
    nodes: Iterable[_NodeLike],
    live_vms: Iterable[_VmLike],
    reserve_cpu_m: int,
    reserve_mem_b: int,
    *,
    total_storage_b: int = _STORAGE_UNLIMITED,
    reserve_storage_b: int = 0,
) -> Capacity:
    """Sum Ready nodes' allocatable and subtract live-VM requests + reserve.

    Totals for CPU/memory come only from Ready nodes. Storage is a configured
    pool (node ephemeral-storage is not reported by ListNodes): total_storage_b
    is supplied, and each live VM with a ``disk`` attribute consumes it. VMs
    without a ``disk`` attribute contribute 0 storage, so pure cpu/mem callers
    are unaffected.
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
    used_storage_b = 0
    for vm in live_vms:
        used_cpu_m += cpu_request_millis(vm.cpu)
        used_mem_b += mem_request_bytes(vm.memory)
        disk = getattr(vm, "disk", None)
        if disk:
            used_storage_b += parse_mem_bytes(disk)

    return Capacity(
        total_cpu_m=total_cpu_m,
        total_mem_b=total_mem_b,
        used_cpu_m=used_cpu_m,
        used_mem_b=used_mem_b,
        reserve_cpu_m=reserve_cpu_m,
        reserve_mem_b=reserve_mem_b,
        total_storage_b=total_storage_b,
        used_storage_b=used_storage_b,
        reserve_storage_b=reserve_storage_b,
    )


def plan_fits(cap: Capacity, cpu_limit: str, mem_limit: str, disk_limit: str | None = None) -> bool:
    """Whether a VM plan's scheduling request fits the free AGGREGATE capacity
    (CPU, memory, and -- when ``disk_limit`` is given -- workspace storage).

    Aggregate fit is necessary but not sufficient on a multi-node cluster: it
    does not model per-node bin-packing, so a plan can pass here yet fail to
    schedule because no single node has room (fragmentation). Pair it with
    :func:`fits_on_some_node`, which adds the per-node check. Storage stays an
    aggregate/logical pool (node ephemeral-storage is not reported), so it is
    only checked here.
    """
    if cpu_request_millis(cpu_limit) > cap.free_cpu_m():
        return False
    if mem_request_bytes(mem_limit) > cap.free_mem_b():
        return False
    if disk_limit and parse_mem_bytes(disk_limit) > cap.free_storage_b():
        return False
    return True


@dataclass(frozen=True)
class NodeCapacity:
    """Per-node free CPU/memory, in scheduling units. Storage is deliberately
    absent: it is a cluster-wide logical pool, checked only in ``plan_fits``."""

    name: str
    ready: bool
    free_cpu_m: int
    free_mem_b: int


def compute_node_capacities(
    nodes: Iterable[_NodeLike],
    vms_by_node: dict[str, Iterable[_VmLike]],
    reserve_cpu_m: int,
    reserve_mem_b: int,
) -> list[NodeCapacity]:
    """Free CPU/memory per Ready node.

    ``vms_by_node`` maps a node name to the VMs the gateway knows are placed
    there (live PodSessions with a recorded ``node_name``). Each node's free is
    its allocatable minus those VMs' scheduling requests minus the reserve.

    The reserve is applied PER NODE, not once cluster-wide: it stands in for the
    kube-system pods the gateway cannot see (kube-proxy, the CNI agent, ...),
    and those run on every node. This is intentionally more conservative than
    the aggregate reserve in :func:`compute_capacity`.

    VMs that are reserved but not yet placed (``node_name`` is NULL) are not in
    ``vms_by_node`` and so are not attributed to any node here. They still count
    against the aggregate via :func:`compute_capacity`, so admission as a whole
    does not over-commit; the per-node view is briefly optimistic about them
    until they schedule, which the orchestrator's Pending watchdog backstops.
    """
    result: list[NodeCapacity] = []
    for node in nodes:
        if not node.ready:
            result.append(NodeCapacity(name=node_name(node), ready=False, free_cpu_m=0, free_mem_b=0))
            continue
        total_cpu_m = parse_cpu_millis(node.cpu_allocatable)
        total_mem_b = parse_mem_bytes(node.memory_allocatable)
        used_cpu_m = 0
        used_mem_b = 0
        for vm in vms_by_node.get(node_name(node), ()):
            used_cpu_m += cpu_request_millis(vm.cpu)
            used_mem_b += mem_request_bytes(vm.memory)
        free_cpu_m = max(0, total_cpu_m - used_cpu_m - reserve_cpu_m)
        free_mem_b = max(0, total_mem_b - used_mem_b - reserve_mem_b)
        result.append(
            NodeCapacity(name=node_name(node), ready=True, free_cpu_m=free_cpu_m, free_mem_b=free_mem_b)
        )
    return result


def node_name(node: _NodeLike) -> str:
    """A node's name, tolerating node-like objects that omit it (e.g. the pure
    capacity-math tests use minimal stand-ins)."""
    return getattr(node, "name", "") or ""


def fits_on_some_node(node_caps: Iterable[NodeCapacity], cpu_limit: str, mem_limit: str) -> bool:
    """Whether at least one Ready node can hold a VM plan's CPU+memory request.

    This is the per-node (bin-packing) half of admission. It rejects the
    fragmentation case aggregate fit misses: e.g. 8Gi requested, 4Gi free on
    each of two nodes -- aggregate says yes, no single node fits, so this says
    no. When there are no nodes (orchestrator unreachable, handled fail-open by
    the caller) this returns False.
    """
    req_cpu_m = cpu_request_millis(cpu_limit)
    req_mem_b = mem_request_bytes(mem_limit)
    return any(
        nc.ready and req_cpu_m <= nc.free_cpu_m and req_mem_b <= nc.free_mem_b
        for nc in node_caps
    )
