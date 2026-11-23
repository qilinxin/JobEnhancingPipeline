ALTER TABLE public.linkedin_job_captures
    ADD COLUMN IF NOT EXISTS capture_kind text NOT NULL DEFAULT 'new'
        CHECK (capture_kind IN ('new', 'repost', 'duplicate')),
    ADD COLUMN IF NOT EXISTS posting_fingerprint text,
    ADD COLUMN IF NOT EXISTS key_technologies text[] NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS linkedin_job_captures_posting_fingerprint_idx
    ON public.linkedin_job_captures (posting_fingerprint, run_id)
    WHERE posting_fingerprint IS NOT NULL;
