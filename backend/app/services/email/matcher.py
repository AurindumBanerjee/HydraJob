"""Application matching, ambiguity detection, confidence policy, and regression prevention."""

import re
from collections.abc import Iterable, Sequence
from typing import Literal

from pydantic import BaseModel, Field

from app.services.email.classifier import EmailCategory, EmailClassificationResult

ApplicationStatusType = Literal[
    "DISCOVERED",
    "TO_APPLY",
    "PREPARING",
    "APPLIED",
    "ACKNOWLEDGED",
    "UNDER_REVIEW",
    "OA_RECEIVED",
    "OA_COMPLETED",
    "TECHNICAL_TEST",
    "INTERVIEW_SCHEDULED",
    "INTERVIEW_COMPLETED",
    "FURTHER_ROUNDS",
    "OFFER_RECEIVED",
    "REJECTED",
    "WITHDRAWN",
    "CLOSED",
]

MatchDecisionType = Literal[
    "AUTO_APPLY",
    "EVENT_ONLY",
    "NEEDS_REVIEW",
    "NO_AUTO_UPDATE",
    "NO_UPDATE_REGRESSION_BLOCKED",
    "DUPLICATE_IGNORED",
]

AUTO_APPLY_CONFIDENCE_THRESHOLD = 0.90
REVIEW_CONFIDENCE_THRESHOLD = 0.70

_GENERIC_ATS_OR_MAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "outlook.com",
        "yahoo.com",
        "greenhouse.io",
        "greenhouse-mail.io",
        "hire.lever.co",
        "lever.co",
        "ashbyhq.com",
        "myworkday.com",
        "workday.com",
        "smartrecruiters.com",
        "icims.com",
        "hackerrank.com",
        "codesignal.com",
        "codility.com",
    }
)

_STAGE_RANK: dict[str, int] = {
    "DISCOVERED": 1,
    "TO_APPLY": 2,
    "PREPARING": 3,
    "APPLIED": 4,
    "ACKNOWLEDGED": 5,
    "UNDER_REVIEW": 6,
    "OA_RECEIVED": 7,
    "OA_COMPLETED": 8,
    "TECHNICAL_TEST": 9,
    "INTERVIEW_SCHEDULED": 10,
    "INTERVIEW_COMPLETED": 11,
    "FURTHER_ROUNDS": 12,
    "OFFER_RECEIVED": 13,
}

_TERMINAL_STATUSES = frozenset({"REJECTED", "WITHDRAWN", "CLOSED"})

_CATEGORY_TO_STATUS: dict[EmailCategory, str | None] = {
    EmailCategory.APPLICATION_ACKNOWLEDGEMENT: "ACKNOWLEDGED",
    EmailCategory.APPLICATION_RECEIVED: "ACKNOWLEDGED",
    EmailCategory.UNDER_REVIEW: "UNDER_REVIEW",
    EmailCategory.OA_INVITATION: "OA_RECEIVED",
    EmailCategory.ASSESSMENT_REMINDER: None,
    EmailCategory.ASSESSMENT_COMPLETED: "OA_COMPLETED",
    EmailCategory.TECHNICAL_TEST: "TECHNICAL_TEST",
    EmailCategory.INTERVIEW_INVITATION: "INTERVIEW_SCHEDULED",
    EmailCategory.INTERVIEW_RESCHEDULE: "INTERVIEW_SCHEDULED",
    EmailCategory.INTERVIEW_FEEDBACK: "INTERVIEW_COMPLETED",
    EmailCategory.NEXT_ROUND: "FURTHER_ROUNDS",
    EmailCategory.OFFER: "OFFER_RECEIVED",
    EmailCategory.REJECTION: "REJECTED",
    EmailCategory.WITHDRAWAL: "WITHDRAWN",
    EmailCategory.DOCUMENT_REQUEST: None,
    EmailCategory.INFORMATION_REQUEST: None,
    EmailCategory.NON_RECRUITMENT: None,
    EmailCategory.UNKNOWN: None,
}

_APP_REF_RE = re.compile(r"\b(?:APP|REQ|REF|JOB)-[A-Z0-9-]{3,20}\b", re.IGNORECASE)


class EmailMatchSignal(BaseModel):
    """Minimal email metadata used for matching (never stores full email body)."""

    gmail_message_id: str
    thread_id: str | None = None
    sender: str = ""
    sender_domain: str = ""
    subject: str = ""
    snippet: str = ""
    application_ref: str | None = None
    company_hint: str | None = None
    title_hint: str | None = None


