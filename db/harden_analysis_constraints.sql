BEGIN;

ALTER TABLE comment_analysis
    ADD COLUMN IF NOT EXISTS analyzed_comments INT NOT NULL DEFAULT 0;

ALTER TABLE comment_analysis
    DROP CONSTRAINT IF EXISTS ck_comment_counts,
    ADD CONSTRAINT ck_comment_counts CHECK (
        total_comments >= 0 AND analyzed_comments >= 0 AND analyzed_comments <= total_comments
    ) NOT VALID;

CREATE UNIQUE INDEX IF NOT EXISTS uq_analysis_article_model
    ON analysis_results (article_id, model_used);

ALTER TABLE analysis_results
    DROP CONSTRAINT IF EXISTS ck_analysis_sentiment,
    DROP CONSTRAINT IF EXISTS ck_analysis_bias,
    DROP CONSTRAINT IF EXISTS ck_analysis_factuality,
    ADD CONSTRAINT ck_analysis_sentiment CHECK (sentiment_score BETWEEN -1.0 AND 1.0) NOT VALID,
    ADD CONSTRAINT ck_analysis_bias CHECK (bias_score BETWEEN 0.0 AND 1.0) NOT VALID,
    ADD CONSTRAINT ck_analysis_factuality CHECK (factuality_score BETWEEN 0.0 AND 1.0) NOT VALID;

ALTER TABLE comment_analysis
    DROP CONSTRAINT IF EXISTS ck_comment_avg_sentiment,
    DROP CONSTRAINT IF EXISTS ck_comment_positive_ratio,
    DROP CONSTRAINT IF EXISTS ck_comment_negative_ratio,
    DROP CONSTRAINT IF EXISTS ck_comment_neutral_ratio,
    DROP CONSTRAINT IF EXISTS ck_comment_ratio_sum,
    ADD CONSTRAINT ck_comment_avg_sentiment CHECK (avg_sentiment BETWEEN -1.0 AND 1.0) NOT VALID,
    ADD CONSTRAINT ck_comment_positive_ratio CHECK (positive_ratio BETWEEN 0.0 AND 1.0) NOT VALID,
    ADD CONSTRAINT ck_comment_negative_ratio CHECK (negative_ratio BETWEEN 0.0 AND 1.0) NOT VALID,
    ADD CONSTRAINT ck_comment_neutral_ratio CHECK (neutral_ratio BETWEEN 0.0 AND 1.0) NOT VALID,
    ADD CONSTRAINT ck_comment_ratio_sum CHECK (
        ABS(positive_ratio + negative_ratio + neutral_ratio - 1.0) <= 0.02
    ) NOT VALID;

ALTER TABLE analysis_results
    VALIDATE CONSTRAINT ck_analysis_sentiment,
    VALIDATE CONSTRAINT ck_analysis_bias,
    VALIDATE CONSTRAINT ck_analysis_factuality;

ALTER TABLE comment_analysis
    VALIDATE CONSTRAINT ck_comment_avg_sentiment,
    VALIDATE CONSTRAINT ck_comment_positive_ratio,
    VALIDATE CONSTRAINT ck_comment_negative_ratio,
    VALIDATE CONSTRAINT ck_comment_neutral_ratio,
    VALIDATE CONSTRAINT ck_comment_ratio_sum;

COMMIT;
