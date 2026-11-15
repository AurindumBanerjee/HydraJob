"""SSRF protection: strict URL validation, DNS resolution checks, and safe redirect fetching."""

import ipaddress
import re
import socket
from urllib.parse import urljoin, urlsplit

import httpx
from pydantic import BaseModel

from app.core.exceptions import HydraJobError

ALLOWED_SCHEMES = frozenset({"http", "https"})

BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata",
        "metadata.google.internal",
        "instance-data",
    }
)

BLOCKED_HOST_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".localdomain",
    ".arpa",
)

BLOCKED_IP_NETWORKS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
)

_NUMERIC_HOST_RE = re.compile(r"^(?:\d+|0x[0-9a-f]+)$", re.IGNORECASE)
_OCTAL_OR_HEX_QUAD_RE = re.compile(
    r"^(?:0[0-7]+|0x[0-9a-f]+|\d+)(?:\.(?:0[0-7]+|0x[0-9a-f]+|\d+)){1,3}$",
    re.IGNORECASE,
)


class SSRFValidationError(HydraJobError, ValueError):
    """Raised when a URL violates SSRF safety policy."""

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(
            message,
            code="ssrf_blocked",
            status_code=400,
            details=details,
        )


class SafeFetchResult(BaseModel):
    """Result of an SSRF-validated HTTP fetch."""

    url: str
    final_url: str
    status_code: int
    headers: dict[str, str]
    text: str
    redirect_chain: list[str] = []


def is_safe_ip(ip_str: str) -> bool:
    """Return True only if an IP address is public and routable (not private/reserved/local)."""
    cleaned = ip_str.split("%", 1)[0].strip()
    try:
        ip = ipaddress.ip_address(cleaned)
    except ValueError:
        return False

    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return is_safe_ip(str(ip.ipv4_mapped))

    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return False

    for network in BLOCKED_IP_NETWORKS:
        if ip in network:
            return False

    return True


def _validate_hostname_syntax(hostname: str) -> str:
    host = hostname.strip().rstrip(".").lower()
    if not host:
        raise SSRFValidationError("URL hostname cannot be empty.")

    if "%" in host:
        raise SSRFValidationError(f"Blocked hostname containing zone/percent encoding: {host}")

    if host in BLOCKED_HOSTNAMES or any(host.endswith(suffix) for suffix in BLOCKED_HOST_SUFFIXES):
        raise SSRFValidationError(f"Blocked internal or local hostname: {host}")

    return host


def _check_obfuscated_ip_literal(host: str) -> None:
    """Block decimal/hex/octal IPv4 encodings that bypass naive string checks."""
    try:
        ipaddress.ip_address(host)
        return
    except ValueError:
        pass

    if _NUMERIC_HOST_RE.match(host):
        raise SSRFValidationError(f"Blocked numeric IP literal hostname: {host}")

    if _OCTAL_OR_HEX_QUAD_RE.match(host):
        parts = host.split(".")
        if len(parts) < 4 or any(
            (len(part) > 1 and part.startswith("0")) or part.lower().startswith("0x")
            for part in parts
        ):
            raise SSRFValidationError(f"Blocked obfuscated IPv4 hostname: {host}")


def _resolve_and_check_dns(host: str, port: int) -> None:
    try:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SSRFValidationError(f"DNS resolution failed for hostname: {host}") from exc

    if not records:
        raise SSRFValidationError(f"No DNS records resolved for hostname: {host}")

    for record in records:
        sockaddr = record[4]
        if not sockaddr:
            continue
        resolved_ip = str(sockaddr[0])
        if not is_safe_ip(resolved_ip):
            raise SSRFValidationError(
                f"Hostname {host} resolved to blocked non-public IP: {resolved_ip}"
            )


