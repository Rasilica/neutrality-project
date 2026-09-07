import os
import socket

import pytest

import network_security

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault(
    "CRAWLER_ALLOWED_HOSTS",
    "example.com,rss.invalid,news.sbs.co.kr,rss.naver.com,n.news.naver.com,news.naver.com",
)


@pytest.fixture(autouse=True)
def deterministic_public_dns(monkeypatch):
    def resolve(_host, port, type=socket.SOCK_STREAM):
        return [
            (
                socket.AF_INET,
                type,
                socket.IPPROTO_TCP,
                "",
                ("93.184.216.34", port),
            )
        ]

    monkeypatch.setattr(network_security.socket, "getaddrinfo", resolve)
