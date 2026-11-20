-- Suppress equivalent cross-platform postings before scoring and display.
BEGIN;
ALTER TABLE public.linkedin_job_captures
    ADD COLUMN IF NOT EXISTS display_identity text,
    ADD COLUMN IF NOT EXISTS display_duplicate_of bigint REFERENCES public.linkedin_job_captures(id);

CREATE OR REPLACE FUNCTION public.job_display_identity(job_title text, company_text text, job_location text, jd text)
RETURNS text LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    company_name text;
    city text;
    words text[];
    body text;
BEGIN
    company_name := split_part(lower(coalesce(company_text,'')), '•', 1);
    company_name := replace(company_name, lower(job_title), '');
    company_name := regexp_replace(company_name, '\m(pty|ltd|limited)\M', '', 'g');
    company_name := regexp_replace(company_name, '[^[:alnum:]]', '', 'g');
    city := substring(lower(coalesce(nullif(job_location,''),split_part(company_text,'•',2)))
                      from '(sydney|melbourne|brisbane|perth|adelaide|canberra|hobart|darwin)');
    IF company_name = '' OR city IS NULL THEN RETURN NULL; END IF;
    body := regexp_replace(lower(coalesce(jd,'')), E'(?m)^\\s*desired skills and experience\\s*$', '', 'g');
    SELECT array_agg(token ORDER BY token) INTO words FROM (
        SELECT DISTINCT token FROM regexp_split_to_table(body, '[^[:alnum:]]+') token WHERE token <> ''
    ) vocabulary;
    -- Short generic templates do not contain enough evidence to merge safely.
    IF cardinality(words) < 80 THEN RETURN NULL; END IF;
    RETURN md5(lower(regexp_replace(job_title,'[[:space:]]+',' ','g')) || '|' || company_name || '|' || city || '|' || array_to_string(words,'|'));
END;
$$;
CREATE INDEX IF NOT EXISTS captures_display_identity_idx ON public.linkedin_job_captures(display_identity);

CREATE OR REPLACE FUNCTION public.suppress_display_duplicate()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    original bigint;
BEGIN
    NEW.display_identity := public.job_display_identity(NEW.title,NEW.company,NEW.location,NEW.description);
    NEW.display_duplicate_of := NULL;
    IF NEW.display_identity IS NOT NULL THEN
        -- Serialize competing platform captures of the same identity.
        PERFORM pg_advisory_xact_lock(hashtextextended(NEW.display_identity, 7));
        SELECT c.id INTO original FROM public.linkedin_job_captures c
        WHERE c.display_identity=NEW.display_identity AND c.id < NEW.id
          AND c.job_id <> NEW.job_id AND c.capture_kind <> 'duplicate'
          AND c.display_duplicate_of IS NULL
          AND (c.captured_at AT TIME ZONE 'Australia/Sydney')::date = (NEW.captured_at AT TIME ZONE 'Australia/Sydney')::date
        ORDER BY c.id LIMIT 1;
        IF original IS NOT NULL THEN
            NEW.display_duplicate_of := original;
            NEW.capture_kind := 'duplicate';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS suppress_display_duplicate ON public.linkedin_job_captures;
CREATE TRIGGER suppress_display_duplicate
BEFORE INSERT OR UPDATE OF title,company,location,description,posting_fingerprint
ON public.linkedin_job_captures FOR EACH ROW EXECUTE FUNCTION public.suppress_display_duplicate();

UPDATE public.linkedin_job_captures
SET display_identity=public.job_display_identity(title,company,location,description);
UPDATE public.linkedin_job_captures SET description=description WHERE display_identity IS NOT NULL;
COMMIT;
