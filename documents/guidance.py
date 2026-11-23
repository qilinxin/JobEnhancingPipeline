"""Rules for preparing a resume and cover letter for a specific posting."""

DIRECT_MIN_SCORE = 75
OUTSOURCED_MIN_SCORE = 85
COVER_LETTER_TEMPLATE = "documents/templates/cover_letter.md"
RESUME_MASTER = "local/resume/resume_master.md"
APPLICANT_PROFILE = "local/resume/applicant_profile.md"
APPLICANT_NAME = "William(Linxin) Qi"
WORK_RIGHTS = (
    "Unrestricted Australian work rights on a Temporary Graduate visa (subclass 485), "
    "valid until 11 April 2028. No sponsorship required."
)

ELIGIBILITY_GUIDE = f"""
Read {APPLICANT_PROFILE} for confirmed applicant facts and role preferences.
Apply those preferences before generating documents.
Check mandatory eligibility before deciding whether to generate documents. Compare
citizenship, active security clearance, work rights and explicit on-site or
relocation requirements with the applicant's confirmed circumstances. Report
unmet or unverified requirements. Never claim eligibility without evidence.
Keep the existing zero-score rule for postings requiring security clearance.

Use the final contracting party to set the generation threshold:
- Direct hire, including agency referrals with a direct client contract and
  direct hires who deploy or support their employer's own product:
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

RESUME_GUIDE = f"""
Use {RESUME_MASTER} as the source of verified experience and the latest
applicant-confirmed Word resume as the layout template. Preserve the fonts,
layout, section structure and official job titles. Change the Summary,
Education, Achievements or other sections only when explicitly requested.

Read the full job description and identify its core responsibilities,
mandatory requirements and preferred skills. Select the strongest relevant
bullets from the master, keeping each under its original role. Lightly adapt
the phrasing to the employer's terminology when the meaning is equivalent.
Preserve the technology, scope, ownership and results of each contribution.
If direct experience is missing, use clearly applicable transferable evidence
or report the gap to the applicant.

Keep job-specific wording in the application copy. When the applicant confirms
a new responsibility, technology or outcome, add it to the master under the
correct role. Correct an existing bullet when the applicant clarifies it and
merge overlapping bullets when they describe the same contribution. Keep
skills with unconfirmed project attribution in the skills section.

Put the strongest evidence first within each role. Aim for one contribution
per bullet and one or two lines per bullet. Bold key technologies or outcomes
selectively. Aim to use most of two pages when the baseline has enough relevant
experience. Preserve useful evidence and compress repeated material first. Omit
weakly related bullets or open-source projects where appropriate. Respect previous
instructions to remove content.

Verify all technologies, responsibilities and outcomes against confirmed
experience. Distinguish commercial work, personal or university projects, and
certifications. Preserve the distinction between AngularJS and Angular. List
AWS SAA as a certification and describe production AWS experience accurately.
Group tools by technical area in Skills. List Java 17 under Backend and APIs
and place autoscaling, monitoring tools and AWS architecture under Delivery
and operations. Use the relevant experience bullets to identify project context.

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
Before drafting, read the full posting and identify its main responsibilities,
mandatory requirements and preferred skills. Map each main responsibility and
mandatory requirement to a verified example, a confirmed eligibility fact or
a gap. Use the confirmed resume and applicant profile as evidence. Prioritise
the work the applicant would do day to day. Report material gaps to the
applicant and distinguish transferable experience from direct experience.
Where the posting lists alternatives, use the verified alternative that meets
the requirement. Keep commercial, internship and personal project experience
distinct.

Use {COVER_LETTER_TEMPLATE} for structure. Open with the exact role and company
and the strongest relevant experience. For a well-matched role with a detailed
posting, aim for 400 to 450 body words and five distinct evidence points.
Use four to six points when supported by the posting and the applicant's
experience. Body length excludes contact details, date, greeting and sign-off.
Follow any employer-specified format, word limit or selection criteria.
Adjust the length to fit one page and the available verified evidence.

Give each evidence point a clear focus. Name the project or context, explain
what the applicant did and include a verified result or concrete deliverable.
Give major responsibilities separate space when combining them would obscure
the applicant's contribution. For engineering roles, cover requirements and
collaboration, implementation, testing, deployment, production support and
performance where the posting calls for them and evidence supports them.
Mention tools in the context of the work. Avoid repeating examples, copying
the posting, listing keywords or inventing outcomes to reach a word count.

Close with a role-specific reason for applying and any relevant confirmed work
arrangements. Use Sydney, NSW as the applicant's location by default. For an
on-site role, state full-time on-site availability in the posting city when
relevant and mention relocation for roles outside Sydney. For Qantas Adelaide,
mention the applicant's Adelaide preference and interest in the new PIC project
where relevant. Verify the company, role, location and date. Use “Hiring
Manager” when the recipient is unknown and remove all placeholder text.

Frame the letter around problems the employer needs solved: turning requirements
into deliverable work, shipping and iterating features, integrating systems and
maintaining reliable production services. Support these contributions with verified
examples rather than a list of technologies. Short application statements should
also lead with the practical value the applicant can provide.

Use the name {APPLICANT_NAME} in both documents. When needed, use:
- {WORK_RIGHTS}
- Available immediately
""".strip()

DELIVERY_GUIDE = """
Deliver editable DOCX files named William_<Company>_resume.docx and
William_<Company>_Coverletter.docx. If names collide for the same company,
add up to two role words after the company name.

Before delivery, check the rendered resume for page count and excessive blank
space on page two. Compare the final cover letter against the posting and the
evidence identified before drafting. Restore any missing material match with
verified evidence and tell the applicant about material gaps. Render the DOCX
and inspect the whole page. For a detailed, well-matched role, the letter
should fill one page from the contact block down to the signature, leaving
normal margins and only a modest amount of blank space below the signature.
If the page looks sparse, develop relevant evidence with verified details
about the applicant's contribution and results, then render it again. If
the letter spills onto a second page, tighten the prose and render again.
Use readable type and normal margins throughout.
Follow employer-specified length and format. Verify the company and role names,
the accuracy of key claims and that previously removed content remains omitted.
""".strip()
