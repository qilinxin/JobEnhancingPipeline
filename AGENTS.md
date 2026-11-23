# Project language

Use English for project documentation, source comments, command-line output, error messages, and interface text. Preserve original job posting content and other external data.

## Application documents

For a job-specific resume, select and lightly tailor verified bullets from `local/resume/resume_master.md` using `documents/guidance.py`. When the applicant confirms a new responsibility or corrects an existing one, update the corresponding role in the master for future applications.

When preparing a cover letter, read the full job description, the confirmed resume and applicant profile in `local/resume/`, `documents/guidance.py`, and `documents/templates/cover_letter.md`. Follow the evidence and rendering checks in the guidance before delivering the DOCX. Save the generated documents under `local/generated_documents/<capture-id>/`.

## Git commits

After completing and verifying file changes for a task, commit those changes before reporting completion. Do this proactively for every task that modifies files. Stage only changes made for the current task.
