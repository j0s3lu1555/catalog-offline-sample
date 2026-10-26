import hashlib
import json
import re
from pathlib import Path
import tempfile
import unittest

from catalog_extract import ReviewRequired, batch, extract


URL = 'https://example.edu/courses/000123'


def page(heading='CS0123 - Example &amp; Testing (3 cr)', lower='3', upper='3', extra=''):
    code = re.split(r'\s+-\s+', heading)[0]
    return f'''<!doctype html><html><head><script id="__NUXT_DATA__" type="application/json">[]</script></head>
    <body><nav><h1>Not a course</h1></nav><main><h1>{code}</h1><h2>{heading}</h2>
    <div><h3>Minimum Credits</h3><div class="field-value">{lower}</div></div>
    <div><h3>Maximum Credits</h3><div class="field-value">{upper}</div></div>{extra}</main></body></html>'''.encode()


class ExtractTests(unittest.TestCase):
    def test_facts_and_provenance(self):
        raw = page()
        result = extract(raw, URL)
        self.assertEqual(result['code'], 'CS0123')
        self.assertEqual(result['title'], 'Example & Testing')
        self.assertEqual(result['source_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertIsNone(result['catalog_year'])

    def test_variable_credits(self):
        result = extract(page('CS0499 - Independent Study (1–6 cr)', '1', '6'), URL)
        self.assertEqual((result['credits_min'], result['credits_max']), ('1', '6'))

    def test_fractional_credits(self):
        self.assertEqual(extract(page('CS0123 - Lab (0.5 cr)', '0.5', '0.5'), URL)['credits_min'], '0.5')

    def test_zero_credits(self):
        self.assertEqual(extract(page('CS0123 - Colloquium (0 cr)', '0', '0'), URL)['credits_min'], '0')

    def test_script_heading_not_used(self):
        raw = page(extra='<script><h2>CS9999 - Wrong (3 cr)</h2></script>')
        self.assertEqual(extract(raw, URL)['code'], 'CS0123')

    def test_distinct_second_course_requires_review(self):
        with self.assertRaises(ReviewRequired):
            extract(page(extra='<h2>CS0999 - Different course (3 cr)</h2>'), URL)

    def test_repeated_identical_heading_is_ok(self):
        self.assertEqual(extract(page(extra='<h2>CS0123 - Example &amp; Testing (3 cr)</h2>'), URL)['code'], 'CS0123')

    def test_missing_credit_field_requires_review(self):
        with self.assertRaises(ReviewRequired):
            extract(page().replace(b'<h3>Minimum Credits</h3>', b'<h3>Unrecognized heading</h3>'), URL)

    def test_wrong_primary_identifier_requires_review(self):
        with self.assertRaises(ReviewRequired):
            extract(page().replace(b'<h1>CS0123</h1>', b'<h1>CS0999</h1>'), URL)

    def test_conflicting_credit_fields_require_review(self):
        with self.assertRaises(ReviewRequired):
            extract(page(extra='<div><h3>Minimum Credits</h3><div class="field-value">4</div></div>'), URL)

    def test_reversed_credit_range_requires_review(self):
        with self.assertRaises(ReviewRequired):
            extract(page(lower='4', upper='3'), URL)

    def test_heading_credit_disagreement_requires_review(self):
        with self.assertRaises(ReviewRequired):
            extract(page('CS0123 - Example (5 cr)', '3', '3'), URL)

    def test_heading_max_disagreement_requires_review(self):
        with self.assertRaises(ReviewRequired):
            extract(page('CS0123 - Example (1–5 cr)', '1', '6'), URL)

    def test_invalid_credit_tokens_require_review(self):
        for token in ['NaN', 'Infinity', '-1', '1,5', '100', '=3+0', '']:
            with self.subTest(token=token), self.assertRaises(ReviewRequired):
                extract(page(lower=token), URL)

    def test_unsupported_template_requires_review(self):
        with self.assertRaises(ReviewRequired):
            extract(page().replace(b'__NUXT_DATA__', b'other'), URL)

    def test_invalid_utf8_requires_review(self):
        with self.assertRaises(ReviewRequired):
            extract(b'\xff\xfe', URL)

    def test_bad_source_urls_require_review(self):
        for url in ['file:///tmp/a', 'http://example.edu/a', 'https://user:password@example.edu/a', 'garbage']:
            with self.subTest(url=url), self.assertRaises(ReviewRequired):
                extract(page(), url)

    def test_failed_records_do_not_disappear(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / 'good.html').write_bytes(page())
            (base / 'bad.html').write_bytes(b'<h2>Unknown</h2>')
            result = batch([{'file': 'good.html', 'url': URL}, {'file': 'bad.html', 'url': URL + '/bad'}], base)
            self.assertEqual((result['source_count'], result['clean_count'], result['review_count']), (2, 1, 1))
            self.assertEqual(result['network_calls'], 0)

    def test_duplicate_code_is_not_silently_merged(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / 'a.html').write_bytes(page())
            (base / 'b.html').write_bytes(page('CS0123 - Revised title (3 cr)'))
            result = batch([{'file': 'a.html', 'url': URL}, {'file': 'b.html', 'url': URL + '/archive'}], base)
            self.assertEqual((result['clean_count'], result['review_count']), (0, 2))

    def test_cross_institution_code_is_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / 'a.html').write_bytes(page())
            result = batch([{'file': 'a.html', 'url': URL}, {'file': 'a.html', 'url': 'https://other.edu/course'}], base)
            self.assertEqual(result['clean_count'], 2)

    def test_manifest_cannot_read_outside_its_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                batch([{'file': '../secret.html', 'url': URL}], Path(temp))


if __name__ == '__main__':
    unittest.main()
