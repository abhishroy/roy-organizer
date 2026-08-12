import pathlib
import tempfile
import unittest
import io
from contextlib import redirect_stdout
from unittest.mock import patch

from roy import cmd_execute, cmd_screenshot_undo
from roy_pilot import (PilotExecutor, PilotJournal, PilotRecord,
                       format_pilot_block, missing_plan_sources,
                       SCREENSHOT_PREFIX, load_blocked_screenshots,
                       save_blocked_screenshots, screenshot_summary, select_pilot_operations,
                       select_screenshot_operations)
from roy_plan import PlanOperation, ReviewPlan


class FakeChecker:
    state = 'KNOWN'
    open_paths = set()

    def __init__(self, config):
        from roy_safety import SafetyChecker
        self.inner = SafetyChecker(config)
        self.open_file_state = self.state
        self.open_files = {path.resolve() for path in self.open_paths}

    def prepare_open_files(self):
        self.open_file_state = self.state
        self.open_files = {path.resolve() for path in self.open_paths} if self.state == 'KNOWN' else None

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def check_source(self, path):
        self.inner.open_file_state = self.open_file_state
        self.inner.open_files = self.open_files
        return self.inner.check_source(path)


class PilotCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.temp.name)
        self.desktop = self.home / 'Desktop'; self.desktop.mkdir()
        (self.home / 'Downloads').mkdir(); (self.home / 'Documents').mkdir()
        (self.home / 'Pictures').mkdir(); (self.home / 'Movies').mkdir()
        (self.home / 'Pictures/Screenshots').mkdir()
        self.log = self.home / 'pilot.jsonl'
        self.config = {
            'machine_profile': 'developer_company_managed',
            'scan_paths': [str(self.home / name) for name in
                           ('Desktop', 'Downloads', 'Documents', 'Pictures', 'Movies')],
            'classification': {'work_terms': ['company', 'work']},
            'safety': {'planning_only': True, 'skip_hidden': True,
                       'skip_git_repos': True, 'skip_open_files': True,
                       'protected_paths': [str(self.home / '.kube')]},
        }
        FakeChecker.state = 'KNOWN'; FakeChecker.open_paths = set()
        self.executor = PilotExecutor(self.config, self.log, home=self.home,
                                      checker_factory=FakeChecker)

    def tearDown(self):
        self.temp.cleanup()

    def operation(self, name='Screenshot 2026-08-12.png', category='Screenshots',
                  decision='approved', source=None, destination=None):
        source = source or self.desktop / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b'image')
        stat = source.stat()
        destination = destination or self.home / 'Pictures/Screenshots/2026/2026-08' / name
        return PlanOperation(str(source), str(destination), category, 1.0, 'screenshot',
                             decision, stat.st_size, 'Desktop', stat.st_mtime)

    def test_maximum_twenty_and_screenshot_only_selection(self):
        operations = [self.operation(f'Screenshot {number}.png') for number in range(22)]
        operations += [self.operation('photo.png', 'Images'), self.operation('pending.png', decision='pending')]
        selected = select_pilot_operations(ReviewPlan(operations))
        self.assertEqual(len(selected), 20)
        self.assertTrue(all(op.category == 'Screenshots' and op.decision == 'approved' for op in selected))
        self.assertEqual(len(select_screenshot_operations(ReviewPlan(operations))), 22)

    def test_screenshot_summary_lists_all_roots_and_destination_tree(self):
        desktop = self.operation('summary-desktop.png')
        downloads = self.operation('summary-downloads.png',
                                   source=self.home / 'Downloads/summary-downloads.png')
        rendered = screenshot_summary([desktop, downloads], self.home)
        self.assertIn('Screenshots approved: 2', rendered)
        self.assertRegex(rendered, r'Desktop\s+1')
        self.assertRegex(rendered, r'Downloads\s+1')
        self.assertRegex(rendered, r'Documents\s+0')
        self.assertRegex(rendered, r'Pictures\s+0')
        self.assertRegex(rendered, r'Movies\s+0')
        self.assertIn('Pictures/\n└── Screenshots/', rendered)

    def test_missing_plan_sources_checks_entire_plan(self):
        present = self.operation('present.png')
        missing = self.operation('missing.png')
        pathlib.Path(missing.source).unlink()
        skipped_missing = self.operation('skipped-missing.png', decision='skipped')
        pathlib.Path(skipped_missing.source).unlink()
        self.assertEqual(missing_plan_sources(ReviewPlan([present, missing, skipped_missing])),
                         [missing.source, skipped_missing.source])

    def test_cli_stale_plan_stops_before_confirmation_or_executor(self):
        present = self.operation('cli-present.png')
        missing = self.operation('cli-missing.png')
        pathlib.Path(missing.source).unlink()
        plan_path = self.home / 'current_plan.json'
        ReviewPlan([present, missing]).save(plan_path)
        config = {'review': {'plan_file': str(plan_path)}}
        args = type('Args', (), {'pilot': True})()
        output = io.StringIO()
        with patch('roy._pilot_executor') as executor, \
                patch('builtins.input', side_effect=AssertionError('confirmation must not be requested')), \
                redirect_stdout(output):
            cmd_execute(args, config)
        executor.assert_not_called()
        self.assertTrue(plan_path.exists())
        self.assertIn('STALE PLAN', output.getvalue())
        self.assertIn('No operations were processed', output.getvalue())
        self.assertIn('python roy.py scan', output.getvalue())

    def test_rejects_category_unapproved_and_symlink(self):
        self.assertIn('screenshots_only', self.executor.validate(self.operation(category='Images')))
        self.assertIn('not_explicitly_approved', self.executor.validate(self.operation('pending.png', decision='pending')))
        target = self.desktop / 'target.png'; target.write_bytes(b'x')
        link = self.desktop / 'link.png'; link.symlink_to(target)
        stat = target.stat()
        op = PlanOperation(str(link), str(self.home/'Pictures/Screenshots/link.png'),
                           'Screenshots', 1, 'test', 'approved', stat.st_size, 'Desktop', stat.st_mtime)
        self.assertIn('symlink_rejected', self.executor.validate(op))

    def test_protected_source_destination_and_collision(self):
        protected = self.home / '.kube/config.png'
        self.assertIn('source_outside', self.executor.validate(self.operation(source=protected)))
        outside = self.home / 'Documents/out.png'
        self.assertIn('destination_outside', self.executor.validate(self.operation('outside.png', destination=outside)))
        op = self.operation('collision.png'); pathlib.Path(op.destination).parent.mkdir(parents=True); pathlib.Path(op.destination).write_bytes(b'x')
        self.assertIn('collision', self.executor.validate(op))

    def test_work_and_git_project_sources_are_protected(self):
        work = self.operation(source=self.desktop / 'company/Screenshot work.png')
        self.assertIn('work_data', self.executor.validate(work))
        project = self.desktop / 'project'; (project / '.git').mkdir(parents=True)
        git_operation = self.operation(source=project / 'Screenshot project.png')
        self.assertIn('software_project', self.executor.validate(git_operation))

    def test_changed_open_and_unknown_state(self):
        op = self.operation('changed.png'); pathlib.Path(op.source).write_bytes(b'changed')
        self.assertIn('source_changed', self.executor.validate(op))
        op = self.operation('open.png'); FakeChecker.open_paths = {pathlib.Path(op.source)}
        self.assertIn('open_file', self.executor.validate(op))
        FakeChecker.open_paths = set(); FakeChecker.state = 'OPEN_FILE_STATE_UNKNOWN'
        self.assertIn('open_file_state_unknown', self.executor.validate(self.operation('unknown.png')))

    def test_success_verify_and_complete_undo(self):
        operations = [self.operation(f'Screenshot success {number}.png') for number in range(2)]
        result = self.executor.execute(operations, 'EXECUTE PILOT')
        self.assertEqual(result['executed'], 2)
        self.assertTrue(self.executor.verify_last()['consistent'])
        undo = self.executor.undo_last()
        self.assertEqual(undo['undone'], 2)
        self.assertTrue(all(pathlib.Path(op.source).exists() for op in operations))
        self.assertTrue(self.executor.verify_last()['consistent'])

    def test_missing_year_and_month_folders_are_created_and_undone(self):
        op = self.operation('nested.png')
        year = pathlib.Path(op.destination).parents[1]
        month = pathlib.Path(op.destination).parent
        self.assertFalse(year.exists()); self.assertFalse(month.exists())
        result = self.executor.execute([op], 'EXECUTE PILOT')
        self.assertEqual(result['executed'], 1)
        self.assertTrue(year.is_dir()); self.assertTrue(month.is_dir())
        created = [record.destination for record in self.executor.journal.records()
                   if record.event == 'created_directory']
        self.assertEqual(created, [str(year), str(month)])
        self.executor.undo_last()
        self.assertFalse(month.exists()); self.assertFalse(year.exists())

    def test_existing_destination_folders_are_never_recorded_or_removed(self):
        parent = self.home / 'Pictures/Screenshots/2026/2026-08'
        parent.mkdir(parents=True)
        op = self.operation('existing-parent.png')
        self.executor.execute([op], 'EXECUTE PILOT')
        self.executor.undo_last()
        self.assertTrue(parent.is_dir())
        self.assertFalse(any(record.event == 'created_directory'
                             for record in self.executor.journal.records()))

    def test_symlink_and_protected_destination_parents_block(self):
        outside = self.home / 'outside'; outside.mkdir()
        link = self.home / 'Pictures/Screenshots/link'; link.symlink_to(outside, target_is_directory=True)
        op = self.operation('linked.png', destination=link / 'month/linked.png')
        self.assertIn('destination_parent_symlink', self.executor.validate(op))
        protected_parent = self.home / 'Pictures/Screenshots/protected'
        self.executor.config['safety']['protected_paths'].append(str(protected_parent))
        op = self.operation('protected-parent.png', destination=protected_parent / 'protected-parent.png')
        self.assertIn('destination_parent_protected', self.executor.validate(op))

    def test_approved_root_symlink_blocks(self):
        root = self.home / 'Pictures/Screenshots'
        root.rmdir()
        target = self.home / 'real-screenshots'; target.mkdir()
        root.symlink_to(target, target_is_directory=True)
        executor = PilotExecutor(self.config, self.log, home=self.home,
                                 checker_factory=FakeChecker)
        op = self.operation('root-link.png', destination=root / '2026/2026-08/root-link.png')
        self.assertIn('approved_destination_root_missing_or_invalid', executor.validate(op))

    def test_permission_denied_parent_blocks(self):
        op = self.operation('permission.png')
        root = self.home / 'Pictures/Screenshots'
        root.chmod(0o555)
        try:
            self.assertIn('destination_parent_permission_denied', self.executor.validate(op))
        finally:
            root.chmod(0o755)

    def test_sandboxed_os_access_false_does_not_override_writable_mode(self):
        op = self.operation('access-false.png')
        with patch('roy_validate.os.access', return_value=False):
            self.assertEqual(self.executor.validate(op), 'SAFE_TO_EXECUTE')

    def test_destination_diagnostics_are_read_only_and_complete(self):
        op = self.operation('diagnostic.png')
        destination = pathlib.Path(op.destination)
        before = destination.parent.exists()
        diagnostics = self.executor.destination_diagnostics(destination)
        self.assertEqual(destination.parent.exists(), before)
        self.assertEqual(set(diagnostics), {
            'expanded_destination_root', 'resolved_destination_root', 'root_exists',
            'root_is_dir', 'root_is_symlink', 'root_os_access_writable',
            'nearest_existing_parent', 'nearest_parent_os_access_writable',
            'nearest_parent_mode_creatable', 'under_approved_root'})
        self.assertTrue(diagnostics['root_exists'])
        self.assertTrue(diagnostics['root_is_dir'])
        self.assertFalse(diagnostics['root_is_symlink'])
        self.assertTrue(diagnostics['nearest_parent_mode_creatable'])
        self.assertTrue(diagnostics['under_approved_root'])

    def test_destination_path_traversal_blocks(self):
        destination = self.home / 'Pictures/Screenshots/../Documents/traversal.png'
        op = self.operation('traversal.png', destination=destination)
        self.assertIn('destination_path_traversal', self.executor.validate(op))

    def test_destination_block_explanation_is_human_readable(self):
        op = self.operation('explain.png')
        rendered = format_pilot_block(op, 'destination_parent_permission_denied')
        self.assertIn('Destination\n\n' + op.destination, rendered)
        self.assertIn('Reason', rendered)
        self.assertIn('Suggestion', rendered)

    def test_exact_confirmation_and_source_reappears_before_undo(self):
        op = self.operation('confirm.png')
        self.assertEqual(self.executor.execute([op], 'yes')['executed'], 0)
        self.executor.execute([op], 'EXECUTE PILOT')
        pathlib.Path(op.source).write_bytes(b'new')
        result = self.executor.undo_last()
        self.assertEqual(result['undone'], 0)
        self.assertIn('original_source_reappeared', result['blocked'][0][1])

    def test_changed_destination_blocks_undo(self):
        op = self.operation('destination-change.png')
        self.executor.execute([op], 'EXECUTE PILOT')
        pathlib.Path(op.destination).write_bytes(b'changed-after-move')
        result = self.executor.undo_last()
        self.assertEqual(result['undone'], 0)
        self.assertIn('pilot_destination_changed', result['blocked'][0][1])

    def test_interrupted_pilot_recovery_is_reported(self):
        op = self.operation('interrupt.png')
        batch = 'pilot-interrupted'
        record = PilotRecord('prepared', batch, 'now', op.source, op.destination,
                             'move', op.size, op.mtime, op.reason, 'SAFE_TO_EXECUTE')
        self.executor.journal.append(record)
        pathlib.Path(op.destination).parent.mkdir(parents=True)
        pathlib.Path(op.source).rename(op.destination)
        result = self.executor.verify_last()
        self.assertFalse(result['consistent'])
        self.assertIn('interrupted_after_move', result['anomalies'][0])
        recovery = self.executor.undo_last()
        self.assertEqual(recovery['undone'], 1)
        self.assertTrue(pathlib.Path(op.source).exists())
        self.assertTrue(self.executor.verify_last()['consistent'])

    def test_multi_hundred_screenshot_batch_one_identity_and_complete_undo(self):
        operations = [self.operation(f'Screenshot bulk {number}.png') for number in range(305)]
        progress = []
        result = self.executor.execute_screenshots(
            operations, 'EXECUTE SCREENSHOTS', progress.append)
        self.assertEqual(result['executed'], 305)
        self.assertEqual(result['blocked'], [])
        self.assertTrue(result['batch_id'].startswith(SCREENSHOT_PREFIX))
        executed_batches = {record.batch_id for record in self.executor.journal.records()
                            if record.event == 'executed'}
        self.assertEqual(len(executed_batches), 4)
        self.assertEqual(len(result['batches']), 4)
        self.assertEqual([batch['executed'] for batch in result['batches']], [100, 100, 100, 5])
        self.assertTrue(all(batch['batch_id'].startswith(result['run_id'] + '-batch-')
                            for batch in result['batches']))
        self.assertEqual([item['remaining'] for item in progress], [205, 105, 5, 0])
        self.assertEqual(self.executor.verify_last()['moved'], 305)
        history = self.executor.history()
        self.assertEqual(history[0]['run_id'], result['run_id'])
        self.assertEqual(history[0]['batches'], 4)
        self.assertTrue(history[0]['verified'])
        self.assertTrue(history[0]['undo_available'])
        undo = self.executor.undo_screenshot_run(result['run_id'])
        self.assertEqual(undo['undone'], 305)
        self.assertEqual(len(undo['batches']), 4)
        self.assertTrue(all(pathlib.Path(operation.source).exists() for operation in operations))
        self.assertFalse(self.executor.history()[0]['undo_available'])

    def test_interrupted_screenshot_batch_is_recoverable(self):
        operations = [self.operation(f'Screenshot interrupted {number}.png') for number in range(205)]
        real_move = pathlib.Path.rename
        calls = 0

        def interrupt_after_move(source, destination):
            nonlocal calls
            calls += 1
            real_move(pathlib.Path(source), pathlib.Path(destination))
            if calls == 151:
                raise KeyboardInterrupt()

        with patch('roy_pilot.shutil.move', side_effect=interrupt_after_move):
            with self.assertRaises(KeyboardInterrupt):
                self.executor.execute_screenshots(operations, 'EXECUTE SCREENSHOTS')
        verification = self.executor.verify_last()
        self.assertFalse(verification['consistent'])
        self.assertTrue(any('interrupted_after_move' in value
                            for value in verification['anomalies']))
        recovery = self.executor.undo_screenshot_run()
        self.assertEqual(recovery['undone'], 151)
        self.assertTrue(self.executor.verify_last()['consistent'])

    def test_cli_screenshot_undo_requires_exact_confirmation_and_undoes_run(self):
        operations = [self.operation(f'Screenshot cli undo {number}.png') for number in range(105)]
        self.executor.execute_screenshots(operations, 'EXECUTE SCREENSHOTS')
        with patch('roy._pilot_executor', return_value=self.executor), \
                patch('builtins.input', return_value='yes'), redirect_stdout(io.StringIO()):
            cmd_screenshot_undo(self.config)
        self.assertFalse(pathlib.Path(operations[0].source).exists())
        with patch('roy._pilot_executor', return_value=self.executor), \
                patch('builtins.input', return_value='UNDO SCREENSHOTS'), \
                redirect_stdout(io.StringIO()):
            cmd_screenshot_undo(self.config)
        self.assertTrue(all(pathlib.Path(operation.source).exists() for operation in operations))

    def test_screenshot_block_is_recorded_and_later_batches_continue(self):
        operations = [self.operation(f'Screenshot stop {number:03d}.png') for number in range(205)]
        collision = pathlib.Path(operations[120].destination)
        collision.parent.mkdir(parents=True, exist_ok=True)
        collision.write_bytes(b'collision')
        result = self.executor.execute_screenshots(operations, 'EXECUTE SCREENSHOTS')
        self.assertEqual(len(result['batches']), 3)
        self.assertEqual(result['batches'][0]['executed'], 100)
        self.assertEqual(result['batches'][1]['executed'], 99)
        self.assertEqual(result['batches'][2]['executed'], 5)
        self.assertEqual(len(result['blocked']), 1)
        self.assertTrue(pathlib.Path(operations[120].source).exists())
        self.assertTrue(all(not pathlib.Path(operation.source).exists()
                            for operation in operations[121:]))
        self.assertEqual(result['unprocessed'], [])
        report = self.home / 'blocked.json'
        save_blocked_screenshots(report, result['run_id'], operations, result['blocked'])
        retry = load_blocked_screenshots(report)
        self.assertEqual(len(retry), 1)
        self.assertEqual(retry[0].source, operations[120].source)


if __name__ == '__main__':
    unittest.main()
