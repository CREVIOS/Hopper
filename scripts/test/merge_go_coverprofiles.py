#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print("usage: merge_go_coverprofiles.py <out> <in1> <in2> [inN...]", file=sys.stderr)
        return 2

    out_path = Path(argv[1])
    in_paths = [Path(arg) for arg in argv[2:]]
    mode = "atomic"
    merged: dict[str, int] = {}

    for path in in_paths:
        for line in path.read_text().splitlines():
            if not line:
                continue
            if line.startswith("mode:"):
                mode = line.split(":", 1)[1].strip()
                continue
            left, hits_text = line.rsplit(" ", 1)
            hits = int(hits_text)
            merged[left] = max(merged.get(left, 0), hits)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as handle:
        handle.write(f"mode: {mode}\n")
        for left, hits in merged.items():
            handle.write(f"{left} {hits}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
