"""Pluggable career-source adapters, registry, and onboarding inspection."""

import json
import re
from abc import ABC, abstractmethod
from html.parser import HTMLParser
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from pydantic import BaseModel, Field

from app.services.scraping.extractors import (
    ExtractedJobData,
    extract_job_from_html,
    extract_json_ld_jobs,
    extract_skills_from_text,
    html_to_plain_text,
)
from app.services.scraping.ssrf import validate_safe_url
from app.services.scraping.url_utils import canonicalize_job_url, extract_domain

_JOB_LINK_HINT_RE = re.compile(
    r"(?:/jobs?/|/careers?/|/openings?/|/positions?/|/roles?/|/requisitions?/|gh_jid=|posting)",
    re.IGNORECASE,
)
_IGNORED_LINK_TEXT = frozenset(
    {
        "home",
        "about",
        "about us",
        "privacy",
        "privacy policy",
        "terms",
        "login",
        "sign in",
        "careers",
        "all jobs",
        "back",
    }
)
_SPA_MARKER_RE = re.compile(
    r'(?:<div\s+id=["\'](?:root|app|__next)["\']\s*>\s*</div>|enable\s+javascript)',
    re.IGNORECASE,
)


class DiscoveredJobSummary(BaseModel):
    """Lightweight job listing extracted from a career source index/feed."""

    external_id: str | None = None
    title: str
    url: str
    canonical_url: str
    company: str | None = None
    location: str | None = None
    department: str | None = None
    employment_type: str | None = None
    workplace_type: str | None = None
    description: str | None = None
    posted_at: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class AdapterInspectionResult(BaseModel):
    """Result of inspecting a career-page URL and optional sample payload."""

    url: str
    canonical_url: str
    recommended_adapter: str
    detected_ats: str | None = None
    status: Literal["READY", "NEEDS_CONFIGURATION"]
    api_endpoint: str | None = None
    sample_jobs_count: int = 0
    reason: str


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[tuple[str, str]] = []
        self._href: str | None = None
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            attr_map = {k.lower(): (v or "") for k, v in attrs}
            href = attr_map.get("href", "").strip()
            if href and not href.startswith(("#", "mailto:", "tel:", "javascript:")):
                self._href = href
                self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            self.anchors.append((self._href, text))
            self._href = None
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._buf.append(data)


def _extract_anchors(html_content: str) -> list[tuple[str, str]]:
    parser = _AnchorParser()
    parser.feed(html_content)
    parser.close()
    return parser.anchors


def _try_parse_json(content: str | None) -> Any | None:
    if not content:
        return None
    stripped = content.lstrip()
    if not stripped.startswith(("{", "[")):
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def _extract_board_token(url: str, expected_hosts: tuple[str, ...]) -> str | None:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if not any(host == h or host.endswith(f".{h}") for h in expected_hosts):
        return None
    segments = [seg for seg in parts.path.split("/") if seg]
    if not segments:
        return None
    if host == "boards-api.greenhouse.io" and len(segments) >= 3 and segments[1] == "boards":
        return segments[2]
    if host == "api.lever.co" and len(segments) >= 3 and segments[1] == "postings":
        return segments[2]
    if host == "api.ashbyhq.com" and len(segments) >= 3 and segments[1] == "job-board":
        return segments[2]
    return segments[0]


def _append_page_query(url: str, page: int, param_name: str = "page") -> str:
    if page <= 1:
        return url
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    updated = [(k, v) for k, v in query if k != param_name]
    updated.append((param_name, str(page)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(updated), ""))


