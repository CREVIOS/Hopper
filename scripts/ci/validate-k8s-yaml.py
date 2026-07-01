#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path


TOP_LEVEL_KEYS = {"apiVersion", "kind", "metadata", "spec"}


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    seen: dict[str, int] = {}
    doc_start = 1

    for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.rstrip()
        if line.strip() == "---":
            seen = {}
            doc_start = lineno + 1
            continue
        if not line or line.startswith("#") or line[0].isspace() or ":" not in line:
            continue
        key = line.split(":", 1)[0]
        if key not in TOP_LEVEL_KEYS:
            continue
        if key in seen:
            errors.append(
                f"{path}:{lineno}: duplicate top-level key {key!r}; "
                f"missing '---' after document starting at line {doc_start}"
            )
        else:
            seen[key] = lineno

    return errors


def main(argv: list[str]) -> int:
    files = [Path(p) for p in argv[1:]]
    if not files:
        files = sorted(Path("k8s").rglob("*.yaml")) + sorted(Path("infrastructure").rglob("*.yaml"))

    errors: list[str] = []
    for path in files:
        if path.is_file():
            errors.extend(validate(path))

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
