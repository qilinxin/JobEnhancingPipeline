ALTER TABLE public.linkedin_job_captures
    ADD COLUMN IF NOT EXISTS match_score numeric(5, 2) CHECK (match_score BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS match_details text;
