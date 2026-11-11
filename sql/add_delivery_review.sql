ALTER TABLE public.linkedin_job_captures
    ADD COLUMN IF NOT EXISTS delivery_reviewed_at timestamptz,
    ADD COLUMN IF NOT EXISTS reviewed_delivery_model text
        CHECK (reviewed_delivery_model IN ('In-house', 'Client delivery')),
    ADD COLUMN IF NOT EXISTS delivery_review_notes text,
    ADD COLUMN IF NOT EXISTS delivery_review_sources text[];
