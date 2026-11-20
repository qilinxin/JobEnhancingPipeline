"""Regression checks for cross-platform posting identities."""

import unittest

from storage.posting import posting_features


class PostingIdentityTests(unittest.TestCase):
    def setUp(self):
        self.capture = {
            'title': 'Java Developer',
            'company': 'Clicks IT Recruitment (QLD)',
            'location': 'Brisbane QLD',
            'description': (
                'Full-time onsite work required. Java 21 and Spring Boot. '
                'Contact ••••@clicks.com.au or 04•• ••• 158. '
                'Adjustments: 13•• ••• 257.'
            ),
        }

    def fingerprint(self, **changes):
        return posting_features(dict(self.capture, **changes))[0]

    def test_masked_contacts_and_linkedin_header_match(self):
        other = self.fingerprint(
            company='Java Developer\n\nClicks IT Recruitment • Brisbane City, Queensland, Australia (On-site)',
            location='',
            description=(
                'Full-time onsite work required. Java 21 and Spring Boot. '
                'Contact recruiter@clicks.com.au or 0419 721 158. '
                'Adjustments: 1300 254 257.'
            ),
        )
        self.assertEqual(self.fingerprint(), other)

    def test_board_formatting_matches(self):
        self.assertEqual(self.fingerprint(), self.fingerprint(
            description='Job Description\n' + self.capture['description'].upper() + '\n#hybrid'))

    def test_different_cities_stay_separate(self):
        self.assertNotEqual(self.fingerprint(), self.fingerprint(location='Sydney NSW'))

    def test_different_employers_stay_separate(self):
        self.assertNotEqual(self.fingerprint(), self.fingerprint(company='Other Recruitment'))

    def test_material_requirements_stay_separate(self):
        self.assertNotEqual(self.fingerprint(), self.fingerprint(
            description=self.capture['description'].replace('Java 21', 'Java 11')))

    def test_work_arrangements_stay_separate(self):
        self.assertNotEqual(self.fingerprint(), self.fingerprint(location='Brisbane QLD (Remote)'))

    def test_missing_location_has_no_cross_platform_identity(self):
        self.assertIsNone(self.fingerprint(location=''))


if __name__ == '__main__':
    unittest.main()
