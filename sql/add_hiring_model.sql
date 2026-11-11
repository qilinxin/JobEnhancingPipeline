ALTER TABLE public.linkedin_job_captures
    ADD COLUMN IF NOT EXISTS hiring_model text
        CHECK (hiring_model IN ('Direct hire', 'Outsourced'));
