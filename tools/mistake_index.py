#!/usr/bin/env python3
"""Build a compact global index from application mistake entries."""
from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

FIELD = re.compile(r"^- `([^`]+)`: ?(.*)$")


def parse(path: Path) -> dict:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = FIELD.match(line.strip())
        if match:
            values[match.group(1)] = match.group(2).strip()
    return {"id": path.stem.removeprefix("mistake-"), "path": path, **values}


def build(root: Path, output: Path) -> None:
    entries = [parse(path) for path in sorted(root.glob("**/mistakes/mistake-*.md")) if path.resolve() != output.resolve()]
    counts = Counter(entry["id"] for entry in entries)
    lines = [
        "# Interview Mistake Index", "", "## Review Queue", "",
        "| mistake_id | domain | competency | failure_type | status | recurrence | source |",
        "|---|---|---|---|---|---:|---|",
    ]
    for entry in entries:
        relative = entry["path"].relative_to(root).as_posix()
        lines.append(f"| {entry['id']} | {entry.get('domain', 'generic')} | {entry.get('competency', '')} | {entry.get('failure_type', '')} | {entry.get('status', 'open')} | {counts[entry['id']]} | {relative} |")
    lines += ["", "## Cross-Application Patterns", "", "Recurrence is counted by stable mistake id; repeated entries should be reviewed for a shared root cause.", "", "## Quick Review Cards", ""]
    for entry in entries:
        spoken = entry.get("spoken_answer", "")
        relative = entry["path"].relative_to(root).as_posix()
        lines += [f"### {entry['id']}", f"- spoken_answer: {spoken}", "- diagram: see full entry", f"- full_entry: [{relative}]({relative})", ""]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.root, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
