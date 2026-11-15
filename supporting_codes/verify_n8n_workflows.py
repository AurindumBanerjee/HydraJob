"""Validate HydraJob n8n workflow JSON exports for schema and secret hygiene.

Usage:
    python supporting_codes/verify_n8n_workflows.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = ROOT_DIR / "n8n" / "workflows"

EXPECTED_WORKFLOWS = {
    "01_manual_job_intake.json",
    "02_scheduled_company_scans.json",
    "03_search_execution.json",
    "04_retry_and_failure_handling.json",
}

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"AIza[0-9A-Za-z\-_]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----"),
]

REQUIRED_NODE_KEYS = {"id", "name", "type", "typeVersion", "position", "parameters"}


def validate_workflow(path: Path) -> None:
    """Validate structure, connections, timezone, and secret hygiene for one workflow JSON."""
    raw = path.read_text(encoding="utf-8")
    for pattern in SECRET_PATTERNS:
        if pattern.search(raw):
            raise ValueError(f"Potential secret detected in {path.name}: {pattern.pattern}")

    data: dict[str, Any] = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: top-level JSON must be an object")

    if not data.get("name"):
        raise ValueError(f"{path.name}: missing workflow 'name'")

    if data.get("active") is not False:
        raise ValueError(f"{path.name}: exported templates must set 'active': false")

    tz = data.get("settings", {}).get("timezone")
    if tz != "Asia/Kolkata":
        raise ValueError(f"{path.name}: settings.timezone must be 'Asia/Kolkata', got {tz!r}")

    nodes = data.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError(f"{path.name}: 'nodes' must be a non-empty list")

    node_names: set[str] = set()
    for node in nodes:
        missing = REQUIRED_NODE_KEYS - set(node.keys())
        if missing:
            raise ValueError(f"{path.name}: node {node.get('name', '<unknown>')} missing {sorted(missing)}")
        if node["name"] in node_names:
            raise ValueError(f"{path.name}: duplicate node name {node['name']!r}")
        node_names.add(node["name"])

        # Ensure no raw X-API-Key header value is hardcoded inside parameters.
        params_str = json.dumps(node["parameters"])
        if "X-API-Key" in params_str and "REPLACE_WITH" not in params_str:
            raise ValueError(
                f"{path.name}: node {node['name']!r} must use n8n httpHeaderAuth credentials, not inline X-API-Key"
            )

        for cred_name, cred_info in node.get("credentials", {}).items():
            cred_id = str(cred_info.get("id", ""))
            if not cred_id.startswith("REPLACE_WITH_"):
                raise ValueError(
                    f"{path.name}: node {node['name']!r} credential {cred_name!r} has non-placeholder id {cred_id!r}"
                )

    connections = data.get("connections")
    if not isinstance(connections, dict) or not connections:
        raise ValueError(f"{path.name}: 'connections' must be a non-empty mapping")

    for src_name, outputs in connections.items():
        if src_name not in node_names:
            raise ValueError(f"{path.name}: connection source {src_name!r} not in nodes")
        for branch_list in outputs.get("main", []):
            for edge in branch_list:
                target = edge.get("node")
                if target not in node_names:
                    raise ValueError(f"{path.name}: connection target {target!r} not in nodes")


def main() -> int:
    """Validate all expected n8n workflow exports."""
    if not WORKFLOWS_DIR.exists():
        print(f"Missing directory: {WORKFLOWS_DIR}", file=sys.stderr)
        return 1

    found = {p.name for p in WORKFLOWS_DIR.glob("*.json")}
    missing = EXPECTED_WORKFLOWS - found
    if missing:
        print(f"Missing expected workflow files: {sorted(missing)}", file=sys.stderr)
        return 1

    for path in sorted(WORKFLOWS_DIR.glob("*.json")):
        validate_workflow(path)
        print(f"Validated {path.name}")

    print(f"OK: All {len(found)} n8n workflows validated cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