class JobSourceAdapter(ABC):
    """Abstract base interface for modular career-source adapters."""

    name: str
    requires_browser: bool = False

    @abstractmethod
    def can_handle(self, url: str, content: str | None = None) -> bool:
        """Return True if this adapter recognizes the URL or payload format."""

    @abstractmethod
    def parse_listings(
        self,
        content: str,
        source_url: str,
        *,
        company_name: str | None = None,
    ) -> list[DiscoveredJobSummary]:
        """Parse job openings from an index page or JSON API response."""

    @abstractmethod
    def parse_job_detail(
        self,
        content: str,
        job_url: str,
        *,
        company_name: str | None = None,
    ) -> ExtractedJobData:
        """Parse an individual job posting detail payload into ExtractedJobData."""

    def build_listing_url(
        self,
        source_url: str,
        *,
        page: int = 1,
        config: dict[str, Any] | None = None,
    ) -> str:
        """Return the listing/API URL for the given page number."""
        param_name = str((config or {}).get("page_param", "page"))
        return _append_page_query(source_url, page=page, param_name=param_name)


class GreenhouseAdapter(JobSourceAdapter):
    """Adapter for Greenhouse public job board API and hosted job pages."""

    name = "greenhouse"

    def can_handle(self, url: str, content: str | None = None) -> bool:
        host = extract_domain(url)
        if host.endswith("greenhouse.io"):
            return True
        parsed = _try_parse_json(content)
        if isinstance(parsed, dict) and isinstance(parsed.get("jobs"), list):
            jobs = parsed["jobs"]
            if jobs and isinstance(jobs[0], dict) and (
                "absolute_url" in jobs[0] or "internal_job_id" in jobs[0]
            ):
                return True
        if content and ("boards.greenhouse.io" in content or "grnhse_app" in content):
            return True
        return False

    def build_listing_url(
        self,
        source_url: str,
        *,
        page: int = 1,
        config: dict[str, Any] | None = None,
    ) -> str:
        board = (config or {}).get("board_token") or _extract_board_token(
            source_url,
            ("boards.greenhouse.io", "job-boards.greenhouse.io", "boards-api.greenhouse.io"),
        )
        if board:
            base = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
            return _append_page_query(base, page=page) if page > 1 else base
        return super().build_listing_url(source_url, page=page, config=config)

    def parse_listings(
        self,
        content: str,
        source_url: str,
        *,
        company_name: str | None = None,
    ) -> list[DiscoveredJobSummary]:
        parsed = _try_parse_json(content)
        if isinstance(parsed, dict) and isinstance(parsed.get("jobs"), list):
            results: list[DiscoveredJobSummary] = []
            for item in parsed["jobs"]:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title") or "").strip()
                raw_url = str(item.get("absolute_url") or "").strip()
                if not title or not raw_url:
                    continue
                full_url = urljoin(source_url, raw_url)
                loc_obj = item.get("location")
                location = (
                    str(loc_obj.get("name", "")).strip() or None
                    if isinstance(loc_obj, dict)
                    else (str(loc_obj).strip() or None if loc_obj else None)
                )
                depts = item.get("departments") or []
                department = (
                    str(depts[0].get("name", "")).strip() or None
                    if depts and isinstance(depts[0], dict)
                    else None
                )
                desc_html = str(item.get("content") or "")
                description = html_to_plain_text(desc_html) if desc_html else None
                results.append(
                    DiscoveredJobSummary(
                        external_id=str(item["id"]) if item.get("id") is not None else None,
                        title=title,
                        url=full_url,
                        canonical_url=canonicalize_job_url(full_url),
                        company=company_name,
                        location=location,
                        department=department,
                        description=description,
                        posted_at=str(item.get("updated_at") or "").strip() or None,
                        raw_payload=item,
                    )
                )
            return results

        return GenericHtmlAdapter().parse_listings(
            content,
            source_url,
            company_name=company_name,
        )

    def parse_job_detail(
        self,
        content: str,
        job_url: str,
        *,
        company_name: str | None = None,
    ) -> ExtractedJobData:
        parsed = _try_parse_json(content)
        if isinstance(parsed, dict) and parsed.get("title"):
            loc_obj = parsed.get("location")
            location = loc_obj.get("name") if isinstance(loc_obj, dict) else loc_obj
            desc_plain = html_to_plain_text(str(parsed.get("content") or "")) or None
            return ExtractedJobData(
                company=company_name,
                title=parsed.get("title"),
                location=location,
                description=desc_plain,
                required_skills=extract_skills_from_text(desc_plain or ""),
                application_url=parsed.get("absolute_url") or job_url,
                external_job_id=str(parsed["id"]) if parsed.get("id") is not None else None,
                extraction_method="greenhouse",
                extraction_methods_used=["greenhouse"],
                raw_metadata={"greenhouse": parsed},
            )
        extracted = extract_job_from_html(content, url=job_url)
        if company_name and not extracted.company:
            extracted.company = company_name
        return extracted


