ALTER TABLE public.linkedin_job_captures
    ADD COLUMN IF NOT EXISTS city text,
    ADD COLUMN IF NOT EXISTS delivery_model text CHECK (delivery_model IN ('In-house', 'Client delivery')),
    ADD COLUMN IF NOT EXISTS clearance_required boolean NOT NULL DEFAULT false
        CHECK (NOT clearance_required OR match_score IS NOT DISTINCT FROM 0);
