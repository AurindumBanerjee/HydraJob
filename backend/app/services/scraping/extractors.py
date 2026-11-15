"""Multi-layer job extraction: JSON-LD, OpenGraph, generic HTML, lazy Playwright, and Ollama."""

import html
import importlib
import json
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

from pydantic import BaseModel, Field, field_validator

from app.services.llm.ollama_client import OllamaClient, OllamaStructuredResponse
from app.services.llm.prompts import PROMPT_VERSION, build_job_extraction_prompt
from app.services.scraping.ssrf import validate_safe_url

_PLACEHOLDER_VALUES = frozenset(
    {
        "",
        "n/a",
        "na",
        "none",
        "null",
        "unknown",
        "not specified",
        "not disclosed",
        "not mentioned",
        "tbd",
        "unspecified",
    }
)

_KNOWN_SKILLS: tuple[tuple[str, str], ...] = (
    ("python", "Python"),
    ("c++", "C++"),
    ("c#", "C#"),
    ("sql", "SQL"),
    ("pytorch", "PyTorch"),
    ("tensorflow", "TensorFlow"),
    ("scikit-learn", "scikit-learn"),
    ("machine learning", "Machine Learning"),
    ("deep learning", "Deep Learning"),
    ("nlp", "NLP"),
    ("natural language processing", "NLP"),
    ("llms", "LLMs"),
    ("llm", "LLMs"),
    ("large language models", "LLMs"),
    ("rag", "RAG"),
    ("retrieval-augmented generation", "RAG"),
    ("computer vision", "Computer Vision"),
    ("fine-tuning", "Model Fine-Tuning"),
    ("fine tuning", "Model Fine-Tuning"),
    ("transformers", "Transformers"),
    ("huggingface", "Hugging Face"),
    ("hugging face", "Hugging Face"),
    ("fastapi", "FastAPI"),
    ("docker", "Docker"),
    ("kubernetes", "Kubernetes"),
    ("aws", "AWS"),
    ("postgresql", "PostgreSQL"),
    ("postgres", "PostgreSQL"),
    ("git", "Git"),
    ("spark", "Apache Spark"),
    ("numpy", "NumPy"),
    ("pandas", "Pandas"),
    ("tinyml", "TinyML"),
    ("onnx", "ONNX"),
    ("cuda", "CUDA"),
    ("java", "Java"),
    ("go", "Go"),
    ("rust", "Rust"),
    ("typescript", "TypeScript"),
    ("javascript", "JavaScript"),
    ("react", "React"),
)

_WHITESPACE_RE = re.compile(r"\s+")
_DEADLINE_RE = re.compile(
    r"(?:application\s+deadline|apply\s+by|closing\s+date|deadline)\s*[:\-]\s*([^\n.;]{3,60})",
    re.IGNORECASE,
)
_LOCATION_LINE_RE = re.compile(
    r"(?:^|\n)\s*(?:location|office|work\s+location)\s*[:\-]\s*([^\n]{2,100})",
    re.IGNORECASE,
)
_EXPERIENCE_LINE_RE = re.compile(
    r"(\d+\s*(?:\+|-\s*\d+)?\s*(?:years?|yrs?)(?:\s+of)?(?:\s+experience)?)",
    re.IGNORECASE,
)
_GRAD_YEAR_RE = re.compile(
    r"(?:class\s+of|batch(?:\s+of)?|graduating(?:\s+in)?|graduation\s+year)\s*[:\-]?\s*"
    r"(202[4-9]|203[0-5])",
    re.IGNORECASE,
)


def _clean_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = _WHITESPACE_RE.sub(" ", str(value)).strip()
    if text.lower() in _PLACEHOLDER_VALUES:
        return None
    return text


def _clean_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [part.strip() for part in re.split(r"[,;\n•|]+", value)]
    elif isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value]
    else:
        return []

    seen: set[str] = set()
    cleaned: list[str] = []
    for item in items:
        normalized = _WHITESPACE_RE.sub(" ", item).strip(" -*\t\r\n")
        if not normalized or normalized.lower() in _PLACEHOLDER_VALUES:
            continue
        key = normalized.lower()
        if key not in seen:
            seen.add(key)
            cleaned.append(normalized)
    return cleaned