class LeverAdapter(JobSourceAdapter):
    """Adapter for Lever public postings JSON API and hosted pages."""

    name = "lever"

    def can_handle(self, url: str, content: str | None = None) -> bool:
        host = extract_domain(url)
        if host.endswith("lever.co"):
            return True
        parsed = _try_parse_json(content)
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            return "hostedUrl" in parsed[0] or "applyUrl" in parsed[0]
        return False

    def build_listing_url(
        self,
        source_url: str,
        *,
        page: int = 1,
        config: dict[str, Any] | None = None,
    ) -> str:
        company = (config or {}).get("board_token") or _extract_board_token(
            source_url,
            ("jobs.lever.co", "api.lever.co"),
        )
        if company:
            base = f"https://api.lever.co/v0/postings/{company}?mode=json"
            return _append_page_query(base, page=page, param_name="skip") if page > 1 else base
        return super().build_listing_url(source_url, page=page, config=config)

    def parse_listings(
        self,
        content: str,
        source_url: str,
        *,
        company_name: str | None = None,
    ) -> list[DiscoveredJobSummary]:
        parsed = _try_parse_json(content)
        if isinstance(parsed, list):
            results: list[DiscoveredJobSummary] = []
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("text") or item.get("title") or "").strip()
                raw_url = str(item.get("hostedUrl") or item.get("applyUrl") or "").strip()
                if not title or not raw_url:
                    continue
                full_url = urljoin(source_url, raw_url)
                categories = item.get("categories") or {}
                location = (
                    str(categories.get("location") or "").strip() or None
                    if isinstance(categories, dict)
                    else None
                )
                team = (
                    str(categories.get("team") or "").strip() or None
                    if isinstance(categories, dict)
                    else None
                )
                commitment = (
                    str(categories.get("commitment") or "").strip() or None
                    if isinstance(categories, dict)
                    else None
                )
                desc_plain = item.get("descriptionPlain") or html_to_plain_text(
                    str(item.get("description") or "")
                )
                results.append(
                    DiscoveredJobSummary(
                        external_id=str(item["id"]) if item.get("id") is not None else None,
                        title=title,
                        url=full_url,
                        canonical_url=canonicalize_job_url(full_url),
                        company=company_name,
                        location=location,
                        department=team,
                        employment_type=commitment,
                        workplace_type=str(item.get("workplaceType") or "").upper() or None,
                        description=str(desc_plain).strip() or None,
                        raw_payload=item,
                    )
                )
            return results

        return GenericHtmlAdapter().parse_listings(
            content,
            source_url,
            company_name=company_name,
        )

    def parse_job_detail(
        self,
        content: str,
        job_url: str,
        *,
        company_name: str | None = None,
    ) -> ExtractedJobData:
        parsed = _try_parse_json(content)
        if isinstance(parsed, dict) and (parsed.get("text") or parsed.get("title")):
            categories = parsed.get("categories") or {}
            desc_plain = str(
                parsed.get("descriptionPlain")
                or html_to_plain_text(str(parsed.get("description") or ""))
            ).strip() or None
            return ExtractedJobData(
                company=company_name,
                title=parsed.get("text") or parsed.get("title"),
                location=categories.get("location") if isinstance(categories, dict) else None,
                employment_type=(
                    categories.get("commitment") if isinstance(categories, dict) else None
                ),
                workplace_type=str(parsed.get("workplaceType") or "").upper() or None,
                description=desc_plain,
                required_skills=extract_skills_from_text(desc_plain or ""),
                application_url=parsed.get("applyUrl") or parsed.get("hostedUrl") or job_url,
                external_job_id=str(parsed["id"]) if parsed.get("id") is not None else None,
                extraction_method="lever",
                extraction_methods_used=["lever"],
                raw_metadata={"lever": parsed},
            )
        extracted = extract_job_from_html(content, url=job_url)
        if company_name and not extracted.company:
            extracted.company = company_name
        return extracted


