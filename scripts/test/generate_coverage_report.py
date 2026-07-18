#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = ROOT / "tests" / "coverage" / "REPORT.md"


@dataclass
class FileCoverage:
    path: str
    covered: int
    total: int
    pct: float


@dataclass
class SuiteCoverage:
    label: str
    source: str
    status: str
    lines_pct: float | None = None
    statements_pct: float | None = None
    functions_pct: float | None = None
    branches_pct: float | None = None
    notes: str = ""
    files: list[FileCoverage] = field(default_factory=list)


def fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}%"


def fmt_ratio(covered: int, total: int) -> str:
    return f"{covered}/{total}"


def rel_path(path: Path) -> str:
    return str(path.relative_to(ROOT))


def top_lowest_files(files: list[FileCoverage], limit: int = 10) -> list[FileCoverage]:
    ranked = [file for file in files if file.total > 0]
    ranked.sort(key=lambda item: (item.pct, -item.total, item.path))
    return ranked[:limit]


def parse_python_coverage(xml_path: Path, label: str) -> SuiteCoverage:
    if not xml_path.exists():
        return SuiteCoverage(
            label=label,
            source=rel_path(xml_path),
            status="missing",
            notes="Artifact not generated yet.",
        )

    root = ET.parse(xml_path).getroot()
    files: list[FileCoverage] = []
    for class_node in root.findall(".//class"):
        filename = class_node.attrib["filename"]
        line_nodes = class_node.findall("./lines/line")
        total = len(line_nodes)
        covered = sum(1 for node in line_nodes if int(node.attrib.get("hits", "0")) > 0)
        pct = (covered / total * 100) if total else 0.0
        files.append(FileCoverage(path=filename, covered=covered, total=total, pct=pct))

    line_pct = float(root.attrib.get("line-rate", "0")) * 100
    branch_valid = int(root.attrib.get("branches-valid", "0"))
    branch_pct = float(root.attrib.get("branch-rate", "0")) * 100 if branch_valid else None
    return SuiteCoverage(
        label=label,
        source=rel_path(xml_path),
        status="available",
        lines_pct=line_pct,
        statements_pct=line_pct,
        branches_pct=branch_pct,
        notes="Cobertura XML emitted by pytest-cov.",
        files=files,
    )


def parse_frontend_coverage(json_path: Path) -> SuiteCoverage:
    if not json_path.exists():
        return SuiteCoverage(
            label="Frontend Vitest",
            source=rel_path(json_path),
            status="missing",
            notes="Artifact not generated yet.",
        )

    data = json.loads(json_path.read_text())
    total = data["total"]
    files: list[FileCoverage] = []
    for path, metrics in data.items():
        if path == "total":
            continue
        lines = metrics["lines"]
        files.append(
            FileCoverage(
                path=path,
                covered=int(lines["covered"]),
                total=int(lines["total"]),
                pct=float(lines["pct"]),
            )
        )

    return SuiteCoverage(
        label="Frontend Vitest",
        source=rel_path(json_path),
        status="available",
        lines_pct=float(total["lines"]["pct"]),
        statements_pct=float(total["statements"]["pct"]),
        functions_pct=float(total["functions"]["pct"]),
        branches_pct=float(total["branches"]["pct"]),
        notes="V8 coverage summary emitted by Vitest.",
        files=files,
    )


