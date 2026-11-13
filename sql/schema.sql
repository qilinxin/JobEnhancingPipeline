BEGIN;

CREATE TABLE linkedin_searches (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    search_url text NOT NULL,
    enabled boolean NOT NULL DEFAULT true
);

CREATE TABLE linkedin_collection_runs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    search_id bigint NOT NULL REFERENCES linkedin_searches (id),
    search_url_used text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status text NOT NULL DEFAULT 'running',
    error_message text,

    CONSTRAINT linkedin_collection_runs_status_check
        CHECK (status IN ('running', 'succeeded', 'partial', 'failed')),

    CONSTRAINT linkedin_collection_runs_finish_check
        CHECK (
            (status = 'running' AND finished_at IS NULL)
            OR (
                status IN ('succeeded', 'partial', 'failed')
                AND finished_at IS NOT NULL
                AND finished_at >= started_at
            )
        )
);

CREATE TABLE linkedin_jobs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    linkedin_job_id text UNIQUE,
    canonical_url text NOT NULL UNIQUE,
    applied_at timestamptz,
    excluded_at timestamptz
);

CREATE TABLE linkedin_company_blacklist (
    company_key text PRIMARY KEY,
    company_name text NOT NULL,
    reason text NOT NULL DEFAULT '',
    added_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE linkedin_job_captures (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id bigint NOT NULL REFERENCES linkedin_collection_runs (id),
    job_id bigint NOT NULL REFERENCES linkedin_jobs (id),
    captured_at timestamptz NOT NULL,
    title text NOT NULL,
    company text,
    company_key text,
    location text,
    description text NOT NULL,
    posted_label text,
    posted_at timestamptz,
    capture_kind text NOT NULL DEFAULT 'new'
        CHECK (capture_kind IN ('new', 'repost', 'duplicate')),
    posting_fingerprint text,
    key_technologies text[] NOT NULL DEFAULT '{}',
    salary_text text,
    match_score numeric(5, 2) CHECK (match_score BETWEEN 0 AND 100),
    company_blacklisted boolean NOT NULL DEFAULT false
        CHECK (NOT company_blacklisted OR match_score IS NOT DISTINCT FROM 0),
    score_before_blacklist numeric(5, 2),
    match_details text,
    city text,
    delivery_model text CHECK (delivery_model IN ('In-house', 'Client delivery')),
    delivery_reviewed_at timestamptz,
    reviewed_delivery_model text CHECK (reviewed_delivery_model IN ('In-house', 'Client delivery')),
    delivery_review_notes text,
    delivery_review_sources text[],
    hiring_model text CHECK (hiring_model IN ('Direct hire', 'Outsourced')),
    clearance_required boolean NOT NULL DEFAULT false
        CHECK (NOT clearance_required OR match_score IS NOT DISTINCT FROM 0),

    CONSTRAINT linkedin_job_captures_run_job_key
        UNIQUE (run_id, job_id)
);

CREATE INDEX linkedin_collection_runs_search_time_idx
    ON linkedin_collection_runs (search_id, started_at DESC);

CREATE INDEX linkedin_job_captures_job_time_idx
    ON linkedin_job_captures (job_id, captured_at DESC);

CREATE INDEX linkedin_job_captures_company_key_idx
    ON linkedin_job_captures (company_key);

CREATE INDEX linkedin_job_captures_posting_fingerprint_idx
    ON linkedin_job_captures (posting_fingerprint, run_id)
    WHERE posting_fingerprint IS NOT NULL;

COMMIT;