class AshbyAdapter(JobSourceAdapter):
    """Adapter for Ashby public job board API and hosted pages."""

    name = "ashby"

    def can_handle(self, url: str, content: str | None = None) -> bool:
        host = extract_domain(url)
        if host.endswith("ashbyhq.com"):
            return True
        parsed = _try_parse_json(content)
        if isinstance(parsed, dict):
            jobs = parsed.get("jobs") or parsed.get("jobPostings")
            if isinstance(jobs, list) and jobs and isinstance(jobs[0], dict):
                return "jobUrl" in jobs[0] or "applyUrl" in jobs[0] or "isRemote" in jobs[0]
        return False

    def build_listing_url(
        self,
        source_url: str,
        *,
        page: int = 1,
        config: dict[str, Any] | None = None,
    ) -> str:
        board = (config or {}).get("board_token") or _extract_board_token(
            source_url,
            ("jobs.ashbyhq.com", "api.ashbyhq.com"),
        )
        if board:
            return f"https://api.ashbyhq.com/posting-api/job-board/{board}"
        return super().build_listing_url(source_url, page=page, config=config)

    def parse_listings(
        self,
        content: str,
        source_url: str,
        *,
        company_name: str | None = None,
    ) -> list[DiscoveredJobSummary]:
        parsed = _try_parse_json(content)
        if isinstance(parsed, dict):
            items = parsed.get("jobs") or parsed.get("jobPostings") or []
            if isinstance(items, list):
                results: list[DiscoveredJobSummary] = []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    title = str(item.get("title") or "").strip()
                    raw_url = str(item.get("jobUrl") or item.get("applyUrl") or "").strip()
                    if not title or not raw_url:
                        continue
                    full_url = urljoin(source_url, raw_url)
                    workplace = "REMOTE" if item.get("isRemote") is True else None
                    desc_raw = str(
                        item.get("descriptionPlain") or item.get("descriptionHtml") or ""
                    )
                    description = html_to_plain_text(desc_raw) if desc_raw else None
                    results.append(
                        DiscoveredJobSummary(
                            external_id=str(item["id"]) if item.get("id") is not None else None,
                            title=title,
                            url=full_url,
                            canonical_url=canonicalize_job_url(full_url),
                            company=company_name,
                            location=str(item.get("location") or "").strip() or None,
                            department=str(item.get("department") or "").strip() or None,
                            employment_type=str(item.get("employmentType") or "").strip() or None,
                            workplace_type=workplace,
                            description=description,
                            posted_at=str(item.get("publishedAt") or "").strip() or None,
                            raw_payload=item,
                        )
                    )
                return results

        return GenericHtmlAdapter().parse_listings(
            content,
            source_url,
            company_name=company_name,
        )

    def parse_job_detail(
        self,
        content: str,
        job_url: str,
        *,
        company_name: str | None = None,
    ) -> ExtractedJobData:
        parsed = _try_parse_json(content)
        if isinstance(parsed, dict) and parsed.get("title"):
            desc_raw = str(parsed.get("descriptionPlain") or parsed.get("descriptionHtml") or "")
            desc_plain = html_to_plain_text(desc_raw) if desc_raw else None
            return ExtractedJobData(
                company=company_name,
                title=parsed.get("title"),
                location=parsed.get("location"),
                employment_type=parsed.get("employmentType"),
                workplace_type="REMOTE" if parsed.get("isRemote") is True else None,
                description=desc_plain,
                required_skills=extract_skills_from_text(desc_plain or ""),
                application_url=parsed.get("applyUrl") or parsed.get("jobUrl") or job_url,
                external_job_id=str(parsed["id"]) if parsed.get("id") is not None else None,
                extraction_method="ashby",
                extraction_methods_used=["ashby"],
                raw_metadata={"ashby": parsed},
            )
        extracted = extract_job_from_html(content, url=job_url)
        if company_name and not extracted.company:
            extracted.company = company_name
        return extracted


