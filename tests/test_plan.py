"""Tests for planning-only review behavior."""
import io
import pathlib
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from unittest.mock import patch

from roy import cmd_organize, cmd_undo, print_plan_summary
from roy_classify import Category, Classifier, FileInfo
from roy_plan import (PlanOperation, ReviewPlan, filter_needs_review,
                      parse_category_choices)
from roy_scan import ScanStats


def item(path, category, destination=None, size=10, work=False):
    return FileInfo(
        path=path, filename=path.name, extension=path.suffix,
        category=category, confidence=.9, reason='test', size=size,
        modified=datetime(2026, 1, 2), proposed_destination=destination,
        work_review=work, needs_review=category == Category.NEEDS_REVIEW,
    )


class TestReviewPlan(unittest.TestCase):
    @patch('roy.create_transaction_log')
    def test_planning_only_blocks_organize_and_undo(self, transaction_log):
        args = type('Args', (), {'dry_run': False, 'last': None, 'batch': None})()
        config = {'safety': {'planning_only': True}}
        cmd_organize(args, config)
        cmd_undo(args, config)
        transaction_log.assert_not_called()

    def test_category_selection_defaults_to_none_and_supports_multiple(self):
        self.assertEqual(parse_category_choices(''), set())
        self.assertEqual(parse_category_choices('1,5,6'), {
            Category.SCREENSHOTS, Category.ARCHIVES, Category.INSTALLERS})
        self.assertNotIn(Category.CODE, parse_category_choices('A'))

    def test_source_and_category_filters_coexist(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = pathlib.Path(tmp)
            desktop = item(home / 'Desktop/a.png', Category.SCREENSHOTS,
                           home / 'Pictures/Screenshots/2026/2026-01/a.png')
            downloads = item(home / 'Downloads/b.png', Category.SCREENSHOTS,
                             home / 'Pictures/Screenshots/2026/2026-01/b.png')
            stats = ScanStats(by_category={'Screenshots': 2})
            with patch('roy_plan.pathlib.Path.home', return_value=home):
                plan = ReviewPlan.from_inventory(
                    [desktop, downloads], stats, [Category.SCREENSHOTS], ['Desktop'])
            self.assertEqual([op.source for op in plan.operations], [str(desktop.path)])

    def test_code_and_work_items_never_enter_plan(self):
        root = pathlib.Path('/tmp')
        files = [
            item(root / 'code.py', Category.CODE, root / 'Code/code.py'),
            item(root / 'work.pdf', Category.DOCUMENTS, root / 'Documents/work.pdf', work=True),
        ]
        stats = ScanStats(by_category={'Code': 1}, work_review=1)
        plan = ReviewPlan.from_inventory(files, stats, [Category.CODE, Category.DOCUMENTS])
        self.assertEqual(plan.operations, [])
        self.assertEqual(plan.protected_code, 1)
        self.assertEqual(plan.protected_work, 1)

    def test_batch_approval_and_skip(self):
        operations = [PlanOperation('/a', '/x/a', 'Images', .9, 'test'),
                      PlanOperation('/b', '/x/b', 'Images', .9, 'test')]
        plan = ReviewPlan(operations)
        plan.decide(operations, 'approved')
        self.assertEqual(plan.summary()['approved'], 2)
        plan.decide([operations[1]], 'skipped')
        self.assertEqual(plan.summary()['skipped'], 1)

    def test_useful_batch_groupings(self):
        operations = [
            PlanOperation('/Desktop/a.jpg', '/Pictures/Organized/a.jpg', 'Images', .9, 'test', source_folder='Desktop'),
            PlanOperation('/Downloads/b.png', '/Pictures/Organized/b.png', 'Images', .8, 'test', source_folder='Downloads'),
        ]
        plan = ReviewPlan(operations)
        self.assertEqual(set(plan.grouped(by='source')), {'Desktop', 'Downloads'})
        self.assertEqual(set(plan.grouped(by='extension')), {'.jpg', '.png'})
        self.assertEqual(len(plan.grouped(by='destination')), 1)
        self.assertEqual(set(plan.grouped(by='confidence')), {'90-99%', '80-89%'})

    def test_changed_destination_preserves_filename(self):
        operation = PlanOperation('/source/photo.jpg', '/old/photo.jpg', 'Images', .9, 'test')
        plan = ReviewPlan([operation])
        plan.change_destination(operation, pathlib.Path('/custom/photos'))
        self.assertEqual(operation.destination, '/custom/photos/photo.jpg')

    def test_plan_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / 'current_plan.json'
            plan = ReviewPlan([PlanOperation('/a', '/b/a', 'Images', .9, 'test', 'approved')],
                              ['Images'], ['Desktop'], 4, 3, 2)
            plan.save(path)
            loaded = ReviewPlan.load(path)
            self.assertEqual(loaded.operations[0].decision, 'approved')
            self.assertEqual(loaded.selected_sources, ['Desktop'])
            self.assertEqual(loaded.duplicate_pairs, 2)

    def test_final_summary(self):
        plan = ReviewPlan([PlanOperation('/a', '/b/a', 'Images', .9, 'test', 'approved', 2048)],
                          protected_code=10, protected_work=5, duplicate_pairs=2)
        output = io.StringIO()
        with redirect_stdout(output):
            print_plan_summary(plan)
        value = output.getvalue()
        self.assertIn('Approved moves:', value)
        self.assertIn('Code                     10', value)
        self.assertIn('execution is disabled', value)

    def test_needs_review_filters_and_never_plans_moves(self):
        files = [
            item(pathlib.Path('/tmp/Desktop/report.xyz'), Category.NEEDS_REVIEW, size=100),
            item(pathlib.Path('/tmp/Downloads/photo.unknown'), Category.NEEDS_REVIEW, size=500),
        ]
        results = filter_needs_review(files, extension='.xyz', search='report', max_size=200)
        self.assertEqual(results, [files[0]])
        self.assertIsNone(results[0].proposed_destination)


class TestCentralDestinations(unittest.TestCase):
    def test_defaults_are_centralized_and_code_has_no_destination(self):
        classifier = Classifier({})
        with patch('roy_classify.pathlib.Path.home', return_value=pathlib.Path('/Users/test')):
            screenshot = item(pathlib.Path('/Users/test/Desktop/Screenshot 2026-08-04 at 03.24.50.png'),
                              Category.SCREENSHOTS)
            screenshot.created = datetime(2020, 1, 1)
            self.assertEqual(
                classifier.propose_destination(screenshot, {}),
                pathlib.Path('/Users/test/Pictures/Screenshots/2026/2026-08') / screenshot.filename)
            archive = item(pathlib.Path('/Users/test/Desktop/files.zip'), Category.ARCHIVES)
            self.assertEqual(classifier.propose_destination(archive, {}),
                             pathlib.Path('/Users/test/Downloads/Archives/General/files.zip'))
            code = item(pathlib.Path('/Users/test/Downloads/app.py'), Category.CODE)
            self.assertIsNone(classifier.propose_destination(code, {}))


if __name__ == '__main__':
    unittest.main()
