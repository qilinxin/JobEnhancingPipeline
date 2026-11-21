# Resume matching references

This project compares a job description with a confirmed resume and explains the evidence and gaps behind the match. [The scoring prompt](resume_matching.md) defines the project's own 100-point rubric. The commercial products below provide public examples of related approaches.

- Oracle Recruiting documents separate ratings for profile, education, experience, and skills. This provides a commercial example of breaking a match down into multiple dimensions. [Oracle, Understand Top Candidate Suggestions](https://docs.oracle.com/en/cloud/saas/talent-management/faush/understand-suggested-candidates.html)
- Workable evaluates candidates against a role-specific ideal candidate profile and shows how the candidate matches individual criteria. This is comparable to evaluating resume evidence against each job's requirements. [Workable, Using the Workable Agent](https://help.workable.com/hc/en-us/articles/38381544828695-Using-the-Workable-Agent)
- Greenhouse supports automatic rejection based on configured application-question answers. This is an example of a discrete eligibility rule. The project's own screening checks use explicit posting requirements and confirmed applicant facts. [Greenhouse, Auto-reject](https://support.greenhouse.io/hc/en-us/articles/360000653472-Auto-reject)

The 45/25/20/10 category weights, technical-depth scale, and Java alignment adjustment are project-specific. The resulting Job Match Score estimates fit against the job description and resume, and has no calibration against employer scores or hiring outcomes.