def parse_go_coverage(profile_path: Path) -> SuiteCoverage:
    if not profile_path.exists():
        return SuiteCoverage(
            label="Orchestrator Go",
            source=rel_path(profile_path),
            status="missing",
            notes="Artifact not generated yet.",
        )

    by_file: dict[str, list[int]] = {}
    total_statements = 0
    covered_statements = 0

    for line in profile_path.read_text().splitlines():
        if not line or line.startswith("mode:"):
            continue
        location, num_statements_text, hits_text = line.rsplit(" ", 2)
        file_path = location.split(":", 1)[0]
        num_statements = int(num_statements_text)
        hits = int(hits_text)

        covered, total = by_file.setdefault(file_path, [0, 0])
        total += num_statements
        if hits > 0:
            covered += num_statements
        by_file[file_path] = [covered, total]

        total_statements += num_statements
        if hits > 0:
            covered_statements += num_statements

    pct = (covered_statements / total_statements * 100) if total_statements else 0.0
    files = [
        FileCoverage(
            path=path,
            covered=covered,
            total=total,
            pct=(covered / total * 100) if total else 0.0,
        )
        for path, (covered, total) in by_file.items()
    ]
    return SuiteCoverage(
        label="Orchestrator Go",
        source=rel_path(profile_path),
        status="available",
        lines_pct=pct,
        statements_pct=pct,
        notes="Statement coverage derived from go coverprofile blocks.",
        files=files,
    )


def render_summary_table(suites: list[SuiteCoverage]) -> list[str]:
    lines = [
        "## Summary",
        "",
        "| Suite | Status | Lines | Statements | Functions | Branches | Source |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for suite in suites:
        lines.append(
            f"| {suite.label} | {suite.status} | {fmt_pct(suite.lines_pct)} | "
            f"{fmt_pct(suite.statements_pct)} | {fmt_pct(suite.functions_pct)} | "
            f"{fmt_pct(suite.branches_pct)} | `{suite.source}` |"
        )
    return lines


def render_artifact_status(suites: list[SuiteCoverage]) -> list[str]:
    lines = ["## Artifact Status", ""]
    for suite in suites:
        lines.append(f"- `{suite.source}`: {suite.status}. {suite.notes}")
    return lines


def render_suite_details(suite: SuiteCoverage) -> list[str]:
    lines = [f"## {suite.label}", ""]
    if suite.status != "available":
        lines.append(f"Artifact missing: `{suite.source}`.")
        return lines

    lines.extend(
        [
            f"Source: `{suite.source}`",
            "",
            f"- Lines: {fmt_pct(suite.lines_pct)}",
            f"- Statements: {fmt_pct(suite.statements_pct)}",
            f"- Functions: {fmt_pct(suite.functions_pct)}",
            f"- Branches: {fmt_pct(suite.branches_pct)}",
            "",
        ]
    )

    weakest = top_lowest_files(suite.files)
    if not weakest:
        lines.append("No file-level data available.")
        return lines

    lines.extend(
        [
            "### Lowest-Covered Files",
            "",
            "| File | Covered | Coverage |",
            "|---|---:|---:|",
        ]
    )
    for file in weakest:
        lines.append(f"| `{file.path}` | {fmt_ratio(file.covered, file.total)} | {fmt_pct(file.pct)} |")
    return lines


def build_report(suites: list[SuiteCoverage]) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    lines = [
        "# Coverage Report",
        "",
        f"Generated from local coverage artifacts on {generated_at}.",
        "",
    ]
    lines.extend(render_summary_table(suites))
    lines.extend(["", *render_artifact_status(suites), ""])
    for suite in suites:
        lines.extend(render_suite_details(suite))
        lines.append("")

    lines.extend(
        [
            "## Refresh",
            "",
            "Regenerate coverage artifacts and rebuild this report:",
            "",
            "```bash",
            "./scripts/test/run.sh test-coverage",
            "```",
            "",
            "Rebuild this report only from existing artifacts:",
            "",
            "```bash",
            "./scripts/test/run.sh test-coverage-report",
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    suites = [
        parse_python_coverage(ROOT / "coverage" / "python" / "unit.xml", "API unit pytest"),
        parse_python_coverage(ROOT / "coverage" / "python" / "integration.xml", "API integration pytest"),
        parse_frontend_coverage(ROOT / "coverage" / "frontend" / "coverage-summary.json"),
        parse_go_coverage(ROOT / "coverage" / "orchestrator" / "orchestrator.out"),
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(build_report(suites))
    print(f"Wrote {REPORT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
