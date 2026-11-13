"""Rules for preparing a resume and cover letter for a specific posting."""

DIRECT_MIN_SCORE = 75
OUTSOURCED_MIN_SCORE = 85
COVER_LETTER_TEMPLATE = "templates/cover_letter.md"
APPLICANT_NAME = "William(Linxin) Qi"
WORK_RIGHTS = (
    "Unrestricted Australian work rights on a Temporary Graduate visa (subclass 485), "
    "valid until 11 April 2028. No sponsorship required."
)

ELIGIBILITY_GUIDE = f"""
Check mandatory eligibility before deciding whether to generate documents. Compare
citizenship, active security clearance, work rights and explicit on-site or
relocation requirements with the applicant's confirmed circumstances. Report
unmet or unverified requirements. Never claim eligibility without evidence.
Keep the existing zero-score rule for postings requiring security clearance.

Use the final contracting party to set the generation threshold:
- Direct hire, including agency referrals with a direct client contract:
  {DIRECT_MIN_SCORE} or above.
- Outsourcing, labour hire or placement with a client under a supplier contract:
  {OUTSOURCED_MIN_SCORE} or above.

If the contract is unclear, give both decisions and explain what to verify.
Generate automatically only when hard requirements are confirmed and every
plausible contract type meets its threshold. Use the stored score for threshold
comparisons. Below threshold, report the score, main gaps and whether to apply.
An explicit instruction to prepare documents can override the score threshold.
Continue to disclose any eligibility gaps and keep all document claims factual.
""".strip()

RESUME_GUIDE = """
Use the latest applicant-confirmed resume as the editing baseline. Preserve its
fonts, layout, section structure and official job titles. Edit only bullets
relevant to the posting. Change the Summary, Education, Achievements or other
sections only when explicitly requested.

Put the strongest evidence first within each role. Aim for one contribution
per bullet and one or two lines per bullet. Bold key technologies or outcomes
selectively. Aim for two pages. Compress repeated material and omit weakly
related bullets or open-source projects where appropriate. Respect previous
instructions to remove content.

Verify all technologies, responsibilities and outcomes against confirmed
experience. Distinguish commercial work, personal or university projects, and
certifications. Preserve the distinction between AngularJS and Angular. List
AWS SAA as a certification and describe production AWS experience accurately.

Choose verified evidence that fits the posting:
- Java backend: Spring Boot, complex SQL, Oracle-to-PostgreSQL migration,
  production incident resolution and CI/CD.
- Finance, payments and integration: corporate bank connectivity, collections
  and payments, financing, ABS, Activiti and batch processing.
- Full stack and security: Infosys React and Spring Boot WAF work, plus
  relevant identity and access control experience.
- Include Kubernetes, Prometheus, Grafana or AWS SAA where relevant.
""".strip()

COVER_LETTER_GUIDE = f"""
Use {COVER_LETTER_TEMPLATE} as the default content and structure template.
Replace its placeholders with confirmed information and omit optional fields
that do not apply. Use “Hiring Manager” when the recipient is unknown.
Add or remove evidence bullets according to the posting.
Verify the company, role, location and date. Follow the employer's requested
format or selection criteria when provided.

Keep the letter to one page. Default to a brief opening, evidence of fit and a
brief closing. State the role and strongest relevant background in the opening.
Introduce the evidence with “My experience aligns…” and use up to six bullets.
Use fewer when the strongest evidence fits in fewer points. Tie each bullet
to a JD requirement with a specific project or responsibility. Bold key
technologies selectively. Use relevant evidence to set the length.

A short three-paragraph letter is also suitable when the applicant's motivation
or location preference is central, such as for Qantas Adelaide. Close with the
reason for applying. Include location, work rights and availability when relevant.
Use Sydney, NSW by default. For Adelaide-only roles, describe confirmed
relocation willingness. For Qantas Adelaide, mention the applicant's Adelaide
preference and interest in the new PIC project where relevant.

Use the name {APPLICANT_NAME} in both documents. When needed, use:
- {WORK_RIGHTS}
- Available immediately
""".strip()

DELIVERY_GUIDE = """
Deliver editable DOCX files named William_<Company>_resume.docx and
William_<Company>_Coverletter.docx. If names collide for the same company,
add up to two role words after the company name.

Before delivery, check that the resume is as close to two pages as practical
and the cover letter fits one page. Verify the company and role names, confirm
the accuracy of key claims, and check that previously removed content remains
omitted.
""".strip()
