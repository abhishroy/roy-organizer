"""
Tests for safety module.
"""
import unittest
import tempfile
import pathlib
import os
from unittest.mock import patch

from roy_safety import SafetyChecker, SafetyCheckResult


class TestSafetyChecker(unittest.TestCase):
    def test_application_managed_media_library_internals_are_protected(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = pathlib.Path(tmp)
            for suffix in ('.imovielibrary', '.photoslibrary', '.musiclibrary',
                           '.fcpbundle', '.logicx'):
                source = home / f'Library{suffix}' / 'Original Media' / 'clip.mov'
                source.parent.mkdir(parents=True)
                source.write_bytes(b'video')
                with self.subTest(suffix=suffix):
                    result = self.checker.check_source(source)
                    self.assertFalse(result.safe)
                    self.assertEqual(result.skip_reason, 'protected_media_library')

    def test_normal_media_folder_is_not_treated_as_application_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = pathlib.Path(tmp) / 'Vacation' / 'clip.mov'
            source.parent.mkdir(); source.write_bytes(b'video')
            self.assertFalse(self.checker.is_in_protected_bundle(source))

    """Test safety checking functionality."""
    
    def setUp(self):
        """Set up test config."""
        self.config = {
            'safety': {
                'protected_paths': [
                    '/System',
                    '/Library',
                    '/Applications',
                    '~/.ssh',
                    '~/.aws',
                ],
                'skip_hidden': True,
                'skip_git_repos': True,
            },
            'classification': {
                'work_terms': ['work', 'company', 'prod', 'github', 'repo']
            }
        }
        self.checker = SafetyChecker(self.config)
    
    def test_protected_paths(self):
        """Test protected path detection."""
        # System paths should be protected
        self.assertFalse(self.checker.is_protected(pathlib.Path('/System/Library/test.txt')).safe)
        self.assertFalse(self.checker.is_protected(pathlib.Path('/Library/Application Support/test.txt')).safe)
        self.assertFalse(self.checker.is_protected(pathlib.Path('/Applications/Test.app')).safe)
        
        # User paths should not be protected
        self.assertTrue(self.checker.is_protected(pathlib.Path('/Users/test/Desktop/file.txt')).safe)
        self.assertTrue(self.checker.is_protected(pathlib.Path('/Users/test/Downloads/file.txt')).safe)
    
    def test_hidden_files(self):
        """Test hidden file detection."""
        self.assertTrue(self.checker.is_hidden(pathlib.Path('/Users/test/.hidden_file')))
        self.assertTrue(self.checker.is_hidden(pathlib.Path('/Users/test/.config/file')))
        self.assertFalse(self.checker.is_hidden(pathlib.Path('/Users/test/visible_file')))
    
    def test_work_terms(self):
        """Test work term detection."""
        self.assertTrue(self.checker.has_work_terms(pathlib.Path('/Users/test/work/project/file.txt')))
        self.assertTrue(self.checker.has_work_terms(pathlib.Path('/Users/test/company/docs/file.txt')))
        self.assertTrue(self.checker.has_work_terms(pathlib.Path('/Users/test/github/repo/file.txt')))
        self.assertFalse(self.checker.has_work_terms(pathlib.Path('/Users/test/personal/file.txt')))

    def test_home_git_directory_does_not_mark_all_user_files_as_repo_files(self):
        """A ~/.git directory must not exclude every normal file under home."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = pathlib.Path(tmpdir)
            (home / '.git').mkdir()
            normal_file = home / 'Documents' / 'personal.txt'
            normal_file.parent.mkdir()
            normal_file.write_text('personal')

            repo_file = home / 'Documents' / 'project' / 'code.py'
            repo_file.parent.mkdir()
            (repo_file.parent / '.git').mkdir()
            repo_file.write_text('print("hello")')

            with patch('roy_safety.pathlib.Path.home', return_value=home):
                self.assertFalse(self.checker.is_in_git_repo(normal_file))
                self.assertTrue(self.checker.is_in_git_repo(repo_file))

    def test_project_markers_protect_project_internals(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            home = pathlib.Path(tmpdir)
            project = home / 'Documents' / 'project'
            project.mkdir(parents=True)
            (project / 'pyproject.toml').write_text('[project]')
            source = project / 'src' / 'main.py'
            source.parent.mkdir()
            source.write_text('print("safe")')
            normal = home / 'Documents' / 'notes.py'
            normal.write_text('# note')
            with patch('roy_safety.pathlib.Path.home', return_value=home):
                self.assertTrue(self.checker.is_in_software_project(source))
                self.assertFalse(self.checker.is_in_software_project(normal))

    @patch('roy_safety.subprocess.run')
    def test_open_files_are_loaded_once_and_cached(self, run):
        run.return_value.stdout = 'p123\nn/tmp/open.txt\nn/tmp/other.txt\n'
        run.return_value.returncode = 0
        self.checker.prepare_open_files()
        self.assertTrue(self.checker.is_open_by_app(pathlib.Path('/tmp/open.txt')))
        self.assertFalse(self.checker.is_open_by_app(pathlib.Path('/tmp/closed.txt')))
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], ['lsof', '-Fn'])
    
    def test_check_source_safe(self):
        """Test checking a safe source file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = pathlib.Path(tmpdir) / 'safe_file.txt'
            test_file.write_text('test')
            
            result = self.checker.check_source(test_file)
            self.assertTrue(result.safe)
            self.assertIsNone(result.skip_reason)
    
    def test_check_source_hidden(self):
        """Test checking a hidden file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = pathlib.Path(tmpdir) / '.hidden_file'
            test_file.write_text('test')
            
            result = self.checker.check_source(test_file)
            self.assertFalse(result.safe)
            self.assertEqual(result.skip_reason, 'hidden_file')
    
    def test_check_destination_collision(self):
        """Test destination collision detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source = pathlib.Path(tmpdir) / 'source.txt'
            dest = pathlib.Path(tmpdir) / 'dest.txt'
            source.write_text('source')
            dest.write_text('dest')
            
            result = self.checker.check_destination(dest, source)
            self.assertFalse(result.safe)
            self.assertEqual(result.skip_reason, 'collision')


class TestPathSafety(unittest.TestCase):
    """Test path safety utilities."""
    
    def test_expand_paths(self):
        """Test path expansion."""
        config = {
            'safety': {
                'protected_paths': ['~/test', '/absolute/path']
            }
        }
        checker = SafetyChecker(config)
        # Just verify it doesn't crash
        self.assertGreaterEqual(len(checker.protected_paths), 1)


if __name__ == '__main__':
    unittest.main()
