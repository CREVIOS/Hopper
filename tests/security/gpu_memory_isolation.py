"""Fail if a fresh CUDA allocation exposes non-zero residual device memory."""

import torch


if not torch.cuda.is_available():
    raise SystemExit("CUDA is unavailable in the GPU security test pod")

size = 64 * 1024 * 1024
sample = torch.empty(size, dtype=torch.uint8, device="cuda")
nonzero = torch.count_nonzero(sample).item()
if nonzero:
    raise SystemExit(f"fresh CUDA allocation contained {nonzero} non-zero bytes")

print(f"PASS: {size} freshly allocated CUDA bytes were zeroed")

