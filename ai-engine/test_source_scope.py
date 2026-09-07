from sqlalchemy import Column, Integer, MetaData, Table

from source_scope import configured_source_hosts, source_url_filter


def test_configured_source_hosts_uses_default_and_normalizes_values(monkeypatch):
    monkeypatch.delenv("ANALYSIS_SOURCE_HOSTS", raising=False)
    assert configured_source_hosts() == ("news.sbs.co.kr",)

    monkeypatch.setenv(
        "ANALYSIS_SOURCE_HOSTS",
        " https://news.example.com/path, news.sbs.co.kr, ,NEWS.EXAMPLE.COM ",
    )
    assert configured_source_hosts() == ("news.example.com", "news.sbs.co.kr")


def test_source_url_filter_uses_https_host_boundary():
    table = Table("articles", MetaData(), Column("url", Integer))
    expression = source_url_filter(table.c.url, ("news.example.com", "news.sbs.co.kr"))
    values = {clause.right.value for clause in expression.clauses}

    assert values == {"https://news.example.com/%", "https://news.sbs.co.kr/%"}
