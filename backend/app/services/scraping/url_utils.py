"""URL canonicalization and domain extraction utilities."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_QUERY_PARAMS = frozenset(
    {
        "gh_src",
        "gh_jid",
        "ashby_jid",
        "ref",
        "source",
        "fbclid",
        "gclid",
    }
)
TRACKING_QUERY_PREFIXES = ("utm_",)


def is_tracking_query_param(name: str) -> bool:
    """Return True if a query parameter name is a known tracking parameter."""
    lowered = name.strip().lower()
    if lowered in TRACKING_QUERY_PARAMS:
        return True
    return any(lowered.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES)


def _format_netloc(hostname: str, port: int | None, scheme: str) -> str:
    host = hostname.lower().rstrip(".")
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if port is None:
        return host
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        return host
    return f"{host}:{port}"


def canonicalize_job_url(url: str) -> str:
    """Normalize a job URL by lowercasing scheme/host and stripping fragments & tracking params."""
    raw = url.strip()
    if not raw:
        raise ValueError("URL cannot be empty.")

    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if not scheme or not parts.hostname:
        raise ValueError(f"Invalid URL without scheme or hostname: {url!r}")

    port = parts.port
    netloc = _format_netloc(parts.hostname, port, scheme)
    path = parts.path.rstrip("/")

    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
    filtered_pairs = [(k, v) for k, v in query_pairs if not is_tracking_query_param(k)]
    filtered_pairs.sort(key=lambda item: (item[0], item[1]))
    query = urlencode(filtered_pairs, doseq=True)

    return urlunsplit((scheme, netloc, path, query, ""))


def extract_domain(url: str) -> str:
    """Extract normalized lowercase hostname from a URL or bare host string."""
    raw = url.strip()
    if not raw:
        return ""
    candidate = raw if "://" in raw else f"https://{raw}"
    parts = urlsplit(candidate)
    return (parts.hostname or "").lower().rstrip(".")
