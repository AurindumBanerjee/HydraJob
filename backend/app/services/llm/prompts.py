"""Versioned prompt templates for HydraJob Ollama structured inference."""

from dataclasses import dataclass

PROMPT_VERSION = "v1.0"
JOB_EXTRACTION_PROMPT_VERSION = "v1.0"
JOB_EVALUATION_PROMPT_VERSION = "v1.0"
EMAIL_CLASSIFICATION_PROMPT_VERSION = "v1.0"

_MAX_INPUT_CHARS = 12000


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """Immutable versioned system/user prompt pair."""

    version: str
    system_prompt: str
    user_prompt: str


def _truncate_text(text: str, max_chars: int = _MAX_INPUT_CHARS) -> str:
    cleaned = text.strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars] + "\n...[truncated]"


def build_job_extraction_prompt(
    text: str,
    *,
    url: str | None = None,
    version: str = JOB_EXTRACTION_PROMPT_VERSION,
) -> PromptTemplate:
    """Build a strict JSON extraction prompt that forbids fabricating unknown fields."""
    system_prompt = (
        "You are a precise structured job-data extractor. Return ONLY a single valid JSON object "
        "matching the requested fields. Never invent, guess, or infer unstated deadlines, "
        "salaries, graduation-year eligibility, degree requirements, or skills. "
        "If a field is not explicitly present in the source text, return null for scalar fields "
        "and [] for list fields."
    )
    source_line = f"Source URL: {url}\n" if url else ""
    user_prompt = (
        f"Prompt-Version: {version}\n"
        f"{source_line}"
        "Extract these JSON keys:\n"
        "- company (string|null)\n"
        "- title (string|null)\n"
        "- location (string|null)\n"
        "- country (string|null)\n"
        "- employment_type (string|null)\n"
        "- workplace_type (string|null: REMOTE|HYBRID|ONSITE|null)\n"
        "- experience_requirement (string|null)\n"
        "- graduation_year_requirement (string|null)\n"
        "- degree_requirement (string|null)\n"
        "- required_skills (array of strings)\n"
        "- preferred_skills (array of strings)\n"
        "- responsibilities (array of strings)\n"
        "- qualifications (array of strings)\n"
        "- salary (string|null)\n"
        "- currency (string|null)\n"
        "- application_deadline (string|null)\n"
        "- application_url (string|null)\n"
        "- description (string|null)\n\n"
        "Job text:\n"
        f"{_truncate_text(text)}"
    )
    return PromptTemplate(version=version, system_prompt=system_prompt, user_prompt=user_prompt)


def build_job_evaluation_prompt(
    *,
    profile_summary: str,
    job_summary: str,
    eligibility_status: str,
    version: str = JOB_EVALUATION_PROMPT_VERSION,
) -> PromptTemplate:
    """Build a structured profile-to-job scoring prompt."""
    system_prompt = (
        "You are an objective career-matching evaluator. Score each component from 0 to 100 "
        "based strictly on evidence in the candidate profile and job description. "
        "Do not exaggerate alignment or ignore missing mandatory requirements. "
        "Return ONLY valid JSON."
    )
    user_prompt = (
        f"Prompt-Version: {version}\n"
        f"Deterministic Eligibility Status: {eligibility_status}\n\n"
        f"Candidate Profile:\n{_truncate_text(profile_summary, 4000)}\n\n"
        f"Job Details:\n{_truncate_text(job_summary, 6000)}\n\n"
        "Return JSON with keys:\n"
        "- technical_score (int 0..100)\n"
        "- experience_score (int 0..100)\n"
        "- role_relevance_score (int 0..100)\n"
        "- location_score (int 0..100)\n"
        "- matched_skills (array of strings)\n"
        "- missing_skills (array of strings)\n"
        "- strengths (array of strings)\n"
        "- concerns (array of strings)\n"
        "- explanation (string)\n"
    )
    return PromptTemplate(version=version, system_prompt=system_prompt, user_prompt=user_prompt)


def build_email_classification_prompt(
    *,
    subject: str,
    sender_domain: str,
    snippet: str,
    allowed_categories: tuple[str, ...],
    version: str = EMAIL_CLASSIFICATION_PROMPT_VERSION,
) -> PromptTemplate:
    """Build a recruitment-email classification prompt without retaining raw email bodies."""
    system_prompt = (
        "You classify recruitment emails into exactly one allowed category. "
        "Use UNKNOWN if evidence is insufficient and NON_RECRUITMENT for unrelated mail. "
        "Return ONLY valid JSON."
    )
    categories_text = ", ".join(allowed_categories)
    user_prompt = (
        f"Prompt-Version: {version}\n"
        f"Allowed categories: {categories_text}\n"
        f"Sender domain: {sender_domain}\n"
        f"Subject: {_truncate_text(subject, 500)}\n"
        f"Snippet: {_truncate_text(snippet, 1000)}\n\n"
        "Return JSON with keys:\n"
        "- category (string from allowed categories)\n"
        "- confidence (float 0.0..1.0)\n"
        "- rationale (string)\n"
    )
    return PromptTemplate(version=version, system_prompt=system_prompt, user_prompt=user_prompt)
