import json
from types import SimpleNamespace

import clustering as clustering_module
import worker as worker_module
from clustering import ArticleClusterer
from dataset_builder import DatasetBuilder
from models import ArticleGroup, ArticleGroupMember


class ChainQuery:
    def __init__(self, rows):
        self.rows = rows

    def outerjoin(self, *_args):
        return self

    def join(self, *_args):
        return self

    def filter(self, *_args):
        return self

    def all(self):
        return self.rows


class RecordingDb:
    def __init__(self, rows):
        self.rows = rows
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def query(self, *_targets):
        return ChainQuery(self.rows)

    def add(self, value):
        if isinstance(value, ArticleGroup) and value.id is None:
            value.id = 41
        self.added.append(value)

    def flush(self):
        return None

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed += 1


def test_clusterer_handles_empty_and_single_article_inputs():
    empty_result = ArticleClusterer(RecordingDb([])).run()
    one_result = ArticleClusterer(
        RecordingDb([SimpleNamespace(id=1, title="한 기사", content=None)])
    ).run()

    assert empty_result["clusters_created"] == 0
    assert one_result["message"] == "Not enough articles to form clusters."


def test_clusterer_creates_group_and_members_for_similar_articles():
    articles = [
        SimpleNamespace(id=1, title="같은 사건", content="공통 본문"),
        SimpleNamespace(id=2, title="같은 사건", content="공통 본문"),
    ]
    db = RecordingDb(articles)

    result = ArticleClusterer(db).run()

    groups = [value for value in db.added if isinstance(value, ArticleGroup)]
    members = [value for value in db.added if isinstance(value, ArticleGroupMember)]
    assert result == {
        "status": "success",
        "clusters_created": 1,
        "processed_articles": 2,
    }
    assert groups[0].topic_title == "같은 사건"
    assert {member.article_id for member in members} == {1, 2}
    assert db.commits == 1


def test_clusterer_rolls_back_vectorization_errors(monkeypatch):
    db = RecordingDb(
        [
            SimpleNamespace(id=1, title="기사 1", content="본문"),
            SimpleNamespace(id=2, title="기사 2", content="본문"),
        ]
    )

    class BrokenVectorizer:
        def __init__(self, **_kwargs):
            pass

        def fit_transform(self, _corpus):
            raise ValueError("cannot vectorize")

    monkeypatch.setattr(clustering_module, "TfidfVectorizer", BrokenVectorizer)

    result = ArticleClusterer(db).run()

    assert result["status"] == "error"
    assert result["message"] == "cannot vectorize"
    assert db.rollbacks == 1


def test_dataset_builder_handles_empty_and_writes_chatml(tmp_path):
    empty_builder = DatasetBuilder.__new__(DatasetBuilder)
    empty_builder.db = RecordingDb([])
    empty_builder.data_dir = str(tmp_path)
    assert empty_builder.build_chatml_dataset()["count"] == 0

    article = SimpleNamespace(title="기사", content="본문")
    analysis = SimpleNamespace(
        sentiment_score=0.1,
        bias_score=0.2,
        factuality_score=0.9,
        summary="요약",
    )
    builder = DatasetBuilder.__new__(DatasetBuilder)
    builder.db = RecordingDb([(article, analysis)])
    builder.data_dir = str(tmp_path)

    result = builder.build_chatml_dataset()
    record = json.loads((tmp_path / "chatml_dataset.jsonl").read_text().strip())

    assert result["count"] == 1
    assert record["messages"][1]["content"] == "[기사 제목]: 기사\n[기사 본문]: 본문"
    assert json.loads(record["messages"][2]["content"])["bias_score"] == 0.2


def test_dataset_builder_reports_output_file_errors(tmp_path):
    builder = DatasetBuilder.__new__(DatasetBuilder)
    builder.db = RecordingDb(
        [
            (
                SimpleNamespace(title="기사", content="본문"),
                SimpleNamespace(
                    sentiment_score=0.1,
                    bias_score=0.2,
                    factuality_score=0.9,
                    summary="요약",
                ),
            )
        ]
    )
    builder.data_dir = str(tmp_path / "missing" / "directory")

    result = builder.build_chatml_dataset()

    assert result["status"] == "error"
    assert result["count"] == 0


def test_worker_continues_after_a_failed_pipeline_step(monkeypatch):
    db = RecordingDb([])
    calls = []

    class SuccessfulStep:
        def __init__(self, _db):
            pass

        def run(self):
            calls.append("success")
            return {"status": "success"}

    class FailedStep:
        def __init__(self, _db):
            pass

        def run(self):
            calls.append("failure")
            raise RuntimeError("step failed")

    monkeypatch.setattr(worker_module, "SessionLocal", lambda: db)
    monkeypatch.setattr(worker_module, "RSSCrawler", FailedStep)
    for name in (
        "ArticleClusterer",
        "GeminiAnalyzer",
        "GPTAnalyzer",
        "CommentCrawler",
        "CommentAnalyzer",
    ):
        monkeypatch.setattr(worker_module, name, SuccessfulStep)

    worker_module.scheduled_pipeline()

    assert calls == ["failure", "success", "success", "success", "success", "success"]
    assert db.rollbacks == 1
    assert db.closed == 1
