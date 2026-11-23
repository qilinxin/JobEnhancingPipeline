SELECT c.run_id,
       c.title,
       j.canonical_url,
       c.description,
       c.captured_at
FROM public.linkedin_job_captures AS c
JOIN public.linkedin_jobs AS j ON j.id = c.job_id
ORDER BY c.captured_at DESC, c.id DESC
LIMIT 1;
