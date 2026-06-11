from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base

class NewsSource(Base):
    __tablename__ = "news_sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    rss_url = Column(Text, nullable=False, unique=True)
    bias_label = Column(String(20), default="unknown")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    articles = relationship("Article", back_populates="source")

class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("news_sources.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=False)
    content = Column(Text)
    url = Column(Text, nullable=False, unique=True)
    published_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    source = relationship("NewsSource", back_populates="articles")
    groups = relationship("ArticleGroupMember", back_populates="article")

class ArticleGroup(Base):
    __tablename__ = "article_groups"

    id = Column(Integer, primary_key=True, index=True)
    topic_title = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    members = relationship("ArticleGroupMember", back_populates="group")

class ArticleGroupMember(Base):
    __tablename__ = "article_group_members"

    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), primary_key=True)
    group_id = Column(Integer, ForeignKey("article_groups.id", ondelete="CASCADE"), primary_key=True)

    article = relationship("Article", back_populates="groups")
    group = relationship("ArticleGroup", back_populates="members")

from sqlalchemy.dialects.postgresql import JSONB

class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True)
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

    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    author = Column(String(100), default="익명")
    likes = Column(Integer, default=0)
    dislikes = Column(Integer, default=0)
    collected_at = Column(DateTime(timezone=True), server_default=func.now())

    article = relationship("Article")

class CommentAnalysis(Base):
    __tablename__ = "comment_analysis"

    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True, unique=True)
    total_comments = Column(Integer, default=0)
    avg_sentiment = Column(Float)
    positive_ratio = Column(Float)
    negative_ratio = Column(Float)
    neutral_ratio = Column(Float)
    public_opinion = Column(Text)
    raw_response = Column(JSONB)
    analyzed_at = Column(DateTime(timezone=True), server_default=func.now())

    article = relationship("Article")
