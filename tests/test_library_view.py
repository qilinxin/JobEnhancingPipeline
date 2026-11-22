"""Verify the live layout escapes posting data and preserves real status forms."""
import unittest
from datetime import date,datetime,timezone
from decimal import Decimal
from unittest.mock import patch
from web.library_view import render_library


class LibraryViewTests(unittest.TestCase):
    def row(self):
        return dict(id=42,title='Engineer <script>alert(1)</script>',company='A & B',location='Sydney (Hybrid)',city='Sydney',canonical_url='https://www.seek.com.au/job/123',display_score=Decimal('82.22'),delivery_reviewed_at=datetime.now(timezone.utc),reviewed_delivery_model='Client delivery',key_technologies=['Java','<img src=x>'],captured_at=datetime.now(timezone.utc),applied_at=None,excluded_at=None)

    @patch('web.library_view.document_file', return_value=None)
    def test_posting_content_is_escaped_and_forms_keep_search(self,_):
        result=render_library([self.row()],[{'day':date(2026,11,23),'total':1}],date(2026,11,23),keyword='Java "API"')
        self.assertIn('Engineer &lt;script&gt;',result)
        self.assertNotIn('<img src=x>',result)
        self.assertIn('82.22',result)
        self.assertIn('Outsourced',result)
        self.assertIn('action="/applied" method="post"',result)
        self.assertIn('name="capture_id" value="42"',result)
        self.assertIn('name="q" value="Java &quot;API&quot;"',result)
        self.assertIn('Documents not generated',result)
        self.assertIn('src="/library.js"',result)
        self.assertNotIn('<style>',result)
        self.assertNotIn('style="width:',result)

    @patch('web.library_view.document_file', return_value=None)
    def test_empty_view_and_actual_status(self,_):
        result=render_library([],[],date(2026,11,23))
        self.assertIn('No jobs match this view',result)
        row=self.row();row.update(applied_at=datetime.now(timezone.utc),excluded_at=datetime.now(timezone.utc),display_score=None)
        result=render_library([row],[],date(2026,11,23),show_excluded=True)
        self.assertIn('Undo applied',result)
        self.assertIn('Restore',result)
        self.assertIn('PENDING',result)
        self.assertIn('Excluded jobs',result)


if __name__=='__main__':
    unittest.main()
