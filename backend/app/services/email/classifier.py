"""Recruitment email classification into 18 domain categories with optional Ollama refinement."""

import re
from enum import StrEnum

from pydantic import BaseModel, Field

from app.services.llm.ollama_client import OllamaClient
from app.services.llm.prompts import PROMPT_VERSION, build_email_classification_prompt


class EmailCategory(StrEnum):
    """All 18 supported recruitment email classifications."""

    APPLICATION_ACKNOWLEDGEMENT = "APPLICATION_ACKNOWLEDGEMENT"
    APPLICATION_RECEIVED = "APPLICATION_RECEIVED"
    UNDER_REVIEW = "UNDER_REVIEW"
    OA_INVITATION = "OA_INVITATION"
    ASSESSMENT_REMINDER = "ASSESSMENT_REMINDER"
    ASSESSMENT_COMPLETED = "ASSESSMENT_COMPLETED"
    TECHNICAL_TEST = "TECHNICAL_TEST"
    INTERVIEW_INVITATION = "INTERVIEW_INVITATION"
    INTERVIEW_RESCHEDULE = "INTERVIEW_RESCHEDULE"
    INTERVIEW_FEEDBACK = "INTERVIEW_FEEDBACK"
    NEXT_ROUND = "NEXT_ROUND"
    REJECTION = "REJECTION"
    OFFER = "OFFER"
    DOCUMENT_REQUEST = "DOCUMENT_REQUEST"
    INFORMATION_REQUEST = "INFORMATION_REQUEST"
    WITHDRAWAL = "WITHDRAWAL"
    NON_RECRUITMENT = "NON_RECRUITMENT"
    UNKNOWN = "UNKNOWN"


EMAIL_CATEGORIES: tuple[str, ...] = tuple(c.value for c in EmailCategory)


class EmailClassificationResult(BaseModel):
    """Structured classification outcome with confidence and matched signals."""

    category: EmailCategory
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    matched_signals: list[str] = Field(default_factory=list)
    used_llm: bool = False
    model_name: str = "deterministic-rules-v1"


class OllamaEmailClassificationSchema(BaseModel):
    """Strict Pydantic schema for optional Ollama email classification."""

    category: EmailCategory
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


