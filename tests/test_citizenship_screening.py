"""Check requirement detection and database enforcement after the migration."""
import unittest
from storage.postgres import connect


class CitizenshipScreeningTests(unittest.TestCase):
    def test_requirement_clauses(self):
        cases = {
            'Only candidates based in Australia who hold Australian citizenship or permanent residency can apply.': True,
            'Applicants must be Australian citizens or permanent residents.': True,
            'Australian Citizenship Mandatory | Baseline Security Clearance Required': True,
            'Java Developer (Aus citizen / PR)': False,  # The full JD establishes mandatory eligibility.
            'Australian Citizenship.': True,
            'Applicants must be based in Sydney and hold full Australian working rights (Australian or NZ citizen, or permanent resident).': True,
            'Must be an Australian Citizen and hold NV1 clearance (NV2 preferred).': True,
            'Australian citizenship or PR is preferred.': False,
            'Australian citizenship is not required.': False,
            'We do not require Australian citizenship.': False,
            'Applicants must be an Australian Citizen/Permanent Resident or have an appropriate Australian work visa or work entitlements.': False,
            'Australian citizens, PR or unrestricted Australian work rights accepted.': False,
            'Equal opportunity regardless of citizenship, gender or race.': False,
            'Experience designing citizen, customer and self-service platforms.': False,
            'PR reviews and CI/CD are essential.': False,
        }
        with connect() as conn:
            for text, expected in cases.items():
                with self.subTest(text=text):
                    self.assertEqual(conn.execute('SELECT public.requires_citizenship_pr(%s)', (text,)).fetchone()[0], expected)

    def test_rescoring_cannot_override_restriction(self):
        with connect() as conn:
            row = conn.execute('SELECT id FROM linkedin_job_captures WHERE citizenship_pr_required LIMIT 1').fetchone()
            self.assertIsNotNone(row)
            with conn.transaction(force_rollback=True):
                score, details = conn.execute(
                    "UPDATE linkedin_job_captures SET match_score=86,match_details='Test rescore' WHERE id=%s RETURNING match_score,match_details",
                    row,
                ).fetchone()
                self.assertEqual(score, 0)
                self.assertIn('subclass 485', details)

    def test_corrected_requirement_requests_rescoring(self):
        with connect() as conn:
            row = conn.execute(
                'SELECT id FROM linkedin_job_captures WHERE citizenship_pr_required AND NOT clearance_required AND NOT company_blacklisted LIMIT 1'
            ).fetchone()
            self.assertIsNotNone(row)
            with conn.transaction(force_rollback=True):
                required, score, details = conn.execute(
                    "UPDATE linkedin_job_captures SET description='Java development. Valid work visas accepted.' WHERE id=%s RETURNING citizenship_pr_required,match_score,match_details",
                    row,
                ).fetchone()
                self.assertFalse(required)
                self.assertIsNone(score)
                self.assertIsNone(details)


if __name__ == '__main__':
    unittest.main()
