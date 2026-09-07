import os
from urllib.parse import urlsplit

from sqlalchemy import or_

DEFAULT_SOURCE_HOSTS = ("news.sbs.co.kr",)


def configured_source_hosts() -> tuple[str, ...]:
    raw_hosts = os.getenv("ANALYSIS_SOURCE_HOSTS")
    if not raw_hosts:
        return DEFAULT_SOURCE_HOSTS

    hosts = []
    for raw_host in raw_hosts.split(","):
        candidate = raw_host.strip()
        if not candidate:
            continue
        parsed = urlsplit(candidate if "://" in candidate else f"//{candidate}")
        hostname = (parsed.hostname or "").rstrip(".").lower()
        if hostname and hostname not in hosts:
            hosts.append(hostname)
    return tuple(hosts) or DEFAULT_SOURCE_HOSTS


def source_url_filter(column, hosts: tuple[str, ...] | None = None):
    selected_hosts = hosts or configured_source_hosts()
    if not selected_hosts:
        raise ValueError("At least one analysis source host is required.")
    return or_(*(column.like(f"https://{host}/%") for host in selected_hosts))
