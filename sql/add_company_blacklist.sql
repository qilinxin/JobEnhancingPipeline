CREATE TABLE IF NOT EXISTS public.linkedin_company_blacklist (
    company_key text PRIMARY KEY,
    company_name text NOT NULL,
    reason text NOT NULL DEFAULT '',
    added_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.linkedin_job_captures
    ADD COLUMN IF NOT EXISTS company_key text,
    ADD COLUMN IF NOT EXISTS company_blacklisted boolean NOT NULL DEFAULT false
        CHECK (NOT company_blacklisted OR match_score IS NOT DISTINCT FROM 0),
    ADD COLUMN IF NOT EXISTS score_before_blacklist numeric(5, 2);

CREATE INDEX IF NOT EXISTS linkedin_job_captures_company_key_idx
    ON public.linkedin_job_captures (company_key);
