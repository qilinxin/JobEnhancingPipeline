DO $migration$
BEGIN
    IF to_regclass('public.linkedin_title_blacklist') IS NULL THEN
        CREATE TABLE public.linkedin_title_blacklist (
            keyword text PRIMARY KEY,
            pattern text NOT NULL
        );

        INSERT INTO public.linkedin_title_blacklist (keyword, pattern) VALUES
            ('intern', $regex$(?<!\w)interns?(?!\w)$regex$),
            ('internship', $regex$(?<!\w)internships?(?!\w)$regex$),
            ('graduate', $regex$(?<!\w)graduates?(?!\w)$regex$),
            ('sales', $regex$(?<!\w)sales(?!\w)$regex$),
            ('pre-sales', $regex$(?<!\w)pre[\s-]?sales(?!\w)$regex$),
            ('business development', $regex$(?<!\w)business development(?!\w)$regex$),
            ('account executive', $regex$(?<!\w)account executive(?!\w)$regex$),
            ('account manager', $regex$(?<!\w)account manager(?!\w)$regex$),
            ('customer success', $regex$(?<!\w)customer success(?!\w)$regex$),
            ('marketing', $regex$(?<!\w)marketing(?!\w)$regex$),
            ('recruiter', $regex$(?<!\w)recruiter(?!\w)$regex$),
            ('recruitment consultant', $regex$(?<!\w)recruitment consultant(?!\w)$regex$),
            ('talent acquisition', $regex$(?<!\w)talent acquisition(?!\w)$regex$),
            ('human resources', $regex$(?<!\w)human resources(?!\w)$regex$),
            ('accountant', $regex$(?<!\w)accountant(?!\w)$regex$),
            ('financial controller', $regex$(?<!\w)financial controller(?!\w)$regex$),
            ('solicitor', $regex$(?<!\w)solicitor(?!\w)$regex$),
            ('lawyer', $regex$(?<!\w)lawyer(?!\w)$regex$),
            ('legal counsel', $regex$(?<!\w)legal counsel(?!\w)$regex$),
            ('administrative officer', $regex$(?<!\w)administrative officer(?!\w)$regex$),
            ('administration officer', $regex$(?<!\w)administration officer(?!\w)$regex$),
            ('administration & finance officer', $regex$(?<!\w)administration\s*&\s*finance officer(?!\w)$regex$),
            ('financial planning and analysis', $regex$(?<!\w)financial planning and analysis(?!\w)$regex$),
            ('gymnastics coach', $regex$(?<!\w)gymnastics coach(?!\w)$regex$),
            ('practice manager', $regex$(?<!\w)practice manager(?!\w)$regex$),
            ('director', $regex$(?<!\w)director(?!\w)$regex$),
            ('head of', $regex$(?<!\w)head of(?!\w)$regex$),
            ('ceo', $regex$(?<!\w)ceo(?!\w)$regex$),
            ('cfo', $regex$(?<!\w)cfo(?!\w)$regex$),
            ('cto', $regex$(?<!\w)cto(?!\w)$regex$),
            ('cio', $regex$(?<!\w)cio(?!\w)$regex$),
            ('coo', $regex$(?<!\w)coo(?!\w)$regex$),
            ('chief executive', $regex$(?<!\w)chief executive(?!\w)$regex$),
            ('chief financial', $regex$(?<!\w)chief financial(?!\w)$regex$),
            ('chief technology', $regex$(?<!\w)chief technology(?!\w)$regex$),
            ('chief information', $regex$(?<!\w)chief information(?!\w)$regex$),
            ('chief operating', $regex$(?<!\w)chief operating(?!\w)$regex$),
            ('销售', $regex$销售$regex$),
            ('总监', $regex$总监$regex$),
            ('首席执行官', $regex$首席执行官$regex$),
            ('首席财务官', $regex$首席财务官$regex$),
            ('行政助理', $regex$行政助理$regex$);
    END IF;
END;
$migration$;
