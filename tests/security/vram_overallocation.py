"""Attempt to commit more CUDA memory than the assigned device exposes."""

import torch


if not torch.cuda.is_available():
    raise SystemExit("CUDA unavailable")

free_bytes, total_bytes = torch.cuda.mem_get_info()
# Touch the allocation so CUDA cannot satisfy it through lazy virtual memory.
allocation = torch.empty(total_bytes + 256 * 1024 * 1024, dtype=torch.uint8, device="cuda")
allocation.fill_(1)
raise SystemExit(
    f"security failure: committed {allocation.numel()} bytes with only {free_bytes} free"
)
