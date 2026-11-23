"""Check auditable score arithmetic and source-evidence validation."""
import unittest
from scoring.requirements import calculate_requirements
from web.app import format_requirement_ledger


class RequirementTests(unittest.TestCase):
    def item(self, name="Java", required=4, evidence=3, category="technical"):
        return dict(name=name, category=category, jd_quote=name,
                    required_level=required, evidence_level=evidence,
                    resume_quote=name if evidence else "", explanation="Verified role evidence.")

    def test_depth_weights_and_normalization(self):
        items = [self.item(), self.item("SQL", 2, 2)]
        score, ledger, _ = calculate_requirements(items, "Java SQL", "Java SQL")
        self.assertAlmostEqual(score, 83.33)
        self.assertAlmostEqual(sum(i["available"] for i in ledger["requirements"]), 100)
        self.assertEqual(ledger["requirements"][0]["status"], "partial")
        self.assertEqual(ledger["requirements"][1]["status"], "met")

    def test_missing_evidence_is_zero_and_alternatives_count_once(self):
        score, ledger, _ = calculate_requirements(
            [self.item("Java or Python", 3, 3), self.item("Kafka", 3, 0)],
            "Java or Python and Kafka", "Java or Python")
        self.assertEqual(score, 50)
        self.assertEqual(ledger["requirements"][1]["status"], "unverified")

    def test_fabricated_quotes_and_duplicates_are_rejected(self):
        for items in ([self.item("Kafka")], [self.item(), self.item()]):
            with self.assertRaises(ValueError):
                calculate_requirements(items, "Java Kafka", "Java")

    def test_rendering_escapes_jd_and_resume(self):
        _, ledger, _ = calculate_requirements([self.item("<script>", 3, 3)], "<script>", "<script>")
        output = format_requirement_ledger(ledger)
        self.assertIn("&lt;script&gt;", output)
        self.assertNotIn("<script>", output)
        self.assertIn("100.00 / 100.00", output)
        self.assertIn('class="requirement-table"', output)
        self.assertNotIn("<blockquote>", output)
        self.assertIn("Hands-on proficiency", output)