_RULE_SPECS: tuple[tuple[EmailCategory, float, tuple[str, ...], str], ...] = (
    # Check WITHDRAWAL and REJECTION early so negatives aren't misread as OFFER/NEXT_ROUND.
    (
        EmailCategory.WITHDRAWAL,
        0.95,
        (
            r"\b(?:confirm(?:ing)?\s+your\s+withdrawal|application\s+has\s+been\s+withdrawn|"
            r"withdrawn\s+your\s+application|you\s+withdrew)\b",
        ),
        "Matched application withdrawal confirmation phrasing.",
    ),
    (
        EmailCategory.REJECTION,
        0.95,
        (
            r"\b(?:regret\s+to\s+inform|not\s+(?:be\s+)?moving\s+forward|"
            r"decided\s+not\s+to\s+proceed|not\s+selected|unfortunately[^.]{0,60}"
            r"(?:other\s+candidates|not\s+advance|cannot\s+move\s+forward|position\s+has\s+been\s+filled)|"
            r"unable\s+to\s+offer|will\s+not\s+be\s+advancing)\b",
        ),
        "Matched rejection phrasing.",
    ),
    (
        EmailCategory.OFFER,
        0.96,
        (
            r"\b(?:pleased\s+to\s+(?:extend|offer)|formal\s+offer|offer\s+of\s+(?:employment|internship)|"
            r"offer\s+letter|compensation\s+package[^.]{0,40}offer)\b",
        ),
        "Matched job/internship offer phrasing.",
    ),
    (
        EmailCategory.INTERVIEW_RESCHEDULE,
        0.94,
        (
            r"\b(?:reschedul(?:e|ed|ing)\s+(?:your\s+)?interview|"
            r"interview\s+(?:has\s+been\s+)?rescheduled|"
            r"new\s+time\s+for\s+your\s+interview|updated\s+interview\s+schedule|"
            r"moved\s+your\s+interview)\b",
        ),
        "Matched interview reschedule phrasing.",
    ),
    (
        EmailCategory.NEXT_ROUND,
        0.93,
        (
            r"\b(?:invited\s+to\s+(?:the\s+)?(?:next|final|second|third|onsite)\s+round|"
            r"advanc(?:e|ed|ing)\s+to\s+(?:the\s+)?(?:next|final)\s+(?:round|stage)|"
            r"moving\s+forward\s+to\s+(?:the\s+)?(?:next|final)\s+(?:round|stage)|"
            r"next\s+round\s+of\s+interviews)\b",
        ),
        "Matched next/final round advancement phrasing.",
    ),
    (
        EmailCategory.INTERVIEW_INVITATION,
        0.94,
        (
            r"\b(?:interview\s+invitation|invite\s+you\s+to\s+(?:an?\s+)?interview|"
            r"schedule\s+(?:an?|your)\s+(?:technical\s+|phone\s+)?interview|"
            r"book\s+(?:an?\s+)?interview\s+slot|like\s+to\s+schedule\s+a\s+(?:call|interview)|"
            r"technical\s+interview\s+with)\b",
        ),
        "Matched interview invitation phrasing.",
    ),
    (
        EmailCategory.INTERVIEW_FEEDBACK,
        0.91,
        (
            r"\b(?:interview\s+feedback|thank\s+you\s+for\s+interviewing|"
            r"following\s+up\s+on\s+your\s+recent\s+interview|interview\s+debrief)\b",
        ),
        "Matched post-interview feedback phrasing.",
    ),
    (
        EmailCategory.ASSESSMENT_REMINDER,
        0.94,
        (
            r"\b(?:reminder\s*[:\-]?\s*(?:complete\s+your\s+)?(?:online\s+)?assessment|"
            r"assessment\s+reminder|coding\s+(?:test|challenge)\s+reminder|"
            r"deadline\s+(?:approaching|tomorrow|soon)[^.]{0,50}(?:assessment|hackerrank|codility|codesignal))\b",
        ),
        "Matched online assessment reminder phrasing.",
    ),
    (
        EmailCategory.ASSESSMENT_COMPLETED,
        0.93,
        (
            r"\b(?:thank\s+you\s+for\s+completing\s+(?:the\s+)?(?:online\s+)?assessment|"
            r"completed\s+(?:your|the)\s+(?:online\s+)?(?:assessment|coding\s+challenge)|"
            r"received\s+your\s+(?:online\s+)?assessment\s+submission|"
            r"assessment\s+submission\s+confirmed)\b",
        ),
        "Matched assessment completion confirmation.",
    ),
    (
        EmailCategory.OA_INVITATION,
        0.95,
        (
            r"\b(?:online\s+assessment|coding\s+assessment|oa\s+invitation|"
            r"invited\s+to\s+complete\s+(?:an?\s+)?(?:online\s+)?(?:assessment|coding\s+challenge)|"
            r"(?:hackerrank|codility|codesignal|karat)\s+(?:assessment|invitation|test|challenge))\b",
        ),
        "Matched online assessment invitation.",
    ),
    (
        EmailCategory.TECHNICAL_TEST,
        0.92,
        (
            r"\b(?:technical\s+test|take[- ]home\s+(?:assignment|project|test|exercise)|"
            r"coding\s+assignment|technical\s+assignment)\b",
        ),
        "Matched technical test or take-home assignment.",
    ),
    (
        EmailCategory.DOCUMENT_REQUEST,
        0.92,
        (
            r"\b(?:submit\s+(?:your\s+)?(?:documents|transcript|marksheet|id|resume)|"
            r"upload\s+(?:your\s+)?(?:official\s+)?(?:transcript|degree\s+certificate|documents)|"
            r"background\s+check\s+documents|document\s+verification)\b",
        ),
        "Matched recruitment document request.",
    ),
    (
        EmailCategory.INFORMATION_REQUEST,
        0.90,
        (
            r"\b(?:additional\s+information\s+required|please\s+(?:confirm|provide|share)\s+your\s+"
            r"(?:availability|graduation\s+date|cgpa|gpa|work\s+authorization|notice\s+period)|"
            r"could\s+you\s+clarify|fill\s+out\s+this\s+(?:short\s+)?form)\b",
        ),
        "Matched candidate information request.",
    ),
    (
        EmailCategory.UNDER_REVIEW,
        0.92,
        (
            r"\b(?:application\s+is\s+(?:currently\s+)?under\s+review|"
            r"currently\s+reviewing\s+your\s+application|"
            r"hiring\s+team\s+is\s+reviewing|being\s+reviewed\s+by\s+our\s+team)\b",
        ),
        "Matched application under-review update.",
    ),
    (
        EmailCategory.APPLICATION_RECEIVED,
        0.93,
        (
            r"\b(?:we\s+(?:have\s+)?received\s+your\s+application|"
            r"application\s+received|successfully\s+submitted\s+your\s+application|"
            r"your\s+application\s+(?:for\s+[^.]{1,60})?\s+has\s+been\s+submitted)\b",
        ),
        "Matched application received confirmation.",
    ),
    (
        EmailCategory.APPLICATION_ACKNOWLEDGEMENT,
        0.92,
        (
            r"\b(?:thank\s+you\s+for\s+applying|thanks\s+for\s+applying|"
            r"acknowledge\s+receipt\s+of\s+your\s+application|"
            r"thank\s+you\s+for\s+your\s+interest\s+in)\b",
        ),
        "Matched application acknowledgement phrasing.",
    ),
    (
        EmailCategory.NON_RECRUITMENT,
        0.91,
        (
            r"\b(?:verification\s+code|one[- ]time\s+password|\botp\b|password\s+reset|"
            r"order\s+confirmation|invoice\s+#|monthly\s+newsletter|"
            r"unsubscribe\s+from\s+marketing|promotional\s+offer)\b",
        ),
        "Matched non-recruitment transactional or marketing email.",
    ),
)