class ExtractedJobData(BaseModel):
    """Structured job fields extracted from an HTML page, JSON feed, or LLM fallback."""

    company: str | None = None
    title: str | None = None
    location: str | None = None
    country: str | None = None
    employment_type: str | None = None
    workplace_type: str | None = None
    experience_requirement: str | None = None
    graduation_year_requirement: str | None = None
    degree_requirement: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    qualifications: list[str] = Field(default_factory=list)
    salary: str | None = None
    currency: str | None = None
    application_deadline: str | None = None
    application_url: str | None = None
    description: str | None = None
    external_job_id: str | None = None
    extraction_method: str | None = None
    extraction_methods_used: list[str] = Field(default_factory=list)
    raw_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "company",
        "title",
        "location",
        "country",
        "employment_type",
        "workplace_type",
        "experience_requirement",
        "graduation_year_requirement",
        "degree_requirement",
        "salary",
        "currency",
        "application_deadline",
        "application_url",
        "description",
        "external_job_id",
        "extraction_method",
        mode="before",
    )
    @classmethod
    def _normalize_scalar(cls, value: object) -> str | None:
        return _clean_optional_str(value)

    @field_validator(
        "required_skills",
        "preferred_skills",
        "responsibilities",
        "qualifications",
        "extraction_methods_used",
        mode="before",
    )
    @classmethod
    def _normalize_list(cls, value: object) -> list[str]:
        return _clean_str_list(value)


class OllamaJobExtractionSchema(BaseModel):
    """Strict Pydantic schema for Ollama structured job extraction."""

    company: str | None = None
    title: str | None = None
    location: str | None = None
    country: str | None = None
    employment_type: str | None = None
    workplace_type: str | None = None
    experience_requirement: str | None = None
    graduation_year_requirement: str | None = None
    degree_requirement: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    qualifications: list[str] = Field(default_factory=list)
    salary: str | None = None
    currency: str | None = None
    application_deadline: str | None = None
    application_url: str | None = None
    description: str | None = None

    @field_validator(
        "company",
        "title",
        "location",
        "country",
        "employment_type",
        "workplace_type",
        "experience_requirement",
        "graduation_year_requirement",
        "degree_requirement",
        "salary",
        "currency",
        "application_deadline",
        "application_url",
        "description",
        mode="before",
    )
    @classmethod
    def _normalize_scalar(cls, value: object) -> str | None:
        return _clean_optional_str(value)

    @field_validator(
        "required_skills",
        "preferred_skills",
        "responsibilities",
        "qualifications",
        mode="before",
    )
    @classmethod
    def _normalize_list(cls, value: object) -> list[str]:
        return _clean_str_list(value)


class PlaywrightFetchResult(BaseModel):
    """Outcome of an optional Playwright rendered-page fetch."""

    available: bool
    html: str | None = None
    final_url: str | None = None
    error: str | None = None


