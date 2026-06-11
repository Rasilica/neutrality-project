BEGIN;

ALTER TABLE IF EXISTS analysis_results
    DROP CONSTRAINT IF EXISTS analysis_results_article_id_fkey;
ALTER TABLE IF EXISTS article_group_members
    DROP CONSTRAINT IF EXISTS article_group_members_article_id_fkey,
    DROP CONSTRAINT IF EXISTS article_group_members_group_id_fkey;
ALTER TABLE IF EXISTS articles
    DROP CONSTRAINT IF EXISTS articles_source_id_fkey;
ALTER TABLE IF EXISTS comment_analysis
    DROP CONSTRAINT IF EXISTS comment_analysis_article_id_fkey;
ALTER TABLE IF EXISTS comments
    DROP CONSTRAINT IF EXISTS comments_article_id_fkey;

ALTER TABLE IF EXISTS news_sources
    ALTER COLUMN id TYPE BIGINT;
ALTER SEQUENCE IF EXISTS news_sources_id_seq AS BIGINT;

ALTER TABLE IF EXISTS articles
    ALTER COLUMN id TYPE BIGINT,
    ALTER COLUMN source_id TYPE BIGINT;
ALTER SEQUENCE IF EXISTS articles_id_seq AS BIGINT;

ALTER TABLE IF EXISTS article_groups
    ALTER COLUMN id TYPE BIGINT;
ALTER SEQUENCE IF EXISTS article_groups_id_seq AS BIGINT;

ALTER TABLE IF EXISTS article_group_members
    ALTER COLUMN article_id TYPE BIGINT,
    ALTER COLUMN group_id TYPE BIGINT;

ALTER TABLE IF EXISTS analysis_results
    ALTER COLUMN id TYPE BIGINT,
    ALTER COLUMN article_id TYPE BIGINT;
ALTER SEQUENCE IF EXISTS analysis_results_id_seq AS BIGINT;

ALTER TABLE IF EXISTS fine_tuning_data
    ALTER COLUMN id TYPE BIGINT;
ALTER SEQUENCE IF EXISTS fine_tuning_data_id_seq AS BIGINT;

ALTER TABLE IF EXISTS comments
    ALTER COLUMN id TYPE BIGINT,
    ALTER COLUMN article_id TYPE BIGINT;
ALTER SEQUENCE IF EXISTS comments_id_seq AS BIGINT;

ALTER TABLE IF EXISTS comment_analysis
    ALTER COLUMN id TYPE BIGINT,
    ALTER COLUMN article_id TYPE BIGINT;
ALTER SEQUENCE IF EXISTS comment_analysis_id_seq AS BIGINT;

ALTER TABLE IF EXISTS articles
    ADD CONSTRAINT articles_source_id_fkey
    FOREIGN KEY (source_id) REFERENCES news_sources(id) ON DELETE CASCADE;
ALTER TABLE IF EXISTS article_group_members
    ADD CONSTRAINT article_group_members_article_id_fkey
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
    ADD CONSTRAINT article_group_members_group_id_fkey
    FOREIGN KEY (group_id) REFERENCES article_groups(id) ON DELETE CASCADE;
ALTER TABLE IF EXISTS analysis_results
    ADD CONSTRAINT analysis_results_article_id_fkey
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE;
ALTER TABLE IF EXISTS comments
    ADD CONSTRAINT comments_article_id_fkey
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE;
ALTER TABLE IF EXISTS comment_analysis
    ADD CONSTRAINT comment_analysis_article_id_fkey
    FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE;

COMMIT;
