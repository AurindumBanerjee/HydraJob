"""Mandatory eligibility evaluator with strict anti-false-certainty rules."""

import re
from typing import Literal

from pydantic import BaseModel, Field

EligibilityStatus = Literal["ELIGIBLE", "UNCERTAIN", "INELIGIBLE", "NOT_EVALUATED"]
ConditionStatus = Literal["PASS", "FAIL", "UNCERTAIN", "NOT_SPECIFIED"]

_CITY_ALIASES = {
    "bangalore": "bengaluru",
    "bengaluru": "bengaluru",
    "bombay": "mumbai",
    "gurgaon": "gurugram",
    "nyc": "new york",
    "sf": "san francisco",
}

_GRAD_YEAR_TEXT_RE = re.compile(
    r"(?:class\s+of|batch(?:\s+of)?|graduating(?:\s+in)?|graduation\s+year|"
    r"passing\s+out|passout)\s*[:\-]?\s*(202[3-9]|203[0-5])"
    r"(?:\s*(?:/|,|or|and)\s*(202[3-9]|203[0-5]))?",
    re.IGNORECASE,
)
_EXPERIENCE_YEARS_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:\+|-\s*(\d+(?:\.\d+)?))?\s*(?:years?|yrs?)"
    r"(?:\s+of)?(?:\s+(?:full[- ]time|relevant|industry|professional|software|ml|ai))?"
    r"\s*experience",
    re.IGNORECASE,
)
_EXPERIENCE_SIMPLE_RE = re.compile(
    r"(?:minimum|min\.?|at\s+least)?\s*(\d+(?:\.\d+)?)\s*(?:\+|-\s*(\d+(?:\.\d+)?))?\s*"
    r"(?:years?|yrs?)",
    re.IGNORECASE,
)
_CGPA_RE = re.compile(
    r"(?:min(?:imum)?\s+)?(?:c?gpa)\s*(?:of|>=|:)?\s*(\d+(?:\.\d+)?)(?:\s*/\s*(\d+(?:\.\d+)?))?",
    re.IGNORECASE,
)


class ProfileSnapshot(BaseModel):
    """Pure domain representation of the candidate profile for matching."""

    name: str | None = None
    degree: str | None = None
    branch: str | None = None
    university: str | None = None
    graduation_year: int | None = None
    cgpa: float | None = None
    cgpa_scale: float = 10.0
    experience_years: float | None = 0.0
    experience_summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    preferred_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    excluded_locations: list[str] = Field(default_factory=list)
    work_authorizations: list[str] = Field(default_factory=list)
    requires_sponsorship: bool | None = None


class ResumeSnapshot(BaseModel):
    """Pure domain representation of a resume version."""

    id: str | int | None = None
    name: str
    skills: list[str] = Field(default_factory=list)
    extracted_text: str | None = None
    is_preferred: bool = False
    is_active: bool = True


class JobRequirementsSnapshot(BaseModel):
    """Pure domain representation of a job posting for eligibility & relevance scoring."""

    job_id: str | int | None = None
    title: str
    company: str | None = None
    description: str | None = None
    location: str | None = None
    country: str | None = None
    employment_type: str | None = None
    workplace_type: str | None = None
    experience_requirement: str | None = None
    min_experience_years: float | None = None
    max_experience_years: float | None = None
    graduation_year_requirement: str | int | list[int] | None = None
    degree_requirement: str | None = None
    min_cgpa: float | None = None
    min_cgpa_scale: float = 10.0
    work_authorization_requirement: str | None = None
    sponsorship_available: bool | None = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    qualifications: list[str] = Field(default_factory=list)


class ConditionCheckResult(BaseModel):
    """Outcome for a single mandatory eligibility condition."""

    condition: str
    status: ConditionStatus
    required_value: str | None = None
    candidate_value: str | None = None
    reason: str


class EligibilityResult(BaseModel):
    """Aggregate eligibility evaluation across all mandatory conditions."""

    status: EligibilityStatus
    checks: list[ConditionCheckResult]
    passed_conditions: list[str] = Field(default_factory=list)
    failed_conditions: list[str] = Field(default_factory=list)
    uncertain_conditions: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    summary: str


def _combined_job_text(job: JobRequirementsSnapshot) -> str:
    parts = [
        job.title or "",
        job.description or "",
        job.experience_requirement or "",
        job.degree_requirement or "",
        job.work_authorization_requirement or "",
        " ".join(job.qualifications),
    ]
    return "\n".join(p for p in parts if p).strip()


