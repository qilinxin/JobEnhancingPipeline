-- Mandatory citizenship/PR restrictions are incompatible with the confirmed 485 visa.
BEGIN;
ALTER TABLE public.linkedin_job_captures
    ADD COLUMN IF NOT EXISTS citizenship_pr_required boolean NOT NULL DEFAULT false;

CREATE OR REPLACE FUNCTION public.requires_citizenship_pr(job_text text)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    clause text;
    status_term text := '(Australian([ /-]+or[ /-]+(NZ|New Zealand))?[[:space:]]+citizens?(hip)?|permanent[[:space:]]+residen(ts?|cy)|\mPR\M)';
BEGIN
    FOR clause IN SELECT regexp_split_to_table(coalesce(job_text, ''), E'\\n|[.!?;][[:space:]]+') LOOP
        clause := regexp_replace(clause, '[[:space:]]+', ' ', 'g');
        IF clause !~* status_term THEN CONTINUE; END IF;
        -- PR can also mean pull request; require residency context for the abbreviation.
        IF clause !~* '(citizen|permanent[[:space:]]+residen|Australian)'
           AND clause !~* '(must (hold|have).{0,15}\mPR\M|\mPR\M (is )?(required|mandatory)|only PR|PR holders)' THEN
            CONTINUE;
        END IF;
        -- An explicit visa/work-rights alternative also accepts the applicant's status.
        IF clause ~* '(or|including|accept|welcome).{0,100}(valid|appropriate|temporary|work|485).{0,35}visa'
           OR clause ~* '(or|including).{0,100}(work entitlements|unrestricted (Australian )?work(ing)? rights|full (Australian )?work(ing)? rights)' THEN
            CONTINUE;
        END IF;
        IF clause ~* (status_term || '.{0,20}(not required|not mandatory|not necessary|optional|preferred|desirable)')
           OR clause ~* ('(not require|do not require|no requirement for|no need for).{0,30}' || status_term)
           OR clause ~* ('(optional|preferred|desirable)[ :]{0,5}' || status_term) THEN
            CONTINUE;
        END IF;
        IF clause ~* '\m(must|required?|mandatory|only|essential|need)\M'
           OR clause ~* '(to be eligible|to be considered)'
           OR clause ~* ('^[[:space:]*•-]*' || status_term || '[[:space:][:punct:]]*$') THEN
            RETURN true;
        END IF;
    END LOOP;
    RETURN false;
END;
$$;

CREATE OR REPLACE FUNCTION public.enforce_citizenship_pr_score()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.citizenship_pr_required := public.requires_citizenship_pr(NEW.title || E'\n' || NEW.description);
    IF NEW.citizenship_pr_required THEN
        NEW.match_score := 0;
        NEW.match_details := 'Mandatory Australian citizenship or permanent residency is required. The confirmed subclass 485 visa does not meet this restriction. Match score is 0.';
    ELSIF TG_OP = 'UPDATE' THEN
        IF OLD.citizenship_pr_required THEN
            -- A corrected JD must be assessed again; never restore a stale score.
            NEW.match_score := CASE WHEN NEW.clearance_required OR NEW.company_blacklisted THEN 0 ELSE NULL END;
            NEW.match_details := NULL;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS enforce_citizenship_pr_score ON public.linkedin_job_captures;
CREATE TRIGGER enforce_citizenship_pr_score BEFORE INSERT OR UPDATE
ON public.linkedin_job_captures FOR EACH ROW EXECUTE FUNCTION public.enforce_citizenship_pr_score();

-- Apply the exact same rule to historical records without changing their JDs.
UPDATE public.linkedin_job_captures SET citizenship_pr_required = citizenship_pr_required
WHERE citizenship_pr_required IS DISTINCT FROM public.requires_citizenship_pr(title || E'\n' || description);
ALTER TABLE public.linkedin_job_captures DROP CONSTRAINT IF EXISTS citizenship_pr_zero_score;
ALTER TABLE public.linkedin_job_captures ADD CONSTRAINT citizenship_pr_zero_score
CHECK (NOT citizenship_pr_required OR match_score IS NOT DISTINCT FROM 0);
COMMIT;
