-- ================================================================
-- [2주차] 하이브리드 AI 뉴스 중립성 분석 플랫폼 - DB 스키마 정의
-- ================================================================

-- 1. 언론사(뉴스 출처) 테이블
CREATE TABLE IF NOT EXISTS news_sources (
    id          BIGSERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,  -- 언론사 이름 (e.g., '조선일보', 'KBS')
    rss_url     TEXT         NOT NULL UNIQUE,  -- RSS 피드 URL
    bias_label  VARCHAR(20)  DEFAULT 'unknown', -- 예상 성향 라벨 (left, center, right, unknown)
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 2. 뉴스 기사 원문 테이블
CREATE TABLE IF NOT EXISTS articles (
    id          BIGSERIAL PRIMARY KEY,
    source_id   BIGINT       NOT NULL REFERENCES news_sources(id) ON DELETE CASCADE,
    title       TEXT         NOT NULL,          -- 기사 제목
    content     TEXT,                           -- 기사 본문
    url         TEXT         NOT NULL UNIQUE,   -- 기사 원문 URL (중복 수집 방지 키)
    published_at TIMESTAMPTZ,                   -- 기사 발행 시각
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_articles_source_id    ON articles(source_id);
CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_source_published_at
    ON articles USING BTREE (source_id, published_at DESC);

-- 3. 기사 그룹 테이블 (동일 사건을 다루는 기사 묶음, 4주차 클러스터링 기반)
CREATE TABLE IF NOT EXISTS article_groups (
    id           BIGSERIAL PRIMARY KEY,
    topic_title  TEXT        NOT NULL,           -- 그룹이 다루는 사건/주제 제목
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 기사-그룹 N:M 매핑 테이블
CREATE TABLE IF NOT EXISTS article_group_members (
    article_id BIGINT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    group_id   BIGINT NOT NULL REFERENCES article_groups(id) ON DELETE CASCADE,
    PRIMARY KEY (article_id, group_id)
);

-- 4. AI 중립성 분석 결과 테이블
CREATE TABLE IF NOT EXISTS analysis_results (
    id                 BIGSERIAL PRIMARY KEY,
    article_id         BIGINT       NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    model_used         VARCHAR(50)  NOT NULL,  -- 분석에 사용된 모델 (e.g., 'gemini-1.5-pro', 'gpt-4o', 'qwen3')
    sentiment_score    FLOAT,                  -- 감정 분석 점수 (-1.0 ~ 1.0, 부정~긍정)
    bias_score         FLOAT,                  -- 편향성 점수 (0.0 ~ 1.0)
    factuality_score   FLOAT,                  -- 사실 기반 점수 (0.0 ~ 1.0)
    summary            TEXT,                   -- AI가 생성한 기사 요약
    raw_response       JSONB,                  -- AI 원본 응답 (전체 JSON 보존)
    analyzed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_analysis_results_article_id ON analysis_results(article_id);
CREATE INDEX IF NOT EXISTS idx_analysis_results_article_model
    ON analysis_results USING BTREE (article_id, model_used);

-- 5. LLM 파인튜닝 학습 데이터 테이블 (ChatML 형식, 7주차 기반)
CREATE TABLE IF NOT EXISTS fine_tuning_data (
    id           BIGSERIAL PRIMARY KEY,
    source_type  VARCHAR(50) NOT NULL DEFAULT 'ai_analysis', -- 데이터 출처 구분
    instruction  TEXT        NOT NULL,  -- system / user instruction
    input        TEXT,                  -- 모델 입력 (기사 본문 등)
    output       TEXT        NOT NULL,  -- 모델 기대 출력 (편향 분석 결과)
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 6. 뉴스 기사 댓글 테이블 (10주차 - 댓글 분석 시스템)
CREATE TABLE IF NOT EXISTS comments (
    id           BIGSERIAL PRIMARY KEY,
    article_id   BIGINT       NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    content      TEXT         NOT NULL,           -- 댓글 본문
    author       VARCHAR(100) DEFAULT '익명',     -- 마스킹된 작성자 ID
    likes        INT          DEFAULT 0,          -- 공감 수
    dislikes     INT          DEFAULT 0,          -- 비공감 수
    collected_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_comments_article_id ON comments(article_id);

-- 7. 댓글 여론 분석 결과 테이블 (10주차 - AI 기반 여론 종합 분석)
CREATE TABLE IF NOT EXISTS comment_analysis (
    id              BIGSERIAL PRIMARY KEY,
    article_id      BIGINT       NOT NULL REFERENCES articles(id) ON DELETE CASCADE UNIQUE,
    total_comments  INT          DEFAULT 0,       -- 분석 대상 댓글 수
    avg_sentiment   FLOAT,                        -- 평균 감정 점수 (-1.0 ~ 1.0)
    positive_ratio  FLOAT,                        -- 긍정 댓글 비율 (0.0 ~ 1.0)
    negative_ratio  FLOAT,                        -- 부정 댓글 비율 (0.0 ~ 1.0)
    neutral_ratio   FLOAT,                        -- 중립 댓글 비율 (0.0 ~ 1.0)
    public_opinion  TEXT,                         -- AI가 종합한 여론 요약
    raw_response    JSONB,                        -- AI 원본 응답
    analyzed_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_comment_analysis_article_id ON comment_analysis(article_id);

-- 완료 메시지
DO $$
BEGIN
    RAISE NOTICE '[news_db] ✅ Schema initialized successfully. Tables: news_sources, articles, article_groups, article_group_members, analysis_results, fine_tuning_data, comments, comment_analysis';
END $$;
