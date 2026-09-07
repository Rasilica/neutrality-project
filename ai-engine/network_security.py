import ipaddress
import socket
from collections.abc import Callable, Iterable
from urllib.parse import urljoin, urlsplit

import requests

REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})


class UnsafeOutboundUrl(ValueError):
    """Raised before an outbound request can target an unsafe network location."""


def _normalize_hostname(hostname: str) -> str:
    return hostname.rstrip(".").encode("idna").decode("ascii").lower()


def _is_allowed_hostname(hostname: str, allowed_hosts: Iterable[str]) -> bool:
    normalized_allowed_hosts = {
        _normalize_hostname(str(host).strip())
        for host in allowed_hosts
        if str(host).strip()
    }
    return any(
        hostname == allowed or hostname.endswith(f".{allowed}")
        for allowed in normalized_allowed_hosts
    )


def _normalize_ip_address(address: str):
    parsed_address = ipaddress.ip_address(address)
    if isinstance(parsed_address, ipaddress.IPv6Address) and parsed_address.ipv4_mapped:
        return parsed_address.ipv4_mapped
    return parsed_address


def validate_outbound_url(
    url: str,
    *,
    allowed_hosts: Iterable[str] | None = None,
    resolver: Callable | None = None,
) -> str:
    candidate = str(url or "").strip()
    try:
        parsed = urlsplit(candidate)
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise UnsafeOutboundUrl("Outbound URL is malformed.") from exc

    if parsed.scheme.lower() not in {"http", "https"}:
        raise UnsafeOutboundUrl("Outbound URL must use HTTP or HTTPS.")
    if not parsed.hostname:
        raise UnsafeOutboundUrl("Outbound URL must include a hostname.")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeOutboundUrl("Outbound URL credentials are not allowed.")

    try:
        hostname = _normalize_hostname(parsed.hostname)
    except UnicodeError as exc:
        raise UnsafeOutboundUrl("Outbound URL hostname is invalid.") from exc

    if allowed_hosts is not None and not _is_allowed_hostname(hostname, allowed_hosts):
        raise UnsafeOutboundUrl("Outbound URL hostname is not allowed.")

    try:
        literal_address = _normalize_ip_address(hostname)
        addresses = [literal_address]
    except ValueError:
        resolve = resolver or socket.getaddrinfo
        try:
            resolved = resolve(hostname, port, type=socket.SOCK_STREAM)
            addresses = [_normalize_ip_address(item[4][0]) for item in resolved]
        except (OSError, ValueError) as exc:
            raise UnsafeOutboundUrl(
                "Outbound URL hostname could not be resolved safely."
            ) from exc

    if not addresses or any(not address.is_global for address in addresses):
        raise UnsafeOutboundUrl("Outbound URL resolves to a non-public address.")

    return candidate


def safe_get(
    url: str,
    *,
    allowed_hosts: Iterable[str] | None = None,
    resolver: Callable | None = None,
    request_get: Callable | None = None,
    max_redirects: int = 5,
    **request_kwargs,
):
    get = request_get or requests.get
    current_url = validate_outbound_url(
        url,
        allowed_hosts=allowed_hosts,
        resolver=resolver,
    )
    request_kwargs.pop("allow_redirects", None)

    for redirect_count in range(max_redirects + 1):
        response = get(current_url, allow_redirects=False, **request_kwargs)
        location = response.headers.get("Location")
        if response.status_code not in REDIRECT_STATUS_CODES or not location:
            return response
        if redirect_count == max_redirects:
            response.close()
            raise UnsafeOutboundUrl("Outbound URL exceeded the redirect limit.")

        redirected_url = urljoin(current_url, location)
        response.close()
        current_url = validate_outbound_url(
            redirected_url,
            allowed_hosts=allowed_hosts,
            resolver=resolver,
        )

    raise AssertionError("unreachable")