class ApplicationMatchCandidate(BaseModel):
    """Candidate application record available for matching."""

    application_id: str | int
    job_id: str | int | None = None
    company_name: str
    company_domain: str | None = None
    job_title: str
    current_status: str
    thread_id: str | None = None
    application_ref: str | None = None
    is_archived: bool = False


class EmailMatchResult(BaseModel):
    """Outcome of matching a classified email against candidate applications."""

    gmail_message_id: str
    matched_application_id: str | int | None = None
    candidate_application_ids: list[str | int] = Field(default_factory=list)
    match_method: str = "unmatched"
    match_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    is_ambiguous: bool = False
    is_duplicate_message: bool = False
    proposed_status: str | None = None
    should_apply_status: bool = False
    needs_review: bool = False
    regression_blocked: bool = False
    decision: MatchDecisionType
    reason: str


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]+", " ", value.lower())).strip()


def _extract_refs(signal: EmailMatchSignal) -> set[str]:
    refs: set[str] = set()
    if signal.application_ref and signal.application_ref.strip():
        refs.add(signal.application_ref.strip().upper())
    for match in _APP_REF_RE.findall(f"{signal.subject} {signal.snippet}"):
        refs.add(match.upper())
    return refs


def _domain_matches(sender_domain: str, candidate_domain: str | None, company_name: str) -> bool:
    s_dom = sender_domain.strip().lower()
    if not s_dom or s_dom in _GENERIC_ATS_OR_MAIL_DOMAINS:
        return False
    if candidate_domain:
        c_dom = candidate_domain.strip().lower()
        if c_dom and (s_dom == c_dom or s_dom.endswith(f".{c_dom}")):
            return True
    comp_slug = re.sub(r"[^a-z0-9]+", "", company_name.lower())
    s_label = s_dom.split(".", 1)[0]
    return bool(
        comp_slug
        and len(comp_slug) >= 3
        and (comp_slug in s_label or s_label == comp_slug)
    )


def _title_similarity(email_text: str, job_title: str, title_hint: str | None = None) -> float:
    norm_job = _normalize_text(job_title)
    if not norm_job:
        return 0.0
    haystack = _normalize_text(f"{title_hint or ''} {email_text}")
    if not haystack:
        return 0.0
    if norm_job in haystack:
        return 1.0

    job_tokens = {t for t in norm_job.split() if len(t) >= 2}
    text_tokens = set(haystack.split())
    if not job_tokens:
        return 0.0
    overlap = len(job_tokens & text_tokens) / len(job_tokens)
    return round(overlap, 4)


def is_status_regression(current_status: str, target_status: str) -> bool:
    """Return True if moving current_status -> target_status would regress progress."""
    cur = current_status.strip().upper()
    tgt = target_status.strip().upper()
    if cur == tgt:
        return False

    if cur in _TERMINAL_STATUSES:
        # Never reopen or overwrite a terminal application status automatically.
        return True

    if cur == "OFFER_RECEIVED" and tgt != "WITHDRAWN":
        return True

    if tgt in _TERMINAL_STATUSES:
        return False

    cur_rank = _STAGE_RANK.get(cur)
    tgt_rank = _STAGE_RANK.get(tgt)
    if cur_rank is None or tgt_rank is None:
        return False
    return tgt_rank < cur_rank


