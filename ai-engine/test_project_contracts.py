from pathlib import Path

import pytest
from sqlalchemy import BigInteger

import database
import models

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_sqlalchemy_identifier_columns_match_postgres_bigint_schema():
    identifier_columns = [
        models.NewsSource.id,
        models.Article.id,
        models.Article.source_id,
        models.ArticleGroup.id,
        models.ArticleGroupMember.article_id,
        models.ArticleGroupMember.group_id,
        models.AnalysisResult.id,
        models.AnalysisResult.article_id,
        models.Comment.id,
        models.Comment.article_id,
        models.CommentAnalysis.id,
        models.CommentAnalysis.article_id,
    ]

    assert all(isinstance(column.type, BigInteger) for column in identifier_columns)


def test_application_does_not_create_database_schema_on_import():
    main_source = (PROJECT_ROOT / "ai-engine" / "main.py").read_text()

    assert "metadata.create_all" not in main_source


def test_google_provider_uses_supported_google_genai_sdk():
    provider_sources = [
        (PROJECT_ROOT / "ai-engine" / "analyzer.py").read_text(),
        (PROJECT_ROOT / "ai-engine" / "comment_analyzer.py").read_text(),
    ]

    assert all("google.generativeai" not in source for source in provider_sources)
    assert all("from google import genai" in source for source in provider_sources)


def test_compose_avoids_global_names_and_defines_healthchecks():
    compose_source = (PROJECT_ROOT / "docker-compose.yml").read_text()

    assert "container_name:" not in compose_source
    assert compose_source.count("healthcheck:") >= 3
    assert "condition: service_healthy" in compose_source


def test_api_server_image_builds_the_jar_in_a_builder_stage():
    dockerfile = (PROJECT_ROOT / "api-server" / "Dockerfile").read_text()

    assert " AS build" in dockerfile
    assert "COPY --from=build" in dockerfile
    assert "mkdir -p /app/logs" in dockerfile


def test_database_url_prefers_an_explicit_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")

    assert database.build_database_url() == "sqlite+pysqlite:///:memory:"


def test_database_url_safely_builds_from_postgres_parts(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("POSTGRES_USER", "news-user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p@ss/word")
    monkeypatch.setenv("POSTGRES_DB", "news_db")
    monkeypatch.setenv("POSTGRES_HOST", "db")

    url = database.build_database_url()

    assert url.drivername == "postgresql+psycopg2"
    assert url.username == "news-user"
    assert url.password == "p@ss/word"
    assert url.host == "db"


def test_database_url_rejects_missing_required_configuration(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_USER", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    monkeypatch.delenv("POSTGRES_DB", raising=False)

    with pytest.raises(RuntimeError, match="POSTGRES_USER"):
        database.build_database_url()


def test_spring_database_password_has_no_hardcoded_fallback():
    application_config = (
        PROJECT_ROOT / "api-server" / "src" / "main" / "resources" / "application.yml"
    ).read_text()

    assert "devpassword" not in application_config
    assert "url: ${SPRING_DATASOURCE_URL}" in application_config
    assert "username: ${SPRING_DATASOURCE_USERNAME}" in application_config
    assert "password: ${SPRING_DATASOURCE_PASSWORD}" in application_config
