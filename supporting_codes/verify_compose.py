"""Verify HydraJob Docker Compose configuration and Phase 0 infra contracts.

Usage:
    python supporting_codes/verify_compose.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
COMPOSE_FILE = ROOT_DIR / "docker-compose.yml"
ENV_EXAMPLE = ROOT_DIR / ".env.example"

REQUIRED_SERVICES = {"postgres", "n8n", "backend", "dashboard", "ollama", "caddy"}


def run_compose_config(args: list[str]) -> str:
    """Run `docker compose ... config` and return stdout, failing on error."""
    cmd = ["docker", "compose", "--env-file", str(ENV_EXAMPLE), *args, "config"]
    result = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FAILED: {' '.join(cmd)}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(result.returncode)
    return result.stdout


def main() -> None:
    """Validate base, dev, and production compose configurations."""
    if not COMPOSE_FILE.exists():
        print(f"Missing {COMPOSE_FILE}", file=sys.stderr)
        sys.exit(1)
    if not ENV_EXAMPLE.exists():
        print(f"Missing {ENV_EXAMPLE}", file=sys.stderr)
        sys.exit(1)

    base_out = run_compose_config(["--profile", "production"])
    for service in REQUIRED_SERVICES:
        if f"\n  {service}:" not in base_out and f"  {service}:" not in base_out:
            print(f"Missing required service '{service}' in resolved config", file=sys.stderr)
            sys.exit(1)

    # Ensure Ollama port 11434 is never published publicly in resolved output.
    if "published: \"11434\"" in base_out or "published: 11434" in base_out:
        print("SECURITY VIOLATION: Ollama port 11434 must not be published", file=sys.stderr)
        sys.exit(1)

    # Validate production override if present.
    prod_file = ROOT_DIR / "docker-compose.prod.yml"
    if prod_file.exists():
        run_compose_config(["-f", "docker-compose.yml", "-f", "docker-compose.prod.yml", "--profile", "production"])

    dev_file = ROOT_DIR / "docker-compose.dev.yml"
    if dev_file.exists():
        run_compose_config(["-f", "docker-compose.yml", "-f", "docker-compose.dev.yml"])

    print("OK: Docker Compose configurations validated cleanly.")


if __name__ == "__main__":
    main()