def _apply_confidence_and_regression_policy(
    *,
    signal: EmailMatchSignal,
    classification: EmailClassificationResult,
    matched: ApplicationMatchCandidate | None,
    candidate_ids: list[str | int],
    match_method: str,
    match_confidence: float,
    is_ambiguous: bool,
) -> EmailMatchResult:
    overall_conf = round(min(classification.confidence, match_confidence), 4)
    proposed = _CATEGORY_TO_STATUS.get(classification.category)

    if is_ambiguous:
        return EmailMatchResult(
            gmail_message_id=signal.gmail_message_id,
            matched_application_id=None,
            candidate_application_ids=candidate_ids,
            match_method=match_method,
            match_confidence=match_confidence,
            overall_confidence=overall_conf,
            is_ambiguous=True,
            proposed_status=proposed,
            should_apply_status=False,
            needs_review=True,
            decision="NEEDS_REVIEW",
            reason=(
                "Multiple active applications matched at the same company; "
                "manual disambiguation required."
            ),
        )

    if matched is None:
        needs_rev = (
            classification.category not in {EmailCategory.NON_RECRUITMENT, EmailCategory.UNKNOWN}
            and classification.confidence >= REVIEW_CONFIDENCE_THRESHOLD
        )
        return EmailMatchResult(
            gmail_message_id=signal.gmail_message_id,
            matched_application_id=None,
            candidate_application_ids=[],
            match_method="unmatched",
            match_confidence=0.0,
            overall_confidence=0.0,
            is_ambiguous=False,
            proposed_status=proposed,
            should_apply_status=False,
            needs_review=needs_rev,
            decision="NO_AUTO_UPDATE",
            reason="No matching application record found.",
        )

    if overall_conf >= AUTO_APPLY_CONFIDENCE_THRESHOLD:
        if proposed is None:
            return EmailMatchResult(
                gmail_message_id=signal.gmail_message_id,
                matched_application_id=matched.application_id,
                candidate_application_ids=[matched.application_id],
                match_method=match_method,
                match_confidence=match_confidence,
                overall_confidence=overall_conf,
                proposed_status=None,
                should_apply_status=False,
                needs_review=False,
                decision="EVENT_ONLY",
                reason=(
                    f"Matched application {matched.application_id}; category "
                    f"{classification.category} records an event without status change."
                ),
            )

        if is_status_regression(matched.current_status, proposed):
            return EmailMatchResult(
                gmail_message_id=signal.gmail_message_id,
                matched_application_id=matched.application_id,
                candidate_application_ids=[matched.application_id],
                match_method=match_method,
                match_confidence=match_confidence,
                overall_confidence=overall_conf,
                proposed_status=proposed,
                should_apply_status=False,
                needs_review=True,
                regression_blocked=True,
                decision="NO_UPDATE_REGRESSION_BLOCKED",
                reason=(
                    f"Blocked backward/terminal status regression from "
                    f"{matched.current_status} to {proposed}."
                ),
            )

        return EmailMatchResult(
            gmail_message_id=signal.gmail_message_id,
            matched_application_id=matched.application_id,
            candidate_application_ids=[matched.application_id],
            match_method=match_method,
            match_confidence=match_confidence,
            overall_confidence=overall_conf,
            proposed_status=proposed,
            should_apply_status=True,
            needs_review=False,
            decision="AUTO_APPLY",
            reason=(
                f"High-confidence ({overall_conf:.2f}) unambiguous match via {match_method}; "
                f"transition {matched.current_status} -> {proposed}."
            ),
        )

    if overall_conf >= REVIEW_CONFIDENCE_THRESHOLD:
        return EmailMatchResult(
            gmail_message_id=signal.gmail_message_id,
            matched_application_id=matched.application_id,
            candidate_application_ids=[matched.application_id],
            match_method=match_method,
            match_confidence=match_confidence,
            overall_confidence=overall_conf,
            proposed_status=proposed,
            should_apply_status=False,
            needs_review=True,
            decision="NEEDS_REVIEW",
            reason=(
                f"Medium confidence ({overall_conf:.2f} in 0.70-0.89); queued for manual review."
            ),
        )

    return EmailMatchResult(
        gmail_message_id=signal.gmail_message_id,
        matched_application_id=matched.application_id,
        candidate_application_ids=[matched.application_id],
        match_method=match_method,
        match_confidence=match_confidence,
        overall_confidence=overall_conf,
        proposed_status=proposed,
        should_apply_status=False,
        needs_review=False,
        decision="NO_AUTO_UPDATE",
        reason=f"Confidence ({overall_conf:.2f}) below 0.70; no automatic update applied.",
    )