class GenericJsonAdapter(JobSourceAdapter):
    """Adapter for generic public JSON job feeds."""

    name = "generic_json"

    @staticmethod
    def _extract_items(parsed: Any) -> list[dict[str, Any]]:
        if isinstance(parsed, list):
            return [x for x in parsed if isinstance(x, dict)]
        if isinstance(parsed, dict):
            for key in ("jobs", "results", "postings", "items", "data"):
                val = parsed.get(key)
                if isinstance(val, list):
                    return [x for x in val if isinstance(x, dict)]
        return []

    def can_handle(self, url: str, content: str | None = None) -> bool:
        parsed = _try_parse_json(content)
        if parsed is None:
            return url.lower().endswith(".json")
        return bool(self._extract_items(parsed))

    def parse_listings(
        self,
        content: str,
        source_url: str,
        *,
        company_name: str | None = None,
    ) -> list[DiscoveredJobSummary]:
        parsed = _try_parse_json(content)
        items = self._extract_items(parsed)
        results: list[DiscoveredJobSummary] = []
        for item in items:
            title = str(item.get("title") or item.get("name") or item.get("role") or "").strip()
            raw_url = str(
                item.get("url")
                or item.get("apply_url")
                or item.get("application_url")
                or item.get("link")
                or ""
            ).strip()
            if not title or not raw_url:
                continue
            full_url = urljoin(source_url, raw_url)
            ext_id = item.get("id") or item.get("external_id") or item.get("job_id")
            desc_raw = str(item.get("description") or "")
            results.append(
                DiscoveredJobSummary(
                    external_id=str(ext_id) if ext_id is not None else None,
                    title=title,
                    url=full_url,
                    canonical_url=canonicalize_job_url(full_url),
                    company=str(item.get("company") or company_name or "").strip() or None,
                    location=str(item.get("location") or "").strip() or None,
                    department=str(item.get("department") or "").strip() or None,
                    employment_type=str(item.get("employment_type") or "").strip() or None,
                    description=html_to_plain_text(desc_raw) if desc_raw else None,
                    raw_payload=item,
                )
            )
        return results

    def parse_job_detail(
        self,
        content: str,
        job_url: str,
        *,
        company_name: str | None = None,
    ) -> ExtractedJobData:
        parsed = _try_parse_json(content)
        if isinstance(parsed, dict):
            item = parsed.get("job") if isinstance(parsed.get("job"), dict) else parsed
            desc_raw = str(item.get("description") or "")
            desc_plain = html_to_plain_text(desc_raw) if desc_raw else None
            return ExtractedJobData(
                company=item.get("company") or company_name,
                title=item.get("title") or item.get("name"),
                location=item.get("location"),
                employment_type=item.get("employment_type"),
                workplace_type=item.get("workplace_type"),
                description=desc_plain,
                required_skills=item.get("required_skills") or extract_skills_from_text(
                    desc_plain or ""
                ),
                application_url=item.get("application_url") or item.get("url") or job_url,
                external_job_id=str(item["id"]) if item.get("id") is not None else None,
                extraction_method="generic_json",
                extraction_methods_used=["generic_json"],
                raw_metadata={"generic_json": item},
            )
        return extract_job_from_html(content, url=job_url)


class JsonLdAdapter(JobSourceAdapter):
    """Adapter for pages embedding schema.org JobPosting JSON-LD."""

    name = "json_ld"

    def can_handle(self, url: str, content: str | None = None) -> bool:
        if not content:
            return False
        return bool(extract_json_ld_jobs(content, base_url=url))

    def parse_listings(
        self,
        content: str,
        source_url: str,
        *,
        company_name: str | None = None,
    ) -> list[DiscoveredJobSummary]:
        postings = extract_json_ld_jobs(content, base_url=source_url)
        results: list[DiscoveredJobSummary] = []
        for posting in postings:
            if not posting.title:
                continue
            target_url = posting.application_url or source_url
            results.append(
                DiscoveredJobSummary(
                    external_id=posting.external_job_id,
                    title=posting.title,
                    url=target_url,
                    canonical_url=canonicalize_job_url(target_url),
                    company=posting.company or company_name,
                    location=posting.location,
                    employment_type=posting.employment_type,
                    workplace_type=posting.workplace_type,
                    description=posting.description,
                )
            )
        return results

    def parse_job_detail(
        self,
        content: str,
        job_url: str,
        *,
        company_name: str | None = None,
    ) -> ExtractedJobData:
        extracted = extract_job_from_html(content, url=job_url)
        if company_name and not extracted.company:
            extracted.company = company_name
        return extracted


