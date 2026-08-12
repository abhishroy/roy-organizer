import pathlib
import unittest
from datetime import datetime

from roy_analytics import explain, organization_score, recommendations, storage_overview
from roy_classify import Category, FileInfo
from roy_scan import ScanStats
from roy_tui import dashboard_text, menu_action


def file(name, category, size=100, destination=True):
    path = pathlib.Path('/Users/test/Desktop') / name
    return FileInfo(path=path, filename=name, extension=path.suffix, category=category,
                    size=size, reason='rule', confidence=.9, modified=datetime.now(),
                    proposed_destination=pathlib.Path('/Users/test/Documents')/name if destination else None,
                    needs_review=category == Category.NEEDS_REVIEW)


class TestExplainability(unittest.TestCase):
    def test_screenshot_explanation(self):
        signals = explain(file('Screenshot 2026-01-01 at 10.00.00.png', Category.SCREENSHOTS))
        self.assertIn('Matches macOS screenshot naming pattern', signals)
        self.assertTrue(any('configured destination' in value for value in signals))

    def test_repository_explanation(self):
        item = file('repo.zip', Category.REPOSITORY_ARCHIVE)
        item.archive_origin = 'personal'
        self.assertIn('Origin: personal', explain(item))

    def test_protected_explanation_never_contains_content(self):
        item = file('green.yaml', Category.NEEDS_REVIEW, destination=False)
        item.protection_type = 'KUBERNETES_CONFIG'
        result = ' '.join(explain(item))
        self.assertIn('No file contents', result)
        self.assertNotIn('token:', result)


class TestAnalytics(unittest.TestCase):
    def setUp(self):
        self.files = [file('a.png', Category.SCREENSHOTS, 10),
                      file('b.mp4', Category.VIDEOS, 20),
                      file('c.xyz', Category.NEEDS_REVIEW, 30, False)]
        self.stats = ScanStats(total_files=3, total_size=60, duplicates=[(self.files[0], self.files[1])])

    def test_score_is_deterministic_and_bounded(self):
        first = organization_score(self.files, self.stats)
        self.assertEqual(first, organization_score(self.files, self.stats))
        self.assertGreaterEqual(first['overall'], 0)
        self.assertLessEqual(first['overall'], 100)

    def test_storage_totals(self):
        result = storage_overview(self.files, self.stats)
        self.assertEqual(result['total'], 60)
        self.assertEqual(result['by_category']['Videos'], 20)
        self.assertEqual(result['exact_duplicate_bytes'], 20)

    def test_recommendations(self):
        values = recommendations(self.files, self.stats)
        self.assertTrue(any('screenshots' in value for value in values))
        self.assertTrue(any('duplicate' in value for value in values))


class TestTUI(unittest.TestCase):
    def test_menu_navigation(self):
        self.assertEqual(menu_action('1'), 'review')
        self.assertEqual(menu_action(' p '), 'protected')
        self.assertEqual(menu_action('q'), 'quit')
        self.assertEqual(menu_action('x'), 'unknown')

    def test_dashboard_has_safety_state(self):
        stats = ScanStats(total_files=1, needs_review=0, protected_by_reason={'hidden_file': 2})
        stats.open_file_state = 'KNOWN'
        text = dashboard_text({'machine_profile': 'developer_company_managed'},
                              [file('a.png', Category.IMAGES)], stats)
        self.assertIn('Developer Company Managed', text)
        self.assertIn('Open-file state: KNOWN', text)
        self.assertIn('Protected: 2', text)


if __name__ == '__main__':
    unittest.main()