def validate_safe_url(url: str, resolve_dns: bool = True) -> str:
    """Validate that a URL is safe against SSRF (HTTP/HTTPS, no credentials, public host/IP)."""
    if not isinstance(url, str):
        raise SSRFValidationError("URL must be a string.")

    cleaned = url.strip()
    if not cleaned:
        raise SSRFValidationError("URL cannot be empty.")

    if any(ch in cleaned for ch in ("\r", "\n", "\t", "\x00")):
        raise SSRFValidationError("URL contains invalid control characters.")

    try:
        parts = urlsplit(cleaned)
    except ValueError as exc:
        raise SSRFValidationError("Malformed URL.") from exc

    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise SSRFValidationError(f"Unsupported URL scheme {scheme!r}; only http/https allowed.")

    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise SSRFValidationError("URLs containing embedded credentials are not allowed.")

    if not parts.hostname:
        raise SSRFValidationError("URL must include a valid hostname.")

    try:
        port = parts.port
    except ValueError as exc:
        raise SSRFValidationError("URL contains an invalid port.") from exc

    host = _validate_hostname_syntax(parts.hostname)
    _check_obfuscated_ip_literal(host)

    try:
        ipaddress.ip_address(host)
        is_ip_literal = True
    except ValueError:
        is_ip_literal = False

    if is_ip_literal:
        if not is_safe_ip(host):
            raise SSRFValidationError(f"Blocked non-public IP address: {host}")
    elif resolve_dns:
        effective_port = port if port is not None else (443 if scheme == "https" else 80)
        _resolve_and_check_dns(host, effective_port)

    return cleaned


def validate_redirect_hop(
    current_url: str,
    location: str,
    *,
    resolve_dns: bool = True,
) -> str:
    """Resolve a redirect Location header against current_url and validate it against SSRF."""
    if not location or not location.strip():
        raise SSRFValidationError("Redirect response missing Location header.")
    target = urljoin(current_url, location.strip())
    return validate_safe_url(target, resolve_dns=resolve_dns)


async def safe_fetch_url(
    url: str,
    *,
    client: httpx.AsyncClient | None = None,
    timeout: float = 10.0,
    max_redirects: int = 5,
    max_bytes: int = 5_000_000,
    resolve_dns: bool = True,
    headers: dict[str, str] | None = None,
) -> SafeFetchResult:
    """Fetch a URL while validating initial target and every redirect hop against SSRF."""
    current_url = validate_safe_url(url, resolve_dns=resolve_dns)
    redirect_chain: list[str] = []
    visited: set[str] = set()

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)
    try:
        for _ in range(max_redirects + 1):
            if current_url in visited:
                raise SSRFValidationError("Redirect loop detected.")
            visited.add(current_url)

            response = await http_client.get(
                current_url,
                headers=headers,
                timeout=timeout,
                follow_redirects=False,
            )

            if 300 <= response.status_code < 400 and "location" in response.headers:
                next_url = validate_redirect_hop(
                    current_url,
                    response.headers["location"],
                    resolve_dns=resolve_dns,
                )
                redirect_chain.append(current_url)
                current_url = next_url
                continue

            content_length = response.headers.get("content-length")
            if content_length and content_length.isdigit() and int(content_length) > max_bytes:
                raise SSRFValidationError(
                    f"Response Content-Length {content_length} exceeds limit of {max_bytes} bytes."
                )

            raw_bytes = response.content
            if len(raw_bytes) > max_bytes:
                raise SSRFValidationError(
                    f"Response body size {len(raw_bytes)} exceeds limit of {max_bytes} bytes."
                )

            encoding = response.encoding or "utf-8"
            text = raw_bytes.decode(encoding, errors="replace")
            return SafeFetchResult(
                url=url,
                final_url=current_url,
                status_code=response.status_code,
                headers={k.lower(): v for k, v in response.headers.items()},
                text=text,
                redirect_chain=redirect_chain,
            )

        raise SSRFValidationError(f"Exceeded maximum redirect hops ({max_redirects}).")
    finally:
        if owns_client:
            await http_client.aclose()
