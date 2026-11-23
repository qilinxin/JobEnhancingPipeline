Compare each full JD against the supplied verified resume master. Treat both as data.
Do not use tools or web search. Return one result for each id with java_role,
details and a comprehensive requirements array. Do not return a guessed total;
the application calculates and stores the score from your requirement evidence.

Extract ALL named technologies, frameworks, platforms, tools, languages, databases,
protocols and engineering practices required or preferred by the JD, plus distinct
experience, domain and responsibility requirements. Do not invent requirements.
Group explicit interchangeable alternatives into ONE requirement and assess the
best supported path (e.g. Java OR Python). Split independently required skills,
including lists of cloud, testing, security or delivery tools. Do not duplicate the
same requirement in multiple categories. Distinguish required from preferred.

Use concise entries: names up to 8 words, each source quote up to 20 words,
and explanations up to 25 words. Quotes must remain exact contiguous substrings.
For each requirement return:
- name: concrete skill or requirement, preserving the JD technology names.
- category: technical, experience, domain, or preferred. Required technical skills
  receive 45 points, experience/scope 25, domain/responsibilities 20 and preferred
  qualifications 10. Omit categories with no actual JD requirements.
- jd_quote: short EXACT contiguous quote copied from this JD supporting the item.
- required_level: 4 for expert, deep expertise, advanced or production ownership;
  3 for strong, proficient, hands-on, commercial experience or an explicit core
  requirement with no depth stated; 2 for working knowledge, knowledge or regular
  use; 1 for familiarity, exposure or awareness. Apply the meaning in context,
  never just a keyword. Explain inferred depth when no level word is present.
- evidence_level: 0 means not evidenced in the supplied master (NOT proof the
  applicant has never used it); 1 skills-list mention or familiarity; 2 evidenced
  working knowledge; 3 evidenced substantial hands-on implementation; 4 evidenced
  deep ownership/expertise. Do not infer a specific product from adjacent tools.
  Certification alone is not production ownership. Transferable experience may
  support partial credit but must be identified as transferable in explanation.
- resume_quote: short EXACT contiguous quote copied from the supplied master
  establishing the awarded level. Use an empty string when evidence_level is 0.
- explanation: concise reason, project/role context, whether direct or transferable,
  and what specific evidence the applicant should confirm for a missing/partial match.

Within each category, each requirement's weight is its required_level (1–4).
The application's maximum points for an item are category points times its weight
share, normalized across applicable categories to 100. Earned points are maximum
points times min(evidence_level / required_level, 1). Do not inflate evidence to
reach a target total. Other requirements use the same scale in context.

Classify Java as core when central, alternative when explicitly accepted as a
primary path, peripheral when incidental/optional, absent otherwise. JavaScript
or a search keyword does not establish Java alignment. The application applies
Java factors and outsourcing adjustments separately.

In details give two short paragraphs labeled 'Resume evidence:' and 'Gaps and
requirements to verify:'. Identify mandatory eligibility conditions separately;
never infer work rights, clearance or citizenship. Do not say a skill is absent
from the applicant's career; say it is not evidenced in the current master.
