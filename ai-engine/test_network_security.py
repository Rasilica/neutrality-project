import socket
from types import SimpleNamespace

import pytest

from network_security import UnsafeOutboundUrl, safe_get, validate_outbound_url


def resolver_for(*addresses):
    def resolve(_host, port, type=socket.SOCK_STREAM):
        results = []
        for address in addresses:
            family = socket.AF_INET6 if ":" in address else socket.AF_INET
            sockaddr = (
                (address, port, 0, 0) if family == socket.AF_INET6 else (address, port)
            )
            results.append((family, type, socket.IPPROTO_TCP, "", sockaddr))
        return results

    return resolve


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/feed.xml",
        "https://user:password@example.com/feed.xml",
        "https:///missing-host",
        "https://example.com:not-a-port/feed.xml",
    ],
)
def test_validate_outbound_url_rejects_unsafe_url_shapes(url):
    with pytest.raises(UnsafeOutboundUrl):
        validate_outbound_url(url, resolver=resolver_for("93.184.216.34"))


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.10",
        "169.254.169.254",
        "192.168.1.20",
        "::1",
        "fc00::1",
        "::ffff:127.0.0.1",
        "::ffff:10.0.0.10",
    ],
)
def test_validate_outbound_url_rejects_non_public_dns_results(address):
    with pytest.raises(UnsafeOutboundUrl):
        validate_outbound_url(
            "https://news.example.com/feed.xml",
            resolver=resolver_for(address),
        )


def test_validate_outbound_url_rejects_mixed_public_and_private_dns_results():
    with pytest.raises(UnsafeOutboundUrl):
        validate_outbound_url(
            "https://news.example.com/feed.xml",
            resolver=resolver_for("93.184.216.34", "127.0.0.1"),
        )


def test_validate_outbound_url_accepts_public_https_url_from_allowed_host():
    validated = validate_outbound_url(
        "https://news.example.com/feed.xml?section=world",
        allowed_hosts={"news.example.com"},
        resolver=resolver_for("93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"),
    )

    assert validated == "https://news.example.com/feed.xml?section=world"


def test_validate_outbound_url_rejects_hostname_suffix_confusion():
    with pytest.raises(UnsafeOutboundUrl):
        validate_outbound_url(
            "https://news.example.com.attacker.test/feed.xml",
            allowed_hosts={"news.example.com"},
            resolver=resolver_for("93.184.216.34"),
        )


def test_validate_outbound_url_rejects_dns_resolution_failure():
    def failed_resolver(_host, _port, type=socket.SOCK_STREAM):
        raise socket.gaierror("not found")

    with pytest.raises(UnsafeOutboundUrl, match="resolved safely"):
        validate_outbound_url(
            "https://news.example.com/feed.xml", resolver=failed_resolver
        )


def test_safe_get_revalidates_redirect_targets_before_following_them():
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(
            status_code=302,
            headers={"Location": "http://127.0.0.1/admin"},
            close=lambda: None,
        )

    with pytest.raises(UnsafeOutboundUrl):
        safe_get(
            "https://news.example.com/feed.xml",
            request_get=fake_get,
            resolver=resolver_for("93.184.216.34"),
        )

    assert [url for url, _kwargs in calls] == ["https://news.example.com/feed.xml"]
    assert calls[0][1]["allow_redirects"] is False


def test_safe_get_follows_a_valid_relative_redirect():
    calls = []
    responses = [
        SimpleNamespace(
            status_code=301, headers={"Location": "/rss/latest.xml"}, close=lambda: None
        ),
        SimpleNamespace(status_code=200, headers={}, close=lambda: None),
    ]

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return responses.pop(0)

    response = safe_get(
        "https://news.example.com/feed.xml",
        request_get=fake_get,
        allowed_hosts={"news.example.com"},
        resolver=resolver_for("93.184.216.34"),
    )

    assert response.status_code == 200
    assert [url for url, _kwargs in calls] == [
        "https://news.example.com/feed.xml",
        "https://news.example.com/rss/latest.xml",
    ]


def test_safe_get_closes_response_and_rejects_excessive_redirects():
    closed = []

    def fake_get(_url, **_kwargs):
        return SimpleNamespace(
            status_code=302,
            headers={"Location": "/again"},
            close=lambda: closed.append(True),
        )

    with pytest.raises(UnsafeOutboundUrl, match="redirect limit"):
        safe_get(
            "https://news.example.com/feed.xml",
            request_get=fake_get,
            resolver=resolver_for("93.184.216.34"),
            max_redirects=1,
        )

    assert len(closed) == 2
