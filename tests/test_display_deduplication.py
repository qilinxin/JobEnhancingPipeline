"""Verify conservative cross-platform normalization and duplicate marking."""
import unittest
from storage.postgres import connect


class DisplayDeduplicationTests(unittest.TestCase):
    def test_equivalent_and_distinct_postings(self):
        body = ' '.join(f'technology{i}' for i in range(100)) + ' Java 17 Spring Boot'
        with connect() as conn:
            def identity(title='Senior Java Developer', company='Hydrogen Group', city='Sydney NSW', text=body):
                return conn.execute('SELECT public.job_display_identity(%s,%s,%s,%s)', (title,company,city,text)).fetchone()[0]
            key=identity()
            self.assertIsNotNone(key)
            self.assertEqual(key,identity(company='Hydrogen Group Pty Ltd',city='Sydney NSW (Hybrid)'))
            self.assertEqual(key,identity(company='Senior Java Developer\n\nHydrogen Group • Sydney, New South Wales, Australia',city='',text=body+'\nDesired Skills and Experience\n'+body))
            self.assertNotEqual(key,identity(title='Lead Java Developer'))
            self.assertNotEqual(key,identity(city='Melbourne VIC'))
            self.assertNotEqual(key,identity(text=body.replace('Java 17','Java 21')))
            self.assertIsNone(identity(text='Java and Spring Boot'))
            self.assertEqual(
                identity(text=body + ' Contact careers@example.com.au'),
                identity(text=body + ' Contact ••••@example.com.au'),
            )
            self.assertNotEqual(
                identity(text=body + ' Contact careers@example.com.au'),
                identity(text=body + ' Contact careers@another.com.au'),
            )

    def test_confirmed_hydrogen_pair(self):
        with connect() as conn:
            rows=conn.execute('SELECT id,capture_kind,display_duplicate_of FROM linkedin_job_captures WHERE id IN (1635,1642) ORDER BY id').fetchall()
            self.assertEqual(len(rows),2)
            self.assertNotEqual(rows[0][1],'duplicate')
            self.assertEqual(rows[1][1: ],('duplicate',1635))


if __name__=='__main__':
    unittest.main()
