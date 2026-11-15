"""Validate and optionally seed HydraJob company sources and job searches.

Usage:
    python supporting_codes/seed_initial_data.py
    python supporting_codes/seed_initial_data.py --apply --api-base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
COMPANY_SOURCES_PATH = ROOT_DIR / "config" / "company_sources.yaml"
JOB_SEARCHES_PATH = ROOT_DIR / "config" / "job_searches.yaml"

REQUIRED_SOURCE_FIELDS = {"name", "industry", "website", "career_url", "adapter", "verified", "active", "status"}
ALLOWED_STATUSES = {"READY", "NEEDS_CONFIGURATION", "DISABLED"}


def load_yaml(path: Path) -> dict[str, Any]:
    """Load and validate a YAML mapping file."""
    if not path.exists():
        raise FileNotFoundError(f"Missing configuration file: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML mapping at root of {path}")
    return data


def validate_configs() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load and validate seed company sources and job searches."""
    sources_doc = load_yaml(COMPANY_SOURCES_PATH)
    searches_doc = load_yaml(JOB_SEARCHES_PATH)

    sources = sources_doc.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("config/company_sources.yaml must contain a non-empty 'sources' list")

    for idx, src in enumerate(sources):
        if not isinstance(src, dict):
            raise ValueError(f"Source entry #{idx} must be a mapping")
        missing = REQUIRED_SOURCE_FIELDS - set(src.keys())
        if missing:
            raise ValueError(f"Source '{src.get('name', idx)}' missing fields: {sorted(missing)}")
        if src["status"] not in ALLOWED_STATUSES:
            raise ValueError(f"Invalid status '{src['status']}' for source '{src['name']}'")
        if not src["verified"] and src["active"]:
            raise ValueError(f"Unverified source '{src['name']}' must not have active=true")

    searches = searches_doc.get("searches")
    if not isinstance(searches, list) or not searches:
        raise ValueError("config/job_searches.yaml must contain a non-empty 'searches' list")

    for idx, search in enumerate(searches):
        if not isinstance(search, dict) or not search.get("name"):
            raise ValueError(f"Search entry #{idx} must be a mapping with a non-empty 'name'")

    return sources, searches


def api_request(
    method: str,
    url: str,
    api_key: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send an HTTP JSON request to the HydraJob FastAPI backend."""
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed ({exc.code}): {detail}") from exc


def list_all_paginated(
    base: str,
    path: str,
    api_key: str | None,
    page_size: int = 200,
) -> list[dict[str, Any]]:
    """Fetch all items across a paginated FastAPI endpoint respecting limit<=200."""
    collected: list[dict[str, Any]] = []
    offset = 0
    while True:
        sep = "&" if "?" in path else "?"
        page = api_request("GET", f"{base}{path}{sep}limit={page_size}&offset={offset}", api_key)
        items = page.get("items", [])
        collected.extend(items)
        total = int(page.get("total", len(collected)))
        if not items or len(collected) >= total:
            break
        offset += len(items)
    return collected


def seed_to_api(
    sources: list[dict[str, Any]],
    searches: list[dict[str, Any]],
    base_url: str,
    api_key: str | None,
) -> None:
    """Idempotently create companies, company sources, and job searches via FastAPI."""
    base = base_url.rstrip("/")

    existing_companies = list_all_paginated(base, "/api/v1/companies", api_key)
    company_by_name = {c["name"].strip().lower(): c for c in existing_companies}

    existing_sources = list_all_paginated(base, "/api/v1/sources", api_key)
    source_urls = {s["career_url"].rstrip("/").lower() for s in existing_sources}

    created_companies = 0
    created_sources = 0
    for src in sources:
        key = src["name"].strip().lower()
        company = company_by_name.get(key)
        if company is None:
            company = api_request(
                "POST",
                f"{base}/api/v1/companies",
                api_key,
                {
                    "name": src["name"],
                    "website": src["website"],
                    "industry": src["industry"],
                    "notes": src.get("notes"),
                },
            )
            company_by_name[key] = company
            created_companies += 1

        career_key = src["career_url"].rstrip("/").lower()
        if career_key not in source_urls:
            api_request(
                "POST",
                f"{base}/api/v1/sources",
                api_key,
                {
                    "company_id": company["id"],
                    "source_name": f"{src['name']} Careers",
                    "career_url": src["career_url"],
                    "source_type": "career_page",
                    "extraction_method": "auto",
                    "adapter_name": src["adapter"],
                    "status": src["status"],
                    "is_active": bool(src["active"]),
                },
            )
            source_urls.add(career_key)
            created_sources += 1

    existing_searches = list_all_paginated(base, "/api/v1/searches", api_key)
    search_names = {s["name"].strip().lower() for s in existing_searches}
    created_searches = 0
    for search in searches:
        if search["name"].strip().lower() not in search_names:
            api_request("POST", f"{base}/api/v1/searches", api_key, search)
            created_searches += 1

    print(
        f"Seed complete: created {created_companies} companies, "
        f"{created_sources} sources, {created_searches} searches."
    )


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Validate and seed HydraJob initial configuration.")
    parser.add_argument("--apply", action="store_true", help="Seed records into the FastAPI backend.")
    parser.add_argument(
        "--api-base-url",
        default=os.getenv("API_BASE_URL", "http://127.0.0.1:8000"),
        help="FastAPI base URL (default: API_BASE_URL or http://127.0.0.1:8000).",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("APP_API_KEY", ""),
        help="Optional X-API-Key header value (default: APP_API_KEY env var).",
    )
    args = parser.parse_args()

    sources, searches = validate_configs()
    by_industry: dict[str, int] = {}
    for src in sources:
        by_industry[src["industry"]] = by_industry.get(src["industry"], 0) + 1

    print(f"Validated {len(sources)} company sources: {by_industry}")
    print(f"Validated {len(searches)} job search configurations:")
    for search in searches:
        print(f"  - {search['name']} (active={search.get('is_active', True)}, min_score={search.get('min_match_score')})")

    if args.apply:
        seed_to_api(sources, searches, args.api_base_url, args.api_key or None)
    else:
        print("Dry-run complete. Pass --apply to seed into a running FastAPI backend.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