class GenericHtmlAdapter(JobSourceAdapter):
    """Adapter for standard HTML career pages and job detail pages."""

    name = "generic_html"

    def can_handle(self, url: str, content: str | None = None) -> bool:
        if not content:
            return False
        if _SPA_MARKER_RE.search(content) and len(html_to_plain_text(content)) < 120:
            return False
        return bool(self.parse_listings(content, url))

    def parse_listings(
        self,
        content: str,
        source_url: str,
        *,
        company_name: str | None = None,
    ) -> list[DiscoveredJobSummary]:
        seen_urls: set[str] = set()
        results: list[DiscoveredJobSummary] = []
        for href, link_text in _extract_anchors(content):
            if not _JOB_LINK_HINT_RE.search(href):
                continue
            cleaned_text = link_text.strip()
            if len(cleaned_text) < 3 or cleaned_text.lower() in _IGNORED_LINK_TEXT:
                continue
            full_url = urljoin(source_url, href)
            try:
                canon = canonicalize_job_url(full_url)
            except ValueError:
                continue
            if canon in seen_urls:
                continue
            seen_urls.add(canon)
            results.append(
                DiscoveredJobSummary(
                    title=cleaned_text,
                    url=full_url,
                    canonical_url=canon,
                    company=company_name,
                )
            )
        return results

    def parse_job_detail(
        self,
        content: str,
        job_url: str,
        *,
        company_name: str | None = None,
    ) -> ExtractedJobData:
        extracted = extract_job_from_html(content, url=job_url)
        if company_name and not extracted.company:
            extracted.company = company_name
        return extracted


class BrowserRenderedAdapter(JobSourceAdapter):
    """Adapter for JavaScript-rendered SPA career pages requiring Playwright."""

    name = "browser_rendered"
    requires_browser = True

    def can_handle(self, url: str, content: str | None = None) -> bool:
        if not content:
            return False
        return bool(_SPA_MARKER_RE.search(content)) and len(html_to_plain_text(content)) < 150

    def parse_listings(
        self,
        content: str,
        source_url: str,
        *,
        company_name: str | None = None,
    ) -> list[DiscoveredJobSummary]:
        json_ld_listings = JsonLdAdapter().parse_listings(
            content,
            source_url,
            company_name=company_name,
        )
        if json_ld_listings:
            return json_ld_listings
        return GenericHtmlAdapter().parse_listings(
            content,
            source_url,
            company_name=company_name,
        )

    def parse_job_detail(
        self,
        content: str,
        job_url: str,
        *,
        company_name: str | None = None,
    ) -> ExtractedJobData:
        extracted = extract_job_from_html(content, url=job_url)
        if company_name and not extracted.company:
            extracted.company = company_name
        if "browser_rendered" not in extracted.extraction_methods_used:
            extracted.extraction_methods_used.append("browser_rendered")
        return extracted


ADAPTER_REGISTRY: dict[str, JobSourceAdapter] = {
    "greenhouse": GreenhouseAdapter(),
    "lever": LeverAdapter(),
    "ashby": AshbyAdapter(),
    "generic_json": GenericJsonAdapter(),
    "json_ld": JsonLdAdapter(),
    "generic_html": GenericHtmlAdapter(),
    "browser_rendered": BrowserRenderedAdapter(),
}


