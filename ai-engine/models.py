from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base

JOB_RESULT_TYPE = JSON().with_variant(JSONB(), "postgresql")


class NewsSource(Base):
    __tablename__ = "news_sources"

    id = Column(BigInteger, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    rss_url = Column(Text, nullable=False, unique=True)
    bias_label = Column(String(20), default="unknown")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    articles = relationship("Article", back_populates="source")


class Article(Base):
    __tablename__ = "articles"

    id = Column(BigInteger, primary_key=True, index=True)
    source_id = Column(
        BigInteger, ForeignKey("news_sources.id", ondelete="CASCADE"), nullable=False
    )
    title = Column(Text, nullable=False)
    content = Column(Text)
    url = Column(Text, nullable=False, unique=True)
    published_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    source = relationship("NewsSource", back_populates="articles")
    groups = relationship("ArticleGroupMember", back_populates="article")


class ArticleGroup(Base):
    __tablename__ = "article_groups"

    id = Column(BigInteger, primary_key=True, index=True)
    topic_title = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    members = relationship("ArticleGroupMember", back_populates="group")


class ArticleGroupMember(Base):
    __tablename__ = "article_group_members"

    article_id = Column(
        BigInteger, ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True
    )
    group_id = Column(
        BigInteger,
        ForeignKey("article_groups.id", ondelete="CASCADE"),
        primary_key=True,
    )

    article = relationship("Article", back_populates="groups")
    group = relationship("ArticleGroup", back_populates="members")


class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    __table_args__ = (
        CheckConstraint(
            "sentiment_score BETWEEN -1.0 AND 1.0", name="ck_analysis_sentiment"
        ),
        CheckConstraint("bias_score BETWEEN 0.0 AND 1.0", name="ck_analysis_bias"),
        CheckConstraint(
            "factuality_score BETWEEN 0.0 AND 1.0", name="ck_analysis_factuality"
        ),
        UniqueConstraint("article_id", "model_used", name="uq_analysis_article_model"),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    article_id = Column(
        BigInteger,
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_used = Column(String(50), nullable=False)
    sentiment_score = Column(Float)
    bias_score = Column(Float)
    factuality_score = Column(Float)
    summary = Column(Text)
    raw_response = Column(JSONB)
    analyzed_at = Column(DateTime(timezone=True), server_default=func.now())

    article = relationship("Article")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(BigInteger, primary_key=True, index=True)
    article_id = Column(
        BigInteger,
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content = Column(Text, nullable=False)
    author = Column(String(100), default="익명")
    likes = Column(Integer, default=0)
    dislikes = Column(Integer, default=0)
    collected_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("likes >= 0 AND dislikes >= 0", name="ck_comments_reactions_nonnegative"),
    )

    article = relationship("Article")


class CommentAnalysis(Base):
    __tablename__ = "comment_analysis"
    __table_args__ = (
        CheckConstraint(
            "avg_sentiment BETWEEN -1.0 AND 1.0", name="ck_comment_avg_sentiment"
        ),
        CheckConstraint(
            "positive_ratio BETWEEN 0.0 AND 1.0", name="ck_comment_positive_ratio"
        ),
        CheckConstraint(
            "negative_ratio BETWEEN 0.0 AND 1.0", name="ck_comment_negative_ratio"
        ),
        CheckConstraint(
            "neutral_ratio BETWEEN 0.0 AND 1.0", name="ck_comment_neutral_ratio"
        ),
        CheckConstraint(
            "ABS(positive_ratio + negative_ratio + neutral_ratio - 1.0) <= 0.02",
            name="ck_comment_ratio_sum",
        ),
        CheckConstraint(
            "total_comments >= 0 AND analyzed_comments >= 0 AND analyzed_comments <= total_comments",
            name="ck_comment_counts",
        ),
    )

    id = Column(BigInteger, primary_key=True, index=True)
    article_id = Column(
        BigInteger,
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
    )
    total_comments = Column(Integer, default=0)
    analyzed_comments = Column(Integer, default=0)
    avg_sentiment = Column(Float)
    positive_ratio = Column(Float)
    negative_ratio = Column(Float)
    neutral_ratio = Column(Float)
    public_opinion = Column(Text)
    raw_response = Column(JSONB)
    analyzed_at = Column(DateTime(timezone=True), server_default=func.now())

    article = relationship("Article")


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id = Column(String(32), primary_key=True)
    operation = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, index=True)
    submitted_at = Column(DateTime(timezone=True), nullable=False)
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))
    result = Column(JOB_RESULT_TYPE)
    error = Column(Text)
