import pathlib
import tempfile
import unittest
from unittest.mock import patch

from roy_alias_cleanup import (ScreenshotAliasCleanup, alias_cleanup_summary,
                               resolve_finder_alias)
from roy_safety import SafetyChecker


class AliasCleanupCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.temp.name)
        self.desktop = self.home / 'Desktop'; self.desktop.mkdir()
        self.screenshots = self.home / 'Pictures/Screenshots'; self.screenshots.mkdir(parents=True)
        self.config = {
            'scan_paths': [str(self.desktop)],
            'classification': {'work_terms': ['work', 'company']},
            'safety': {'skip_open_files': False, 'skip_hidden': True,
                       'skip_git_repos': True, 'protected_paths': []},
        }
        self.targets = {}

    def tearDown(self):
        self.temp.cleanup()

    def alias(self, name, target):
        path = self.desktop / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'fake Finder alias')
        self.targets[path] = target
        return path

    def cleanup(self):
        return ScreenshotAliasCleanup(
            self.config, home=self.home, detector=lambda path: path in self.targets,
            resolver=lambda path: self.targets[path], safety=SafetyChecker(self.config),
            journal_path=self.home / 'alias-journal.jsonl')

    def test_broken_redundant_and_elsewhere_alias_classification(self):
        organized = self.screenshots / '2026/a.png'; organized.parent.mkdir(); organized.write_bytes(b'x')
        elsewhere = self.home / 'elsewhere.png'; elsewhere.write_bytes(b'x')
        broken = self.alias('Screenshot 2026-01-01 at 10.00.00 alias', self.home/'missing.png')
        redundant = self.alias('Screenshot 2026-01-02 at 10.00.00 alias', organized)
        retained = self.alias('Screenshot 2026-01-03 at 10.00.00 alias', elsewhere)
        by_path = {item.path: item for item in self.cleanup().discover()}
        self.assertEqual(by_path[str(broken)].status, 'broken')
        self.assertEqual(by_path[str(redundant)].status, 'redundant')
        self.assertEqual(by_path[str(retained)].status, 'retained')

    def test_unresolved_alias_is_broken_and_symlink_is_not_alias(self):
        alias = self.alias('Screenshot 2026-02-01 at 10.00.00 alias', None)
        target = self.desktop / 'target'; target.write_bytes(b'x')
        link = self.desktop / 'Screenshot 2026-02-02 at 10.00.00 alias'; link.symlink_to(target)
        self.targets[link] = target
        found = self.cleanup().discover()
        self.assertEqual([item.path for item in found], [str(alias)])
        self.assertEqual(found[0].status, 'broken')

    def test_exact_confirmation_moves_only_eligible_aliases_to_trash(self):
        organized = self.screenshots / 'a.png'; organized.write_bytes(b'x')
        eligible = self.alias('Screenshot 2026-03-01 at 10.00.00 alias', organized)
        elsewhere = self.home / 'elsewhere.png'; elsewhere.write_bytes(b'x')
        retained = self.alias('Screenshot 2026-03-02 at 10.00.00 alias', elsewhere)
        cleanup = self.cleanup(); candidates = cleanup.discover()
        denied = cleanup.quarantine(candidates, 'yes')
        self.assertEqual(denied['quarantined'], 0)
        result = cleanup.quarantine(candidates, 'DELETE SCREENSHOT ALIASES')
        self.assertEqual(result['quarantined'], 1)
        self.assertFalse(eligible.exists()); self.assertTrue(retained.exists())
        trashed = list((self.home/'.Trash/ROY Organizer').rglob('*alias'))
        self.assertEqual(len(trashed), 1)
        self.assertIn('moved to Trash', alias_cleanup_summary(candidates))

    def test_work_and_project_aliases_are_retained(self):
        work = self.alias('work/Screenshot 2026-04-01 at 10.00.00 alias', None)
        project = self.alias('project/Screenshot 2026-04-02 at 10.00.00 alias', None)
        (project.parent / '.git').mkdir()
        by_path = {item.path: item for item in self.cleanup().discover()}
        self.assertEqual(by_path[str(work)].status, 'retained')
        self.assertEqual(by_path[str(project)].status, 'retained')

    def test_metadata_resolver_does_not_spawn_or_open_an_app(self):
        alias = self.desktop / 'nonexistent screenshot alias'
        with patch('roy_alias_cleanup.subprocess.run') as run:
            self.assertIsNone(resolve_finder_alias(alias))
        run.assert_not_called()

    def test_symlinked_trash_is_blocked(self):
        organized = self.screenshots / 'a.png'; organized.write_bytes(b'x')
        self.alias('Screenshot 2026-05-01 at 10.00.00 alias', organized)
        outside = self.home / 'outside'; outside.mkdir()
        (self.home / '.Trash').symlink_to(outside, target_is_directory=True)
        cleanup = self.cleanup()
        result = cleanup.quarantine(cleanup.discover(), 'DELETE SCREENSHOT ALIASES')
        self.assertEqual(result['quarantined'], 0)
        self.assertEqual(result['blocked'], [('trash', 'trash_path_unsafe')])


if __name__ == '__main__':
    unittest.main()