def match_email_to_applications(
    *,
    signal: EmailMatchSignal,
    classification: EmailClassificationResult,
    candidates: Sequence[ApplicationMatchCandidate],
    processed_message_ids: Iterable[str] = (),
) -> EmailMatchResult:
    """Match a classified recruitment email to an application and enforce confidence policy."""
    seen_ids = {str(mid).strip() for mid in processed_message_ids if str(mid).strip()}
    if signal.gmail_message_id in seen_ids:
        return EmailMatchResult(
            gmail_message_id=signal.gmail_message_id,
            is_duplicate_message=True,
            should_apply_status=False,
            needs_review=False,
            decision="DUPLICATE_IGNORED",
            reason=f"Duplicate message {signal.gmail_message_id} already processed.",
        )

    if classification.category == EmailCategory.NON_RECRUITMENT:
        return EmailMatchResult(
            gmail_message_id=signal.gmail_message_id,
            should_apply_status=False,
            needs_review=False,
            decision="NO_AUTO_UPDATE",
            reason="Classified as NON_RECRUITMENT; no application update.",
        )

    active_pool = [c for c in candidates if not c.is_archived]
    if not active_pool:
        return _apply_confidence_and_regression_policy(
            signal=signal,
            classification=classification,
            matched=None,
            candidate_ids=[],
            match_method="unmatched",
            match_confidence=0.0,
            is_ambiguous=False,
        )

    # 1. Exact thread_id match
    if signal.thread_id:
        thread_hits = [c for c in active_pool if c.thread_id and c.thread_id == signal.thread_id]
        if len(thread_hits) == 1:
            return _apply_confidence_and_regression_policy(
                signal=signal,
                classification=classification,
                matched=thread_hits[0],
                candidate_ids=[thread_hits[0].application_id],
                match_method="thread_id",
                match_confidence=0.99,
                is_ambiguous=False,
            )
        if len(thread_hits) > 1:
            return _apply_confidence_and_regression_policy(
                signal=signal,
                classification=classification,
                matched=None,
                candidate_ids=[c.application_id for c in thread_hits],
                match_method="thread_id",
                match_confidence=0.80,
                is_ambiguous=True,
            )

    # 2. Exact application_ref match
    email_refs = _extract_refs(signal)
    if email_refs:
        ref_hits = [
            c
            for c in active_pool
            if c.application_ref and c.application_ref.strip().upper() in email_refs
        ]
        if len(ref_hits) == 1:
            return _apply_confidence_and_regression_policy(
                signal=signal,
                classification=classification,
                matched=ref_hits[0],
                candidate_ids=[ref_hits[0].application_id],
                match_method="application_ref",
                match_confidence=0.98,
                is_ambiguous=False,
            )

    # 3. Company match (sender_domain or company_name in subject/sender/snippet/hint)
    email_text = f"{signal.sender} {signal.subject} {signal.snippet}"
    norm_email_text = _normalize_text(email_text)
    norm_company_hint = _normalize_text(signal.company_hint)

    company_matches: list[tuple[ApplicationMatchCandidate, str, float]] = []
    for cand in active_pool:
        dom_ok = _domain_matches(signal.sender_domain, cand.company_domain, cand.company_name)
        norm_comp = _normalize_text(cand.company_name)
        name_ok = bool(
            norm_comp
            and (
                re.search(rf"\b{re.escape(norm_comp)}\b", norm_email_text)
                or (norm_company_hint and norm_comp == norm_company_hint)
            )
        )
        if dom_ok and name_ok:
            company_matches.append((cand, "sender_domain+company_name", 0.96))
        elif dom_ok:
            company_matches.append((cand, "sender_domain", 0.93))
        elif name_ok:
            company_matches.append((cand, "company_name", 0.88))

    if not company_matches:
        return _apply_confidence_and_regression_policy(
            signal=signal,
            classification=classification,
            matched=None,
            candidate_ids=[],
            match_method="unmatched",
            match_confidence=0.0,
            is_ambiguous=False,
        )

    if len(company_matches) == 1:
        cand, method, comp_conf = company_matches[0]
        title_sim = _title_similarity(
            f"{signal.subject} {signal.snippet}",
            cand.job_title,
            signal.title_hint,
        )
        final_match_conf = min(0.98, comp_conf + (0.04 if title_sim >= 0.7 else 0.0))
        if title_sim >= 0.7 and method == "company_name":
            method = "company_name+job_title"
            final_match_conf = 0.94
        return _apply_confidence_and_regression_policy(
            signal=signal,
            classification=classification,
            matched=cand,
            candidate_ids=[cand.application_id],
            match_method=method,
            match_confidence=final_match_conf,
            is_ambiguous=False,
        )

    # Multiple applications exist at the matched company -> attempt disambiguation by job_title.
    scored_titles: list[tuple[float, ApplicationMatchCandidate, str, float]] = []
    for cand, method, comp_conf in company_matches:
        t_sim = _title_similarity(
            f"{signal.subject} {signal.snippet}",
            cand.job_title,
            signal.title_hint,
        )
        scored_titles.append((t_sim, cand, method, comp_conf))

    scored_titles.sort(key=lambda item: item[0], reverse=True)
    top_sim, top_cand, top_method, top_comp_conf = scored_titles[0]
    second_sim = scored_titles[1][0]

    # Disambiguate only if top title match is strong and clearly beats the runner-up.
    if top_sim >= 0.75 and (top_sim - second_sim) >= 0.25:
        final_conf = max(0.92, top_comp_conf) if top_comp_conf >= 0.88 else 0.88
        return _apply_confidence_and_regression_policy(
            signal=signal,
            classification=classification,
            matched=top_cand,
            candidate_ids=[c.application_id for _, c, _, _ in scored_titles],
            match_method=f"{top_method}+job_title",
            match_confidence=final_conf,
            is_ambiguous=False,
        )

    return _apply_confidence_and_regression_policy(
        signal=signal,
        classification=classification,
        matched=None,
        candidate_ids=[c.application_id for _, c, _, _ in scored_titles],
        match_method=top_method,
        match_confidence=0.75,
        is_ambiguous=True,
    )
