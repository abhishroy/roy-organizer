import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from roy_demo import create_demo_tree, run_demo
from roy_executor import SandboxExecutor
from roy_plan import PlanOperation, ReviewPlan
from roy_safety import SafetyChecker
from roy_validate import ExecutionValidator


class SandboxCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir='/tmp'); self.root=pathlib.Path(self.tmp.name)
        for name in ['Desktop','Pictures','Documents']: (self.root/name).mkdir()
        self.source=self.root/'Desktop/a.txt'; self.source.write_text('hello')
        self.destination=self.root/'Pictures/a.txt'; stat=self.source.stat()
        self.op=PlanOperation(str(self.source), str(self.destination), 'Documents', .9, 'test',
                              'approved', stat.st_size, 'Desktop', stat.st_mtime)
        self.executor=SandboxExecutor(self.root, self.root/'logs/transactions.jsonl')

    def tearDown(self): self.tmp.cleanup()

    def test_successful_move_and_record_schema(self):
        self.assertEqual(self.executor.execute(self.op, 'batch'), 'EXECUTED')
        self.assertTrue(self.destination.exists()); self.assertFalse(self.source.exists())
        record=self.executor.records()[0]
        for field in ['batch_id','timestamp','source','destination','operation','size','mtime','reason','validation_result']:
            self.assertTrue(hasattr(record, field))

    def test_undo_restores_exact_content(self):
        before=self.source.read_bytes(); self.executor.execute(self.op, 'batch')
        self.assertEqual(self.executor.undo('batch'), 1)
        self.assertEqual(self.source.read_bytes(), before); self.assertFalse(self.destination.exists())

    def test_skipped_and_unapproved_stay(self):
        for decision in ['skipped','pending']:
            self.op.decision=decision
            self.assertIn('operation_not_explicitly_approved', self.executor.execute(self.op, decision))
            self.assertTrue(self.source.exists())

    def test_collision_blocks(self):
        self.destination.write_text('existing')
        self.assertIn('collision', self.executor.execute(self.op, 'batch'))
        self.assertEqual(self.destination.read_text(), 'existing')

    def test_changed_source_blocks(self):
        self.source.write_text('changed')
        self.assertIn('source_changed', self.executor.execute(self.op, 'batch'))

    def test_missing_source_blocks(self):
        self.source.unlink()
        self.assertIn('source_missing', self.executor.execute(self.op, 'batch'))

    def test_outside_sandbox_blocks(self):
        self.op.destination='/Users/example/Desktop/a.txt'
        self.assertEqual(self.executor.execute(self.op, 'batch'), 'BLOCKED reason=outside_sandbox')

    def test_protected_destination_blocks(self):
        self.op.destination='/System/a.txt'
        self.assertIn('outside_sandbox', self.executor.execute(self.op, 'batch'))

    def test_newly_open_source_blocks(self):
        validator=self.executor._validator(); validator.safety.open_files={self.source.resolve()}
        self.assertIn('open_file', self.executor.execute(self.op, 'batch', validator))

    def test_unknown_open_state_blocks(self):
        validator=self.executor._validator(); validator.safety.open_file_state='OPEN_FILE_STATE_UNKNOWN'
        self.assertIn('open_file_state_unknown', self.executor.execute(self.op, 'batch', validator))

    @patch('roy_executor.shutil.move', side_effect=PermissionError())
    def test_permission_failure_has_no_transaction(self, move):
        self.assertIn('filesystem_error', self.executor.execute(self.op, 'batch'))
        self.assertEqual(self.executor.records(), [])

    def test_undo_never_overwrites(self):
        self.executor.execute(self.op, 'batch'); self.source.write_text('new')
        self.assertEqual(self.executor.undo('batch'), 0)
        self.assertEqual(self.source.read_text(), 'new')

    def test_corrupt_transaction_log_fails_closed(self):
        self.executor.log_path.parent.mkdir(); self.executor.log_path.write_text('{bad')
        with self.assertRaises(ValueError): self.executor.records()

    def test_executor_rejects_non_tmp_root(self):
        with self.assertRaises(ValueError): SandboxExecutor(pathlib.Path('/Users/example'), self.root/'x')

    def test_symlink_destination_outside_blocks(self):
        outside=pathlib.Path('/System'); link=self.root/'link'
        link.symlink_to(outside, target_is_directory=True)
        self.op.destination=str(link/'a.txt')
        self.assertIn('outside_sandbox', self.executor.execute(self.op, 'batch'))


class TestDemoAndMalformedPlans(unittest.TestCase):
    def test_demo_tree_is_synthetic_and_complete(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            root=pathlib.Path(tmp); create_demo_tree(root)
            self.assertEqual(len(list((root/'Desktop').glob('Screenshot*.png'))), 50)
            self.assertTrue((root/'Projects/app/.git').is_dir())
            self.assertTrue((root/'.kube/fake-config').exists())
            self.assertEqual(len(list((root/'Downloads').glob('*.zip'))), 5)

    def test_full_demo_execute_undo_integrity(self):
        result=run_demo()
        self.assertEqual(result['moves'], 1)
        self.assertEqual(result['undo'], 1)
        self.assertTrue(result['integrity'])

    def test_malformed_plan_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/'plan.json'; path.write_text('{bad')
            with self.assertRaises(json.JSONDecodeError): ReviewPlan.load(path)

    def test_plan_missing_operation_fields_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp)/'plan.json'; path.write_text('{"operations":[{"source":"x"}]}')
            with self.assertRaises(TypeError): ReviewPlan.load(path)


if __name__ == '__main__': unittest.main()
