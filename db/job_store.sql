BEGIN;

CREATE TABLE IF NOT EXISTS analysis_jobs (
    id           VARCHAR(32) PRIMARY KEY,
    operation    VARCHAR(50) NOT NULL,
    status       VARCHAR(20) NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL,
    started_at   TIMESTAMPTZ,
    finished_at  TIMESTAMPTZ,
    result       JSONB,
    error        TEXT
);

CREATE INDEX IF NOT EXISTS idx_analysis_jobs_status ON analysis_jobs(status);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_submitted_at ON analysis_jobs(submitted_at DESC);

COMMIT;