def _normalize_loc_token(value: str) -> str:
    lowered = re.sub(r"[^a-z0-9\s]+", " ", value.lower()).strip()
    for alias, canonical in _CITY_ALIASES.items():
        lowered = re.sub(rf"\b{re.escape(alias)}\b", canonical, lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _check_graduation_year(
    profile: ProfileSnapshot,
    job: JobRequirementsSnapshot,
    combined_text: str,
) -> ConditionCheckResult:
    allowed_years: set[int] = set()
    min_year: int | None = None
    req_display: str | None = None

    raw = job.graduation_year_requirement
    if isinstance(raw, int):
        allowed_years.add(raw)
        req_display = str(raw)
    elif isinstance(raw, list):
        allowed_years.update(int(y) for y in raw)
        req_display = ", ".join(str(y) for y in sorted(allowed_years))
    elif isinstance(raw, str) and raw.strip():
        req_display = raw.strip()
        years = [int(m) for m in re.findall(r"\b(202[3-9]|203[0-5])\b", raw)]
        if ("or later" in raw.lower() or "+" in raw or ">=" in raw) and years:
            min_year = min(years)
        else:
            allowed_years.update(years)
    else:
        match = _GRAD_YEAR_TEXT_RE.search(combined_text)
        if match:
            req_display = match.group(0).strip()
            for grp in match.groups():
                if grp:
                    allowed_years.add(int(grp))

    if not req_display and not allowed_years and min_year is None:
        return ConditionCheckResult(
            condition="graduation_year",
            status="NOT_SPECIFIED",
            candidate_value=str(profile.graduation_year) if profile.graduation_year else None,
            reason="Job does not state a graduation year requirement.",
        )

    if profile.graduation_year is None:
        return ConditionCheckResult(
            condition="graduation_year",
            status="UNCERTAIN",
            required_value=req_display,
            candidate_value=None,
            reason=(
                "Job specifies a graduation year requirement, "
                "but candidate graduation year is missing."
            ),
        )

    cand_str = str(profile.graduation_year)
    if min_year is not None:
        if profile.graduation_year >= min_year:
            return ConditionCheckResult(
                condition="graduation_year",
                status="PASS",
                required_value=req_display,
                candidate_value=cand_str,
                reason=f"Candidate graduation year {cand_str} meets >= {min_year}.",
            )
        return ConditionCheckResult(
            condition="graduation_year",
            status="FAIL",
            required_value=req_display,
            candidate_value=cand_str,
            reason=f"Candidate graduation year {cand_str} is earlier than required {min_year}.",
        )

    if allowed_years:
        if profile.graduation_year in allowed_years:
            return ConditionCheckResult(
                condition="graduation_year",
                status="PASS",
                required_value=req_display,
                candidate_value=cand_str,
                reason=f"Candidate graduation year {cand_str} matches {sorted(allowed_years)}.",
            )
        return ConditionCheckResult(
            condition="graduation_year",
            status="FAIL",
            required_value=req_display,
            candidate_value=cand_str,
            reason=(
                f"Job requires graduation year {sorted(allowed_years)}, "
                f"candidate is {cand_str}."
            ),
        )

    return ConditionCheckResult(
        condition="graduation_year",
        status="UNCERTAIN",
        required_value=req_display,
        candidate_value=cand_str,
        reason="Graduation year text could not be parsed cleanly.",
    )


def _degree_level(text: str) -> set[str]:
    lowered = text.lower()
    levels: set[str] = set()
    if re.search(
        r"\b(?:b\.?\s?tech|btech|b\.?\s?e\.?|bachelor|b\.?\s?s\.?|b\.?\s?sc|undergrad)\b",
        lowered,
    ):
        levels.add("bachelor")
    if re.search(
        r"\b(?:m\.?\s?tech|mtech|m\.?\s?e\.?|master|m\.?\s?s\.?|m\.?\s?sc|mba)\b",
        lowered,
    ):
        levels.add("master")
    if re.search(r"\b(?:ph\.?\s?d|doctorate|doctoral)\b", lowered):
        levels.add("phd")
    return levels


def _extract_degree_text(job: JobRequirementsSnapshot, combined_text: str) -> str | None:
    if job.degree_requirement and job.degree_requirement.strip():
        return job.degree_requirement.strip()
    degree_keywords = (
        "b.tech",
        "btech",
        "bachelor",
        "master",
        "m.tech",
        "phd",
        "ph.d",
        "degree",
    )
    for line in combined_text.splitlines():
        lowered = line.lower()
        if any(k in lowered for k in degree_keywords):
            if "preferred" in lowered and "required" not in lowered and "must" not in lowered:
                continue
            return line.strip()
    return None


def _check_degree_branch(
    profile: ProfileSnapshot,
    job: JobRequirementsSnapshot,
    combined_text: str,
) -> ConditionCheckResult:
    req_text = _extract_degree_text(job, combined_text)
    if not req_text:
        return ConditionCheckResult(
            condition="degree_branch",
            status="NOT_SPECIFIED",
            candidate_value=" ".join(p for p in (profile.degree, profile.branch) if p) or None,
            reason="Job does not state an explicit mandatory degree or branch requirement.",
        )

    cand_text = " ".join(p for p in (profile.degree, profile.branch) if p).strip()
    if not cand_text:
        return ConditionCheckResult(
            condition="degree_branch",
            status="UNCERTAIN",
            required_value=req_text,
            candidate_value=None,
            reason="Job specifies a degree requirement, but candidate degree/branch is missing.",
        )

    req_levels = _degree_level(req_text)
    cand_levels = _degree_level(cand_text)
    req_lower = req_text.lower()
    cand_lower = cand_text.lower()

    if req_levels and cand_levels and not (req_levels & cand_levels):
        # Candidate with B.Tech fails Master's-only or PhD-only mandatory requirement.
        return ConditionCheckResult(
            condition="degree_branch",
            status="FAIL",
            required_value=req_text,
            candidate_value=cand_text,
            reason=(
                f"Required degree level ({sorted(req_levels)}) "
                f"does not match candidate ({sorted(cand_levels)})."
            ),
        )

    # Check explicit non-CS branch exclusivity (e.g. Mechanical/Civil/MBA Finance).
    exclusive_non_cs = (
        "mechanical",
        "civil engineering",
        "chemical engineering",
        "biotech",
        "medical",
        "mbbs",
        "law",
    )
    cs_terms = (
        "computer science",
        "cse",
        "cs",
        "software",
        "ai",
        "data science",
        "machine learning",
        "it",
        "information technology",
        "engineering",
        "stem",
        "technical",
    )
    if any(term in req_lower for term in exclusive_non_cs) and not any(
        term in req_lower for term in cs_terms
    ):
        if not any(term in cand_lower for term in exclusive_non_cs):
            return ConditionCheckResult(
                condition="degree_branch",
                status="FAIL",
                required_value=req_text,
                candidate_value=cand_text,
                reason="Required academic branch does not match candidate branch.",
            )

    if (req_levels and cand_levels and (req_levels & cand_levels)) or any(
        term in req_lower for term in cs_terms
    ):
        return ConditionCheckResult(
            condition="degree_branch",
            status="PASS",
            required_value=req_text,
            candidate_value=cand_text,
            reason="Candidate degree and branch satisfy the stated academic requirement.",
        )

    return ConditionCheckResult(
        condition="degree_branch",
        status="UNCERTAIN",
        required_value=req_text,
        candidate_value=cand_text,
        reason="Degree requirement is ambiguous relative to candidate credentials.",
    )


def _normalize_cgpa(value: float, scale: float) -> float:
    if scale <= 0:
        return value
    return (value / scale) * 10.0


def _check_min_cgpa(
    profile: ProfileSnapshot,
    job: JobRequirementsSnapshot,
    combined_text: str,
) -> ConditionCheckResult:
    req_cgpa = job.min_cgpa
    req_scale = job.min_cgpa_scale
    req_display: str | None = None

    if req_cgpa is not None:
        req_display = f"{req_cgpa}/{req_scale:g}"
    else:
        match = _CGPA_RE.search(combined_text)
        if match:
            req_cgpa = float(match.group(1))
            if match.group(2):
                req_scale = float(match.group(2))
            else:
                req_scale = 4.0 if req_cgpa <= 4.0 else 10.0
            req_display = f"{req_cgpa}/{req_scale:g}"

    if req_cgpa is None:
        cand_cgpa_str = (
            f"{profile.cgpa}/{profile.cgpa_scale:g}" if profile.cgpa is not None else None
        )
        return ConditionCheckResult(
            condition="min_cgpa",
            status="NOT_SPECIFIED",
            candidate_value=cand_cgpa_str,
            reason="Job does not state a minimum CGPA requirement.",
        )

    if profile.cgpa is None:
        return ConditionCheckResult(
            condition="min_cgpa",
            status="UNCERTAIN",
            required_value=req_display,
            candidate_value=None,
            reason="Job specifies a minimum CGPA, but candidate CGPA is not provided.",
        )

    cand_norm = _normalize_cgpa(profile.cgpa, profile.cgpa_scale)
    req_norm = _normalize_cgpa(req_cgpa, req_scale)
    cand_display = f"{profile.cgpa}/{profile.cgpa_scale:g}"

    if cand_norm + 1e-6 >= req_norm:
        return ConditionCheckResult(
            condition="min_cgpa",
            status="PASS",
            required_value=req_display,
            candidate_value=cand_display,
            reason=f"Candidate CGPA {cand_display} meets minimum {req_display}.",
        )
    return ConditionCheckResult(
        condition="min_cgpa",
        status="FAIL",
        required_value=req_display,
        candidate_value=cand_display,
        reason=f"Candidate CGPA {cand_display} is below required {req_display}.",
    )


def _parse_experience_bounds(
    job: JobRequirementsSnapshot,
    combined_text: str,
) -> tuple[float | None, float | None, str | None]:
    if job.min_experience_years is not None or job.max_experience_years is not None:
        parts = []
        if job.min_experience_years is not None:
            parts.append(f"min {job.min_experience_years:g} yrs")
        if job.max_experience_years is not None:
            parts.append(f"max {job.max_experience_years:g} yrs")
        return job.min_experience_years, job.max_experience_years, ", ".join(parts)

    req_source = job.experience_requirement
    if req_source and req_source.strip():
        match = _EXPERIENCE_SIMPLE_RE.search(req_source)
        if match:
            min_y = float(match.group(1))
            max_y = float(match.group(2)) if match.group(2) else None
            return min_y, max_y, req_source.strip()
        lower = req_source.lower()
        entry_markers = ("intern", "fresher", "new grad", "entry", "0 year", "no experience")
        if any(k in lower for k in entry_markers):
            return 0.0, None, req_source.strip()
        return None, None, req_source.strip()

    match = _EXPERIENCE_YEARS_RE.search(combined_text)
    if match:
        min_y = float(match.group(1))
        max_y = float(match.group(2)) if match.group(2) else None
        return min_y, max_y, match.group(0).strip()

    title_lower = (job.title or "").lower()
    emp_lower = (job.employment_type or "").lower()
    if "intern" in title_lower or "intern" in emp_lower or "new grad" in title_lower:
        return 0.0, None, "Internship / New Grad"

    return None, None, None


def _check_experience_years(
    profile: ProfileSnapshot,
    job: JobRequirementsSnapshot,
    combined_text: str,
) -> ConditionCheckResult:
    min_y, max_y, req_display = _parse_experience_bounds(job, combined_text)
    cand_exp_str = str(profile.experience_years) if profile.experience_years is not None else None
    if req_display is None and min_y is None and max_y is None:
        return ConditionCheckResult(
            condition="experience_years",
            status="NOT_SPECIFIED",
            candidate_value=cand_exp_str,
            reason="Job does not state an explicit years-of-experience requirement.",
        )

    if min_y is None and max_y is None:
        return ConditionCheckResult(
            condition="experience_years",
            status="UNCERTAIN",
            required_value=req_display,
            candidate_value=cand_exp_str,
            reason="Experience requirement is qualitative without clear year bounds.",
        )

    if profile.experience_years is None:
        if min_y == 0.0 and max_y is None:
            return ConditionCheckResult(
                condition="experience_years",
                status="PASS",
                required_value=req_display,
                candidate_value="0",
                reason="Role requires 0+ years / internship level.",
            )
        return ConditionCheckResult(
            condition="experience_years",
            status="UNCERTAIN",
            required_value=req_display,
            candidate_value=None,
            reason="Job specifies years of experience, but candidate experience_years is missing.",
        )

    cand_y = float(profile.experience_years)
    cand_display = f"{cand_y:g} years"
    if min_y is not None and cand_y + 1e-6 < min_y:
        return ConditionCheckResult(
            condition="experience_years",
            status="FAIL",
            required_value=req_display,
            candidate_value=cand_display,
            reason=(
                f"Candidate experience ({cand_display}) is below "
                f"required minimum ({min_y:g} years)."
            ),
        )
    if max_y is not None and cand_y - 1e-6 > max_y:
        return ConditionCheckResult(
            condition="experience_years",
            status="FAIL",
            required_value=req_display,
            candidate_value=cand_display,
            reason=f"Candidate experience ({cand_display}) exceeds maximum ({max_y:g} years).",
        )
    return ConditionCheckResult(
        condition="experience_years",
        status="PASS",
        required_value=req_display,
        candidate_value=cand_display,
        reason=f"Candidate experience ({cand_display}) meets requirement ({req_display}).",
    )


def _check_location(
    profile: ProfileSnapshot,
    job: JobRequirementsSnapshot,
) -> ConditionCheckResult:
    loc_text = " ".join(p for p in (job.location, job.country) if p).strip()
    workplace = (job.workplace_type or "").strip().upper()
    if not loc_text and not workplace:
        return ConditionCheckResult(
            condition="location",
            status="NOT_SPECIFIED",
            candidate_value=", ".join(profile.preferred_locations) or None,
            reason="Job does not state a location or workplace type.",
        )

    norm_job_loc = _normalize_loc_token(loc_text)
    is_remote = workplace == "REMOTE" or "remote" in norm_job_loc
    req_display = loc_text or workplace

    for excluded in profile.excluded_locations:
        norm_ex = _normalize_loc_token(excluded)
        if not norm_ex:
            continue
        if norm_ex == "remote" and is_remote:
            return ConditionCheckResult(
                condition="location",
                status="FAIL",
                required_value=req_display,
                candidate_value=", ".join(profile.preferred_locations) or None,
                reason="Remote work is in candidate excluded locations.",
            )
        if not is_remote and norm_ex in norm_job_loc:
            return ConditionCheckResult(
                condition="location",
                status="FAIL",
                required_value=req_display,
                candidate_value=", ".join(profile.preferred_locations) or None,
                reason=f"Job location {req_display!r} matches excluded location {excluded!r}.",
            )

    if is_remote:
        return ConditionCheckResult(
            condition="location",
            status="PASS",
            required_value=req_display,
            candidate_value=", ".join(profile.preferred_locations) or "Any",
            reason="Remote role satisfies location compatibility.",
        )

    if not profile.preferred_locations:
        return ConditionCheckResult(
            condition="location",
            status="PASS",
            required_value=req_display,
            candidate_value="No restriction",
            reason="Location is not excluded and candidate has no location restriction.",
        )

    for pref in profile.preferred_locations:
        norm_pref = _normalize_loc_token(pref)
        if norm_pref and (norm_pref in norm_job_loc or norm_job_loc in norm_pref):
            return ConditionCheckResult(
                condition="location",
                status="PASS",
                required_value=req_display,
                candidate_value=", ".join(profile.preferred_locations),
                reason=f"Job location {req_display!r} matches preferred location {pref!r}.",
            )

    return ConditionCheckResult(
        condition="location",
        status="UNCERTAIN",
        required_value=req_display,
        candidate_value=", ".join(profile.preferred_locations),
        reason=f"Job location {req_display!r} is outside preferred locations.",
    )


def _check_work_authorization(
    profile: ProfileSnapshot,
    job: JobRequirementsSnapshot,
    combined_text: str,
) -> ConditionCheckResult:
    lowered = combined_text.lower()
    req_explicit = (job.work_authorization_requirement or "").strip()

    us_restricted = any(
        phrase in lowered
        for phrase in (
            "u.s. citizen",
            "us citizen",
            "united states citizen",
            "security clearance",
            "green card",
            "permanent resident",
            "without sponsorship",
            "no visa sponsorship",
            "not sponsor",
            "unable to sponsor",
            "authorized to work in the u.s",
            "authorized to work in the united states",
            "authorized to work in the us",
        )
    )
    india_auth = any(
        phrase in lowered
        for phrase in (
            "authorized to work in india",
            "work authorization in india",
            "indian citizen",
        )
    )

    if (
        not req_explicit
        and not us_restricted
        and not india_auth
        and job.sponsorship_available is None
    ):
        return ConditionCheckResult(
            condition="work_authorization",
            status="NOT_SPECIFIED",
            candidate_value=", ".join(profile.work_authorizations) or None,
            reason="Job does not state an explicit work authorization or sponsorship restriction.",
        )

    req_display = req_explicit or (
        "US authorization / no sponsorship"
        if us_restricted
        else (
            "India authorization"
            if india_auth
            else f"sponsorship_available={job.sponsorship_available}"
        )
    )
    cand_auths = {a.strip().lower() for a in profile.work_authorizations if a.strip()}
    cand_display = ", ".join(profile.work_authorizations) or None

    if job.sponsorship_available is False and profile.requires_sponsorship is True:
        return ConditionCheckResult(
            condition="work_authorization",
            status="FAIL",
            required_value=req_display,
            candidate_value=cand_display,
            reason="Job does not offer visa sponsorship and candidate requires sponsorship.",
        )

    if us_restricted:
        if any(a in cand_auths for a in ("us", "usa", "united states", "us citizen", "green card")):
            return ConditionCheckResult(
                condition="work_authorization",
                status="PASS",
                required_value=req_display,
                candidate_value=cand_display,
                reason="Candidate holds required US work authorization.",
            )
        if cand_auths or profile.requires_sponsorship is True:
            return ConditionCheckResult(
                condition="work_authorization",
                status="FAIL",
                required_value=req_display,
                candidate_value=cand_display,
                reason="Job restricts to US work authorization/citizenship without sponsorship.",
            )
        return ConditionCheckResult(
            condition="work_authorization",
            status="UNCERTAIN",
            required_value=req_display,
            candidate_value=None,
            reason=(
                "Job requires US work authorization, "
                "but candidate authorization status is unknown."
            ),
        )

    if india_auth:
        if "india" in cand_auths:
            return ConditionCheckResult(
                condition="work_authorization",
                status="PASS",
                required_value=req_display,
                candidate_value=cand_display,
                reason="Candidate holds work authorization in India.",
            )
        return ConditionCheckResult(
            condition="work_authorization",
            status="UNCERTAIN",
            required_value=req_display,
            candidate_value=cand_display,
            reason="Job mentions India work authorization; verify candidate status.",
        )

    if job.sponsorship_available is True:
        return ConditionCheckResult(
            condition="work_authorization",
            status="PASS",
            required_value=req_display,
            candidate_value=cand_display,
            reason="Job states visa sponsorship is available.",
        )

    return ConditionCheckResult(
        condition="work_authorization",
        status="UNCERTAIN",
        required_value=req_display,
        candidate_value=cand_display,
        reason="Work authorization requirement should be verified manually.",
    )


def evaluate_eligibility(
    profile: ProfileSnapshot,
    job: JobRequirementsSnapshot,
) -> EligibilityResult:
    """Evaluate mandatory conditions first; missing requirements never produce false certainty."""
    combined_text = _combined_job_text(job)
    checks = [
        _check_graduation_year(profile, job, combined_text),
        _check_degree_branch(profile, job, combined_text),
        _check_min_cgpa(profile, job, combined_text),
        _check_experience_years(profile, job, combined_text),
        _check_location(profile, job),
        _check_work_authorization(profile, job, combined_text),
    ]

    passed = [c.condition for c in checks if c.status == "PASS"]
    failed = [c.condition for c in checks if c.status == "FAIL"]
    uncertain = [c.condition for c in checks if c.status == "UNCERTAIN"]
    missing = [c.condition for c in checks if c.status == "NOT_SPECIFIED"]

    core_qualification_conditions = {
        "graduation_year",
        "degree_branch",
        "experience_years",
        "min_cgpa",
    }
    passed_core = [c for c in passed if c in core_qualification_conditions]

    if failed:
        status: EligibilityStatus = "INELIGIBLE"
        summary = f"Ineligible due to failed mandatory condition(s): {', '.join(failed)}."
    elif len(missing) == len(checks):
        status = "NOT_EVALUATED"
        summary = "No mandatory eligibility requirements were stated in the job posting."
    elif uncertain:
        status = "UNCERTAIN"
        summary = (
            "Eligibility is uncertain for: "
            f"{', '.join(uncertain)} (missing or unconfirmed criteria)."
        )
    elif not passed_core:
        status = "UNCERTAIN"
        summary = (
            "Core academic and experience eligibility requirements are missing from the posting; "
            "cannot confirm eligibility with certainty."
        )
    else:
        status = "ELIGIBLE"
        summary = f"Meets all stated mandatory eligibility conditions ({', '.join(passed)})."

    return EligibilityResult(
        status=status,
        checks=checks,
        passed_conditions=passed,
        failed_conditions=failed,
        uncertain_conditions=uncertain,
        missing_requirements=missing,
        summary=summary,
    )
