#!/usr/bin/env python3
"""Idempotent SHA-256 manifest for inbound materials (stdlib only)."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

STATUSES = {"raw", "parsed", "filed", "skipped", "failed"}
KINDS = {"profile_material", "jd_batch", "unknown"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": "1.0", "entries": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise ValueError("manifest must be an object with entries list")
    return data


def classify(path: Path, root: Path) -> str:
    relative = path.relative_to(root).parts
    if relative and relative[0] == "materials":
        return "profile_material"
    if relative and relative[0] == "jd-batch":
        return "jd_batch"
    return "unknown"


def scan(root: Path, manifest_path: Path) -> dict:
    manifest = load_manifest(manifest_path)
    entries = manifest["entries"]
    by_hash = {entry.get("sha256"): entry for entry in entries if entry.get("sha256")}
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != ".gitkeep"):
        digest = sha256(path)
        relative = path.relative_to(root).as_posix()
        if digest in by_hash:
            by_hash[digest]["status"] = "skipped"
            by_hash[digest]["source"] = relative
            by_hash[digest]["processed_at"] = now
            continue
        entry = {
            "source": relative,
            "sha256": digest,
            "kind": classify(path, root),
            "status": "raw",
            "produced": [],
            "affects_profile_fields": [],
            "processed_at": now,
        }
        entries.append(entry)
        by_hash[digest] = entry
    manifest["schema_version"] = "1.0"
    manifest["entries"] = entries
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["scan"])
    parser.add_argument("root", type=Path)
    parser.add_argument("--manifest", type=Path, default=Path("documents/_inbox_manifest.json"))
    args = parser.parse_args()
    manifest = scan(args.root, args.manifest)
    print(json.dumps({"entries": len(manifest["entries"]), "manifest": str(args.manifest)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
