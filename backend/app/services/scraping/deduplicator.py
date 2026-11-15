"""Job deduplication logic preventing false merges across unrelated roles."""

import difflib
import re
from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.services.scraping.url_utils import canonicalize_job_url

_LEGAL_SUFFIX_RE = re.compile(
    r"\b(?:inc(?:orporated)?|llc|ltd|limited|corp(?:oration)?|pvt|plc|gmbh|co)\b\.?",
    re.IGNORECASE,
)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9\s]+")
_WHITESPACE_RE = re.compile(r"\s+")

_LOCATION_ALIASES = {
    "bangalore": "bengaluru",
    "bengaluru": "bengaluru",
    "nyc": "new york",
    "new york city": "new york",
    "sf": "san francisco",
}


def normalize_company_name(name: str | None) -> str:
    """Normalize company names conservatively while preserving core identity."""
    if not name:
        return ""
    cleaned = _LEGAL_SUFFIX_RE.sub("", name.lower())
    cleaned = _NON_ALNUM_RE.sub(" ", cleaned)
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def normalize_job_title(title: str | None) -> str:
    """Normalize job title whitespace and punctuation without erasing seniority levels."""
    if not title:
        return ""
    cleaned = _NON_ALNUM_RE.sub(" ", title.lower())
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def normalize_location(location: str | None) -> str:
    """Normalize location string and city aliases while keeping distinct cities separate."""
    if not location:
        return ""
    cleaned = _NON_ALNUM_RE.sub(" ", location.lower())
    collapsed = _WHITESPACE_RE.sub(" ", cleaned.strip())
    for alias, canonical in _LOCATION_ALIASES.items():
        collapsed = re.sub(rf"\b{re.escape(alias)}\b", canonical, collapsed)
    return _WHITESPACE_RE.sub(" ", collapsed).strip()


def compute_description_similarity(desc_a: str | None, desc_b: str | None) -> float:
    """Compute bounded [0.0, 1.0] similarity between two job descriptions."""
    norm_a = _WHITESPACE_RE.sub(" ", (desc_a or "").lower()).strip()
    norm_b = _WHITESPACE_RE.sub(" ", (desc_b or "").lower()).strip()
    if not norm_a or not norm_b:
        return 0.0
    if norm_a == norm_b:
        return 1.0

    seq_ratio = difflib.SequenceMatcher(None, norm_a[:4000], norm_b[:4000]).ratio()
    tokens_a = set(re.findall(r"[a-z0-9]{2,}", norm_a))
    tokens_b = set(re.findall(r"[a-z0-9]{2,}", norm_b))
    if not tokens_a or not tokens_b:
        return round(seq_ratio, 4)
    jaccard = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
    return round(0.5 * seq_ratio + 0.5 * jaccard, 4)


class ExistingJobFingerprint(BaseModel):
    """Lightweight representation of an existing job record for deduplication."""

    job_id: str | int
    canonical_url: str | None = None
    source_type: str | None = None
    external_id: str | None = None
    source_references: list[tuple[str, str]] = Field(default_factory=list)
    company: str | None = None
    normalized_company: str | None = None
    title: str | None = None
    normalized_title: str | None = None
    location: str | None = None
    normalized_location: str | None = None
    description: str | None = None


class DedupDecision(BaseModel):
    """Outcome of checking a candidate job against existing records."""

    is_duplicate: bool
    matched_job_id: str | int | None = None
    match_reason: Literal["canonical_url", "source_external_id", "composite_metadata", "no_match"]
    similarity_score: float = 0.0
    should_add_source_reference: bool = False
    should_update_existing: bool = False
    details: str = ""


def _coerce_fingerprint(item: ExistingJobFingerprint | dict[str, Any]) -> ExistingJobFingerprint:
    if isinstance(item, ExistingJobFingerprint):
        return item
    return ExistingJobFingerprint.model_validate(item)


def _safe_canonical(url: str | None) -> str | None:
    if not url or not url.strip():
        return None
    try:
        return canonicalize_job_url(url)
    except ValueError:
        return url.strip().lower().rstrip("/")


def compute_dedup_decision(
    *,
    canonical_url: str | None = None,
    source_type: str | None = None,
    external_id: str | None = None,
    company: str | None = None,
    title: str | None = None,
    location: str | None = None,
    description: str | None = None,
    existing_jobs: Sequence[ExistingJobFingerprint | dict[str, Any]] = (),
    description_similarity_threshold: float = 0.65,
) -> DedupDecision:
    """Decide whether an incoming job matches an existing job without false title-only merges."""
    records = [_coerce_fingerprint(job) for job in existing_jobs]
    target_canon_url = _safe_canonical(canonical_url)
    target_source = source_type.strip().lower() if source_type else None
    target_ext_id = external_id.strip() if external_id else None

    # 1. Exact canonical URL match
    if target_canon_url:
        for rec in records:
            rec_canon = _safe_canonical(rec.canonical_url)
            if rec_canon and rec_canon == target_canon_url:
                return DedupDecision(
                    is_duplicate=True,
                    matched_job_id=rec.job_id,
                    match_reason="canonical_url",
                    similarity_score=1.0,
                    should_add_source_reference=bool(target_source and target_ext_id),
                    should_update_existing=True,
                    details=f"Matched existing job {rec.job_id} by canonical URL.",
                )

    # 2. Exact (source_type, external_id) match
    if target_source and target_ext_id:
        for rec in records:
            refs: list[tuple[str, str]] = [
                (src.strip().lower(), ext.strip())
                for src, ext in rec.source_references
                if src and ext
            ]
            if rec.source_type and rec.external_id:
                refs.append((rec.source_type.strip().lower(), rec.external_id.strip()))
            if (target_source, target_ext_id) in refs:
                return DedupDecision(
                    is_duplicate=True,
                    matched_job_id=rec.job_id,
                    match_reason="source_external_id",
                    similarity_score=1.0,
                    should_add_source_reference=False,
                    should_update_existing=True,
                    details=(
                        f"Matched existing job {rec.job_id} by "
                        f"({target_source}, {target_ext_id})."
                    ),
                )

    # 3. Composite (normalized_company, normalized_title, normalized_location) + description check
    norm_company = normalize_company_name(company)
    norm_title = normalize_job_title(title)
    norm_location = normalize_location(location)

    if norm_company and norm_title and norm_location:
        for rec in records:
            rec_company = rec.normalized_company or normalize_company_name(rec.company)
            rec_title = rec.normalized_title or normalize_job_title(rec.title)
            rec_location = rec.normalized_location or normalize_location(rec.location)

            if not (rec_company and rec_title and rec_location):
                continue
            if (norm_company, norm_title, norm_location) != (rec_company, rec_title, rec_location):
                continue

            has_both_descriptions = bool(
                (description or "").strip() and (rec.description or "").strip()
            )
            if has_both_descriptions:
                sim = compute_description_similarity(description, rec.description)
                if sim < description_similarity_threshold:
                    continue
                return DedupDecision(
                    is_duplicate=True,
                    matched_job_id=rec.job_id,
                    match_reason="composite_metadata",
                    similarity_score=sim,
                    should_add_source_reference=True,
                    should_update_existing=True,
                    details=(
                        f"Matched existing job {rec.job_id} by composite metadata "
                        f"with description similarity {sim:.2f}."
                    ),
                )

    return DedupDecision(
        is_duplicate=False,
        matched_job_id=None,
        match_reason="no_match",
        similarity_score=0.0,
        should_add_source_reference=False,
        should_update_existing=False,
        details="No matching existing job found.",
    )