class _TextFragmentParser(HTMLParser):
    """Strip HTML tags cleanly into readable plain text."""

    _BLOCK_TAGS = frozenset({"p", "div", "li", "br", "h1", "h2", "h3", "h4", "tr", "section"})
    _SKIP_TAGS = frozenset({"script", "style", "noscript", "svg", "template"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        if lower in self._SKIP_TAGS:
            self._skip_depth += 1
        elif self._skip_depth == 0 and lower in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif self._skip_depth == 0 and lower in self._BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data:
            self._chunks.append(data)

    def get_text(self) -> str:
        raw = "".join(self._chunks)
        lines = [_WHITESPACE_RE.sub(" ", line).strip() for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)


def html_to_plain_text(html_fragment: str) -> str:
    """Convert an HTML fragment (or entity-escaped HTML) to clean plain text."""
    if not html_fragment:
        return ""
    unescaped = html.unescape(html_fragment)
    parser = _TextFragmentParser()
    parser.feed(unescaped)
    parser.close()
    return parser.get_text()


class _StructuredHTMLParser(HTMLParser):
    """Single-pass stdlib HTML parser capturing JSON-LD, meta tags, headings, lists, and text."""

    _SKIP_VISIBLE_TAGS = frozenset({"script", "style", "noscript", "svg", "template"})
    _HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4"})
    _BLOCK_BREAK_TAGS = frozenset({"p", "div", "section", "article", "br", "tr"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.json_ld_blocks: list[str] = []
        self.meta_tags: dict[str, str] = {}
        self.canonical_url: str | None = None
        self.page_title: str | None = None
        self.h1_texts: list[str] = []
        self.sections: list[tuple[str, list[str]]] = []
        self.links: list[tuple[str, str]] = []

        self._in_json_ld = False
        self._json_ld_buf: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._title_buf: list[str] = []
        self._current_heading_tag: str | None = None
        self._heading_buf: list[str] = []
        self._in_li = False
        self._li_buf: list[str] = []
        self._in_p = False
        self._p_buf: list[str] = []
        self._in_a_href: str | None = None
        self._a_buf: list[str] = []

        self._active_section: str = "_intro"
        self._section_items: dict[str, list[str]] = {"_intro": []}
        self._section_order: list[str] = ["_intro"]
        self._visible_chunks: list[str] = []

    def _ensure_section(self, name: str) -> None:
        if name not in self._section_items:
            self._section_items[name] = []
            self._section_order.append(name)
        self._active_section = name

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        attr_map = {k.lower(): (v or "") for k, v in attrs}

        if lower == "script":
            script_type = attr_map.get("type", "").lower()
            if "ld+json" in script_type:
                self._in_json_ld = True
                self._json_ld_buf = []
            self._skip_depth += 1
            return

        if lower in self._SKIP_VISIBLE_TAGS:
            self._skip_depth += 1
            return

        if lower == "meta":
            key = (attr_map.get("property") or attr_map.get("name") or "").strip().lower()
            content = attr_map.get("content", "").strip()
            if key and content and key not in self.meta_tags:
                self.meta_tags[key] = content
            return

        if lower == "link":
            rel = attr_map.get("rel", "").lower()
            href = attr_map.get("href", "").strip()
            if "canonical" in rel and href and not self.canonical_url:
                self.canonical_url = href
            return

        if lower == "title":
            self._in_title = True
            self._title_buf = []
            return

        if self._skip_depth > 0:
            return

        if lower in self._HEADING_TAGS:
            self._current_heading_tag = lower
            self._heading_buf = []
            self._visible_chunks.append("\n")
        elif lower == "li":
            self._in_li = True
            self._li_buf = []
            self._visible_chunks.append("\n- ")
        elif lower == "p":
            self._in_p = True
            self._p_buf = []
            self._visible_chunks.append("\n")
        elif lower == "a":
            href = attr_map.get("href", "").strip()
            if href:
                self._in_a_href = href
                self._a_buf = []
        elif lower in self._BLOCK_BREAK_TAGS:
            self._visible_chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower == "script":
            if self._in_json_ld:
                block = "".join(self._json_ld_buf).strip()
                if block:
                    self.json_ld_blocks.append(block)
                self._in_json_ld = False
                self._json_ld_buf = []
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return

        if lower in self._SKIP_VISIBLE_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return

        if lower == "title" and self._in_title:
            title_text = _WHITESPACE_RE.sub(" ", "".join(self._title_buf)).strip()
            if title_text and not self.page_title:
                self.page_title = title_text
            self._in_title = False
            self._title_buf = []
            return

        if self._skip_depth > 0:
            return

        if lower == self._current_heading_tag:
            heading_text = _WHITESPACE_RE.sub(" ", "".join(self._heading_buf)).strip()
            if heading_text:
                if lower == "h1":
                    self.h1_texts.append(heading_text)
                self._ensure_section(heading_text)
            self._current_heading_tag = None
            self._heading_buf = []
            self._visible_chunks.append("\n")
        elif lower == "li" and self._in_li:
            li_text = _WHITESPACE_RE.sub(" ", "".join(self._li_buf)).strip()
            if li_text:
                self._section_items[self._active_section].append(li_text)
            self._in_li = False
            self._li_buf = []
            self._visible_chunks.append("\n")
        elif lower == "p" and self._in_p:
            p_text = _WHITESPACE_RE.sub(" ", "".join(self._p_buf)).strip()
            if p_text:
                self._section_items[self._active_section].append(p_text)
            self._in_p = False
            self._p_buf = []
            self._visible_chunks.append("\n")
        elif lower == "a" and self._in_a_href is not None:
            link_text = _WHITESPACE_RE.sub(" ", "".join(self._a_buf)).strip()
            self.links.append((self._in_a_href, link_text))
            self._in_a_href = None
            self._a_buf = []
        elif lower in self._BLOCK_BREAK_TAGS:
            self._visible_chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._json_ld_buf.append(data)
            return
        if self._in_title:
            self._title_buf.append(data)
            return
        if self._skip_depth > 0:
            return
        self._visible_chunks.append(data)
        if self._current_heading_tag:
            self._heading_buf.append(data)
        if self._in_li:
            self._li_buf.append(data)
        if self._in_p:
            self._p_buf.append(data)
        if self._in_a_href is not None:
            self._a_buf.append(data)

    def finalize(self) -> None:
        self.sections = [
            (heading, self._section_items[heading])
            for heading in self._section_order
            if self._section_items[heading]
        ]

    def visible_text(self) -> str:
        raw = "".join(self._visible_chunks)
        lines = [_WHITESPACE_RE.sub(" ", line).strip() for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)


def _parse_html(html_content: str) -> _StructuredHTMLParser:
    parser = _StructuredHTMLParser()
    parser.feed(html_content)
    parser.close()
    parser.finalize()
    return parser


def _find_job_postings(obj: Any) -> list[dict[str, Any]]:
    """Recursively find schema.org JobPosting objects in parsed JSON-LD."""
    found: list[dict[str, Any]] = []
    if isinstance(obj, list):
        for item in obj:
            found.extend(_find_job_postings(item))
    elif isinstance(obj, dict):
        raw_type = obj.get("@type")
        types = raw_type if isinstance(raw_type, list) else [raw_type]
        if any(isinstance(t, str) and t.lower().endswith("jobposting") for t in types):
            found.append(obj)
        if "@graph" in obj:
            found.extend(_find_job_postings(obj["@graph"]))
    return found


def _parse_json_ld_location(
    job_location: Any,
    applicant_reqs: Any = None,
) -> tuple[str | None, str | None]:
    locations: list[str] = []
    country: str | None = None

    items = (
        job_location
        if isinstance(job_location, list)
        else ([job_location] if job_location else [])
    )
    for item in items:
        if isinstance(item, str):
            locations.append(item.strip())
            continue
        if not isinstance(item, dict):
            continue
        addr = item.get("address")
        if isinstance(addr, str):
            locations.append(addr.strip())
        elif isinstance(addr, dict):
            locality = _clean_optional_str(addr.get("addressLocality"))
            region = _clean_optional_str(addr.get("addressRegion"))
            raw_country = addr.get("addressCountry")
            if isinstance(raw_country, dict):
                raw_country = raw_country.get("name")
            country_str = _clean_optional_str(raw_country)
            if country_str and not country:
                country = country_str
            parts = [p for p in (locality, region, country_str) if p]
            if parts:
                locations.append(", ".join(parts))
        elif item.get("name"):
            locations.append(str(item["name"]).strip())

    if not locations and isinstance(applicant_reqs, dict) and applicant_reqs.get("name"):
        locations.append(str(applicant_reqs["name"]).strip())

    return (", ".join(dict.fromkeys(locations)) if locations else None), country


def _parse_json_ld_salary(base_salary: Any) -> tuple[str | None, str | None]:
    if not isinstance(base_salary, dict):
        return _clean_optional_str(base_salary), None
    currency = _clean_optional_str(base_salary.get("currency"))
    value_obj = base_salary.get("value")
    if isinstance(value_obj, dict):
        min_v = value_obj.get("minValue")
        max_v = value_obj.get("maxValue")
        exact_v = value_obj.get("value")
        unit = _clean_optional_str(value_obj.get("unitText"))
        if min_v is not None and max_v is not None:
            text = f"{min_v}-{max_v}"
        elif exact_v is not None:
            text = str(exact_v)
        else:
            text = None
        if text and unit:
            text = f"{text} / {unit}"
        return _clean_optional_str(text), currency
    if value_obj is not None:
        return _clean_optional_str(value_obj), currency
    return None, currency


def extract_skills_from_text(text: str) -> list[str]:
    """Identify explicit canonical technical skills present in job text."""
    if not text:
        return []
    lowered = text.lower()
    found: list[str] = []
    seen: set[str] = set()
    for needle, label in _KNOWN_SKILLS:
        if needle in ("c++", "c#"):
            escaped = re.escape(needle)
            matched = bool(re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", lowered))
        else:
            matched = bool(re.search(rf"\b{re.escape(needle)}\b", lowered))
        if matched and label.lower() not in seen:
            seen.add(label.lower())
            found.append(label)
    return found


def _json_ld_dict_to_job(posting: dict[str, Any], base_url: str | None = None) -> ExtractedJobData:
    title = _clean_optional_str(posting.get("title") or posting.get("name"))
    org = posting.get("hiringOrganization")
    if isinstance(org, dict):
        company = _clean_optional_str(org.get("name"))
    else:
        company = _clean_optional_str(org)

    raw_desc = posting.get("description")
    description = html_to_plain_text(str(raw_desc)) if raw_desc else None

    location, country = _parse_json_ld_location(
        posting.get("jobLocation"),
        posting.get("applicantLocationRequirements"),
    )

    job_loc_type = str(posting.get("jobLocationType") or "").upper()
    workplace_type = "REMOTE" if "TELECOMMUTE" in job_loc_type else None
    if workplace_type == "REMOTE" and not location:
        location = "Remote"

    emp_raw = posting.get("employmentType")
    if isinstance(emp_raw, list):
        employment_type = ", ".join(str(x).strip() for x in emp_raw if str(x).strip()) or None
    else:
        employment_type = _clean_optional_str(emp_raw)

    exp_raw = posting.get("experienceRequirements")
    if isinstance(exp_raw, dict):
        months = exp_raw.get("monthsOfExperience")
        experience_requirement = (
            f"{round(float(months) / 12, 1):g} years" if months is not None else None
        )
    else:
        experience_requirement = _clean_optional_str(exp_raw)

    edu_raw = posting.get("educationRequirements")
    if isinstance(edu_raw, dict):
        degree_requirement = _clean_optional_str(edu_raw.get("credentialCategory"))
    else:
        degree_requirement = _clean_optional_str(edu_raw)

    salary, currency = _parse_json_ld_salary(posting.get("baseSalary"))
    deadline = _clean_optional_str(posting.get("validThrough"))

    raw_url = _clean_optional_str(posting.get("url"))
    application_url = urljoin(base_url, raw_url) if (raw_url and base_url) else raw_url

    ident = posting.get("identifier")
    if isinstance(ident, dict):
        external_id = _clean_optional_str(ident.get("value"))
    else:
        external_id = _clean_optional_str(ident)

    skills = _clean_str_list(posting.get("skills"))
    if not skills and description:
        skills = extract_skills_from_text(description)

    responsibilities = _clean_str_list(posting.get("responsibilities"))
    qualifications = _clean_str_list(posting.get("qualifications"))

    return ExtractedJobData(
        company=company,
        title=title,
        location=location,
        country=country,
        employment_type=employment_type,
        workplace_type=workplace_type,
        experience_requirement=experience_requirement,
        degree_requirement=degree_requirement,
        required_skills=skills,
        responsibilities=responsibilities,
        qualifications=qualifications,
        salary=salary,
        currency=currency,
        application_deadline=deadline,
        application_url=application_url,
        description=description,
        external_job_id=external_id,
        extraction_method="json_ld",
        extraction_methods_used=["json_ld"],
        raw_metadata={"json_ld": posting},
    )


def extract_json_ld_jobs(html_content: str, base_url: str | None = None) -> list[ExtractedJobData]:
    """Extract all schema.org JobPosting objects embedded as JSON-LD in HTML."""
    parsed = _parse_html(html_content)
    results: list[ExtractedJobData] = []
    for block in parsed.json_ld_blocks:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        for posting in _find_job_postings(data):
            results.append(_json_ld_dict_to_job(posting, base_url=base_url))
    return results


def extract_json_ld_job(html_content: str, base_url: str | None = None) -> ExtractedJobData | None:
    """Layer 1: Extract the first schema.org JobPosting from JSON-LD if present."""
    postings = extract_json_ld_jobs(html_content, base_url=base_url)
    return postings[0] if postings else None


def extract_opengraph_metadata(
    html_content: str,
    base_url: str | None = None,
) -> ExtractedJobData:
    """Layer 2: Extract OpenGraph and standard meta tags from HTML."""
    parsed = _parse_html(html_content)
    meta = parsed.meta_tags

    company = _clean_optional_str(
        meta.get("og:site_name") or meta.get("application-name") or meta.get("author")
    )
    raw_title = _clean_optional_str(meta.get("og:title") or meta.get("twitter:title"))
    if raw_title and company and raw_title.lower().endswith(f"| {company.lower()}"):
        raw_title = raw_title[: -(len(company) + 2)].strip()

    description = _clean_optional_str(
        meta.get("og:description") or meta.get("twitter:description") or meta.get("description")
    )
    raw_url = _clean_optional_str(meta.get("og:url") or parsed.canonical_url)
    application_url = urljoin(base_url, raw_url) if (raw_url and base_url) else raw_url

    skills = extract_skills_from_text(description or "")
    methods = ["opengraph"] if any((company, raw_title, description, application_url)) else []

    return ExtractedJobData(
        company=company,
        title=raw_title,
        description=description,
        application_url=application_url,
        required_skills=skills,
        extraction_method="opengraph" if methods else None,
        extraction_methods_used=methods,
        raw_metadata={"meta_tags": meta},
    )


def _split_title_and_company(page_title: str | None) -> tuple[str | None, str | None]:
    if not page_title:
        return None, None
    for sep in (" at ", " @ ", " | ", " - ", " — "):
        if sep in page_title:
            left, right = page_title.split(sep, 1)
            left_c = _clean_optional_str(left)
            right_c = _clean_optional_str(right)
            if left_c and right_c:
                if sep in (" at ", " @ "):
                    return left_c, right_c
                if "careers" in right_c.lower() or "jobs" in right_c.lower():
                    company_part = re.sub(
                        r"\b(?:careers|jobs)\b", "", right_c, flags=re.IGNORECASE
                    ).strip(" -|")
                    return left_c, _clean_optional_str(company_part)
                return left_c, right_c
    return page_title, None


def extract_generic_html(
    html_content: str,
    base_url: str | None = None,
) -> ExtractedJobData:
    """Layer 3: Extract structured details from visible HTML headings, lists, and text."""
    parsed = _parse_html(html_content)
    visible = parsed.visible_text()

    title_from_page, company_from_title = _split_title_and_company(parsed.page_title)
    title = _clean_optional_str(parsed.h1_texts[0]) if parsed.h1_texts else title_from_page

    responsibilities: list[str] = []
    qualifications: list[str] = []
    preferred_skills: list[str] = []
    required_skills: list[str] = []

    for heading, items in parsed.sections:
        lowered = heading.lower()
        if any(k in lowered for k in ("responsibilit", "what you", "duties", "your role")):
            responsibilities.extend(items)
        elif any(k in lowered for k in ("preferred", "nice to have", "bonus")):
            for item in items:
                preferred_skills.extend(extract_skills_from_text(item))
        elif any(k in lowered for k in ("skill", "tech stack", "technologies", "requirements")):
            if "qualif" in lowered or "require" in lowered:
                qualifications.extend(items)
            for item in items:
                extracted = extract_skills_from_text(item)
                if extracted:
                    required_skills.extend(extracted)
                elif "skill" in lowered and len(item) <= 40:
                    required_skills.append(item)
        elif "qualif" in lowered or "looking for" in lowered or "eligibility" in lowered:
            qualifications.extend(items)

    if not required_skills and visible:
        required_skills = extract_skills_from_text(visible)

    loc_match = _LOCATION_LINE_RE.search(visible)
    location = _clean_optional_str(loc_match.group(1)) if loc_match else None

    workplace_type: str | None = None
    lower_visible = visible.lower()
    if "remote" in (location or "").lower() or "fully remote" in lower_visible:
        workplace_type = "REMOTE"
    elif "hybrid" in lower_visible:
        workplace_type = "HYBRID"
    elif "on-site" in lower_visible or "onsite" in lower_visible:
        workplace_type = "ONSITE"

    deadline_match = _DEADLINE_RE.search(visible)
    application_deadline = _clean_optional_str(deadline_match.group(1)) if deadline_match else None

    exp_match = _EXPERIENCE_LINE_RE.search(visible)
    experience_requirement = _clean_optional_str(exp_match.group(1)) if exp_match else None

    grad_match = _GRAD_YEAR_RE.search(visible)
    graduation_year_requirement = grad_match.group(1) if grad_match else None

    application_url = urljoin(base_url, parsed.canonical_url) if (
        parsed.canonical_url and base_url
    ) else parsed.canonical_url

    return ExtractedJobData(
        company=company_from_title,
        title=title,
        location=location,
        workplace_type=workplace_type,
        experience_requirement=experience_requirement,
        graduation_year_requirement=graduation_year_requirement,
        required_skills=required_skills,
        preferred_skills=preferred_skills,
        responsibilities=responsibilities,
        qualifications=qualifications,
        application_deadline=application_deadline,
        application_url=application_url,
        description=visible or None,
        extraction_method="generic_html" if (title or visible) else None,
        extraction_methods_used=["generic_html"] if (title or visible) else [],
        raw_metadata={"sections": [h for h, _ in parsed.sections]},
    )


async def fetch_with_playwright(
    url: str,
    *,
    timeout_ms: int = 15000,
    resolve_dns: bool = True,
) -> PlaywrightFetchResult:
    """Layer 4: Lazily import Playwright to render JS pages without requiring it at install."""
    safe_url = validate_safe_url(url, resolve_dns=resolve_dns)
    try:
        pw_module = importlib.import_module("playwright.async_api")
        async_playwright = pw_module.async_playwright
    except ImportError:
        return PlaywrightFetchResult(
            available=False,
            error="Playwright is not installed in this environment.",
        )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()

            async def _ssrf_route_handler(route: Any) -> None:
                try:
                    validate_safe_url(route.request.url, resolve_dns=resolve_dns)
                except Exception:
                    await route.abort()
                    return
                await route.continue_()

            await page.route("**/*", _ssrf_route_handler)
            await page.goto(safe_url, wait_until="networkidle", timeout=timeout_ms)
            final_url = validate_safe_url(page.url, resolve_dns=resolve_dns)
            content = await page.content()
            return PlaywrightFetchResult(available=True, html=content, final_url=final_url)
        finally:
            await browser.close()


def _merge_extracted_layers(*layers: ExtractedJobData) -> ExtractedJobData:
    """Merge layers in priority order: earlier layers take precedence for non-empty fields."""
    merged: dict[str, Any] = {}
    methods_used: list[str] = []
    scalar_fields = (
        "company",
        "title",
        "location",
        "country",
        "employment_type",
        "workplace_type",
        "experience_requirement",
        "graduation_year_requirement",
        "degree_requirement",
        "salary",
        "currency",
        "application_deadline",
        "application_url",
        "description",
        "external_job_id",
    )
    list_fields = (
        "required_skills",
        "preferred_skills",
        "responsibilities",
        "qualifications",
    )

    for layer in layers:
        for method in layer.extraction_methods_used:
            if method not in methods_used:
                methods_used.append(method)
        for field in scalar_fields:
            if not merged.get(field):
                val = getattr(layer, field)
                if val:
                    merged[field] = val
        for field in list_fields:
            if not merged.get(field):
                val = getattr(layer, field)
                if val:
                    merged[field] = list(val)

    merged["extraction_methods_used"] = methods_used
    merged["extraction_method"] = methods_used[0] if methods_used else None
    return ExtractedJobData(**merged)


def extract_job_from_html(
    html_content: str,
    *,
    url: str | None = None,
) -> ExtractedJobData:
    """Run deterministic extraction layers 1 (JSON-LD) -> 2 (OpenGraph) -> 3 (Generic HTML)."""
    json_ld = extract_json_ld_job(html_content, base_url=url)
    og = extract_opengraph_metadata(html_content, base_url=url)
    generic = extract_generic_html(html_content, base_url=url)
    layers = [layer for layer in (json_ld, og, generic) if layer is not None]
    return _merge_extracted_layers(*layers)


def _schema_to_extracted(
    schema: OllamaJobExtractionSchema,
    *,
    method: str = "ollama",
) -> ExtractedJobData:
    return ExtractedJobData(
        company=schema.company,
        title=schema.title,
        location=schema.location,
        country=schema.country,
        employment_type=schema.employment_type,
        workplace_type=schema.workplace_type,
        experience_requirement=schema.experience_requirement,
        graduation_year_requirement=schema.graduation_year_requirement,
        degree_requirement=schema.degree_requirement,
        required_skills=schema.required_skills,
        preferred_skills=schema.preferred_skills,
        responsibilities=schema.responsibilities,
        qualifications=schema.qualifications,
        salary=schema.salary,
        currency=schema.currency,
        application_deadline=schema.application_deadline,
        application_url=schema.application_url,
        description=schema.description,
        extraction_method=method,
        extraction_methods_used=[method],
    )


def _extracted_to_schema(data: ExtractedJobData) -> OllamaJobExtractionSchema:
    return OllamaJobExtractionSchema(
        company=data.company,
        title=data.title,
        location=data.location,
        country=data.country,
        employment_type=data.employment_type,
        workplace_type=data.workplace_type,
        experience_requirement=data.experience_requirement,
        graduation_year_requirement=data.graduation_year_requirement,
        degree_requirement=data.degree_requirement,
        required_skills=data.required_skills,
        preferred_skills=data.preferred_skills,
        responsibilities=data.responsibilities,
        qualifications=data.qualifications,
        salary=data.salary,
        currency=data.currency,
        application_deadline=data.application_deadline,
        application_url=data.application_url,
        description=data.description,
    )


async def extract_job_with_ollama(
    text: str,
    *,
    url: str | None = None,
    ollama_client: OllamaClient | None = None,
    base_data: ExtractedJobData | None = None,
) -> tuple[ExtractedJobData, OllamaStructuredResponse[OllamaJobExtractionSchema]]:
    """Layer 5: Run Ollama structured extraction with deterministic fallback on errors."""
    client = ollama_client or OllamaClient()
    fallback_extracted = base_data or ExtractedJobData(description=_clean_optional_str(text))
    prompt_spec = build_job_extraction_prompt(text, url=url, version=PROMPT_VERSION)

    response = await client.agenerate_structured(
        prompt=prompt_spec.user_prompt,
        system_prompt=prompt_spec.system_prompt,
        response_model=OllamaJobExtractionSchema,
        fallback_factory=lambda: _extracted_to_schema(fallback_extracted),
        prompt_version=prompt_spec.version,
    )

    if response.used_fallback:
        return fallback_extracted, response

    llm_extracted = _schema_to_extracted(response.data, method="ollama")
    merged = _merge_extracted_layers(fallback_extracted, llm_extracted)
    return merged, response
