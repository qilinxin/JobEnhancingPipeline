-- Persist the evidence ledger separately from narrative match details.
ALTER TABLE public.linkedin_job_captures
    ADD COLUMN IF NOT EXISTS match_breakdown jsonb;

CREATE OR REPLACE FUNCTION public.invalidate_match_breakdown()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (NEW.title, NEW.description, NEW.clearance_required, NEW.citizenship_pr_required)
       IS DISTINCT FROM (OLD.title, OLD.description, OLD.clearance_required, OLD.citizenship_pr_required)
       OR NEW.match_score IS NULL THEN
        NEW.match_breakdown := NULL;
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS invalidate_match_breakdown ON public.linkedin_job_captures;
CREATE TRIGGER invalidate_match_breakdown BEFORE UPDATE
ON public.linkedin_job_captures FOR EACH ROW EXECUTE FUNCTION public.invalidate_match_breakdown();