_WEAK_RECRUITMENT_HINTS: tuple[tuple[EmailCategory, float, str], ...] = (
    (EmailCategory.INTERVIEW_INVITATION, 0.78, "interview"),
    (EmailCategory.OA_INVITATION, 0.76, "assessment"),
    (EmailCategory.REJECTION, 0.75, "unfortunately"),
    (EmailCategory.OFFER, 0.74, "offer"),
    (EmailCategory.UNDER_REVIEW, 0.76, "reviewing"),
    (EmailCategory.APPLICATION_ACKNOWLEDGEMENT, 0.75, "applying"),
)


def classify_email(
    *,
    subject: str,
    snippet: str = "",
    sender_domain: str = "",
) -> EmailClassificationResult:
    """Deterministically classify a recruitment email into one of the 18 categories."""
    combined = f"{subject}\n{snippet}".strip()
    if not combined:
        return EmailClassificationResult(
            category=EmailCategory.UNKNOWN,
            confidence=0.25,
            rationale="Empty subject and snippet; unable to classify.",
        )

    for category, base_conf, patterns, rationale in _RULE_SPECS:
        matched: list[str] = []
        for pattern in patterns:
            found = re.search(pattern, combined, re.IGNORECASE)
            if found:
                matched.append(found.group(0).strip())
        if matched:
            return EmailClassificationResult(
                category=category,
                confidence=base_conf,
                rationale=rationale,
                matched_signals=matched,
            )

    # Secondary weak hints produce medium-confidence results (0.70-0.89 -> review queue)
    lowered = combined.lower()
    for category, weak_conf, keyword in _WEAK_RECRUITMENT_HINTS:
        if re.search(rf"\b{re.escape(keyword)}\b", lowered):
            return EmailClassificationResult(
                category=category,
                confidence=weak_conf,
                rationale=(
                    f"Weak keyword match ({keyword!r}) from {sender_domain or 'unknown domain'}; "
                    "requires human review."
                ),
                matched_signals=[keyword],
            )

    return EmailClassificationResult(
        category=EmailCategory.UNKNOWN,
        confidence=0.40,
        rationale="No deterministic recruitment pattern matched with sufficient confidence.",
    )


async def aclassify_email(
    *,
    subject: str,
    snippet: str = "",
    sender_domain: str = "",
    ollama_client: OllamaClient | None = None,
    use_ollama: bool = False,
) -> EmailClassificationResult:
    """Classify an email deterministically, with optional Ollama refinement and safe fallback."""
    deterministic = classify_email(
        subject=subject,
        snippet=snippet,
        sender_domain=sender_domain,
    )
    if not use_ollama:
        return deterministic

    client = ollama_client or OllamaClient()
    prompt_spec = build_email_classification_prompt(
        subject=subject,
        sender_domain=sender_domain,
        snippet=snippet,
        allowed_categories=EMAIL_CATEGORIES,
        version=PROMPT_VERSION,
    )

    fallback_schema = OllamaEmailClassificationSchema(
        category=deterministic.category,
        confidence=deterministic.confidence,
        rationale=deterministic.rationale,
    )
    llm_resp = await client.agenerate_structured(
        prompt=prompt_spec.user_prompt,
        system_prompt=prompt_spec.system_prompt,
        response_model=OllamaEmailClassificationSchema,
        fallback_factory=lambda: fallback_schema,
        prompt_version=prompt_spec.version,
    )

    if llm_resp.used_fallback:
        return deterministic

    return EmailClassificationResult(
        category=llm_resp.data.category,
        confidence=llm_resp.data.confidence,
        rationale=llm_resp.data.rationale,
        matched_signals=deterministic.matched_signals,
        used_llm=True,
        model_name=llm_resp.model_name,
    )