def get_adapter(adapter_name: str) -> JobSourceAdapter:
    """Lookup an adapter by name in ADAPTER_REGISTRY."""
    key = adapter_name.strip().lower()
    if key not in ADAPTER_REGISTRY:
        available = ", ".join(sorted(ADAPTER_REGISTRY))
        raise KeyError(f"Unknown adapter {adapter_name!r}. Available: {available}")
    return ADAPTER_REGISTRY[key]


def inspect_and_recommend_adapter(
    url: str,
    sample_content: str | None = None,
    *,
    resolve_dns: bool = False,
) -> AdapterInspectionResult:
    """Inspect a career URL (and optional sample HTML/JSON) and recommend an adapter."""
    safe_url = validate_safe_url(url, resolve_dns=resolve_dns)
    canon_url = canonicalize_job_url(safe_url)

    ats_order = ("greenhouse", "lever", "ashby")
    for ats_name in ats_order:
        adapter = ADAPTER_REGISTRY[ats_name]
        if adapter.can_handle(safe_url, sample_content):
            api_endpoint = adapter.build_listing_url(safe_url)
            sample_count = (
                len(adapter.parse_listings(sample_content, safe_url))
                if sample_content
                else 0
            )
            return AdapterInspectionResult(
                url=safe_url,
                canonical_url=canon_url,
                recommended_adapter=ats_name,
                detected_ats=ats_name,
                status="READY",
                api_endpoint=api_endpoint,
                sample_jobs_count=sample_count,
                reason=f"Detected {ats_name} ATS board; public job API adapter is ready.",
            )

    if sample_content:
        generic_json = ADAPTER_REGISTRY["generic_json"]
        if generic_json.can_handle(safe_url, sample_content):
            sample_jobs = generic_json.parse_listings(sample_content, safe_url)
            status = "READY" if sample_jobs else "NEEDS_CONFIGURATION"
            return AdapterInspectionResult(
                url=safe_url,
                canonical_url=canon_url,
                recommended_adapter="generic_json",
                detected_ats=None,
                status=status,
                api_endpoint=safe_url,
                sample_jobs_count=len(sample_jobs),
                reason=(
                    f"Detected structured JSON feed with {len(sample_jobs)} sample job(s)."
                    if sample_jobs
                    else "JSON payload detected, but job item fields need mapping."
                ),
            )

        json_ld = ADAPTER_REGISTRY["json_ld"]
        if json_ld.can_handle(safe_url, sample_content):
            sample_jobs = json_ld.parse_listings(sample_content, safe_url)
            return AdapterInspectionResult(
                url=safe_url,
                canonical_url=canon_url,
                recommended_adapter="json_ld",
                detected_ats=None,
                status="READY",
                sample_jobs_count=len(sample_jobs),
                reason=f"Detected schema.org JobPosting JSON-LD ({len(sample_jobs)} item(s)).",
            )

        browser_adapter = ADAPTER_REGISTRY["browser_rendered"]
        if browser_adapter.can_handle(safe_url, sample_content):
            return AdapterInspectionResult(
                url=safe_url,
                canonical_url=canon_url,
                recommended_adapter="browser_rendered",
                detected_ats=None,
                status="NEEDS_CONFIGURATION",
                sample_jobs_count=0,
                reason="Page appears to be a JS-rendered SPA shell; requires browser rendering.",
            )

        html_adapter = ADAPTER_REGISTRY["generic_html"]
        sample_jobs = html_adapter.parse_listings(sample_content, safe_url)
        if sample_jobs:
            return AdapterInspectionResult(
                url=safe_url,
                canonical_url=canon_url,
                recommended_adapter="generic_html",
                detected_ats=None,
                status="READY",
                sample_jobs_count=len(sample_jobs),
                reason=f"Detected {len(sample_jobs)} recognizable job link(s) in static HTML.",
            )

    return AdapterInspectionResult(
        url=safe_url,
        canonical_url=canon_url,
        recommended_adapter="generic_html",
        detected_ats=None,
        status="NEEDS_CONFIGURATION",
        sample_jobs_count=0,
        reason=(
            "Unable to automatically verify a known ATS or job listings; "
            "marked NEEDS_CONFIGURATION for manual inspection."
        ),
    )
