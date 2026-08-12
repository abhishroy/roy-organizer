"""Phase 3 safety tests. All filesystem access is confined to temporary roots."""
import io
import pathlib
import subprocess
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from datetime import datetime
from unittest.mock import patch

from roy_classify import Category, FileInfo
from roy_inspect import inspect_kubeconfig, inspect_zip
from roy_plan import PlanOperation, ReviewPlan, SAFE_CATEGORIES
from roy_safety import SafetyChecker
from roy_scan import ScanStats, Scanner
from roy_validate import ExecutionValidator


def base_config(**safety):
    values = {'protected_paths': [], 'skip_hidden': True, 'skip_git_repos': True,
              'skip_open_files': True, 'planning_only': False}
    values.update(safety)
    return {'machine_profile': 'developer_company_managed', 'safety': values,
            'classification': {'work_terms': ['work', 'company', 'adevinta']}}


KUBE = """apiVersion: v1
kind: Config
clusters:
- cluster:
    server: https://cluster.invalid
contexts:
- context:
    cluster: prod
    user: me
current-context: prod
users:
- user:
    token: TOP-SECRET-TOKEN
    client-certificate-data: TOP-SECRET-CERT
"""


class TestDeveloperProtection(unittest.TestCase):
    def test_explicit_developer_paths(self):
        with tempfile.TemporaryDirectory() as tmp, patch('roy_safety.pathlib.Path.home', return_value=pathlib.Path(tmp)):
            home = pathlib.Path(tmp)
            checker = SafetyChecker(base_config())
            paths = [home/'.zshrc', home/'.oh-my-zsh/themes/a.zsh-theme', home/'.aws/credentials',
                     home/'.ssh/config', home/'.vscode/settings.json', home/'.terraform.d/plugin',
                     home/'.docker/config.json', home/'.config/gcloud/configurations/default']
            for path in paths:
                with self.subTest(path=path):
                    self.assertTrue(checker.is_developer_config(path))

    def test_homebrew_and_company_security_are_protected(self):
        checker = SafetyChecker(base_config())
        self.assertTrue(checker.is_developer_config(pathlib.Path('/opt/homebrew/bin/brew')))
        for path in ['/Library/CS/falcond', '/Library/Application Support/AirWatch/a',
                     '/Library/PaloAltoNetworks/GlobalProtect/a', '/Library/MDM/profile']:
            self.assertTrue(checker.is_company_security_path(pathlib.Path(path)))

    def test_project_markers(self):
        markers = ['.git', '.github', 'package.json', 'build.gradle', 'Dockerfile',
                   'Makefile', 'main.tf', 'gradlew']
        for marker in markers:
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as tmp:
                home = pathlib.Path(tmp); project = home/'project'; project.mkdir()
                target = project/'file.txt'; target.write_text('x')
                marker_path = project/marker
                marker_path.mkdir() if marker.startswith('.') and marker in {'.git', '.github'} else marker_path.write_text('x')
                with patch('roy_safety.pathlib.Path.home', return_value=home):
                    checker = SafetyChecker(base_config())
                    self.assertTrue(checker.is_in_software_project(target))


class TestKubeconfigDetection(unittest.TestCase):
    def test_arbitrary_names_extensions_and_secret_forms(self):
        for name in ['green.yaml', 'cluster-eu', 'config', 'dev-access.txt', 'something.conf']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp)/name; path.write_text(KUBE + '\n  client-key-data: SECRET-KEY\n')
                self.assertTrue(inspect_kubeconfig(path))

    def test_false_positives(self):
        samples = {
            'ordinary.yaml': 'name: demo\ncolor: blue\n',
            'values.yaml': 'replicaCount: 2\nimage:\n  repository: nginx\n',
            'deployment.yaml': 'apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: web\n',
            'service.yaml': 'apiVersion: v1\nkind: Service\nspec:\n  ports: []\n',
        }
        with tempfile.TemporaryDirectory() as tmp:
            for name, content in samples.items():
                path = pathlib.Path(tmp)/name; path.write_text(content)
                self.assertFalse(inspect_kubeconfig(path), name)

    def test_kube_path_and_symlink_are_protected(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = pathlib.Path(tmp); kube = home/'.kube'; kube.mkdir(); target = kube/'anything'; target.write_text(KUBE)
            link = home/'Documents'/'link.yaml'; link.parent.mkdir(); link.symlink_to(target)
            with patch('roy_safety.pathlib.Path.home', return_value=home):
                checker = SafetyChecker(base_config()); checker.open_files = set(); checker.open_file_state = 'KNOWN'
                self.assertEqual(checker.check_source(target).skip_reason, 'developer_config')
                self.assertEqual(checker.check_source(link).skip_reason, 'developer_config')

    def test_no_secret_leakage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp)/'green.yaml'; path.write_text(KUBE)
            checker = SafetyChecker(base_config()); checker.open_files=set(); checker.open_file_state='KNOWN'
            output = io.StringIO()
            with redirect_stdout(output):
                result = checker.check_source(path)
            self.assertEqual(result.reason, 'Protected: Kubernetes configuration')
            self.assertNotIn('TOP-SECRET', output.getvalue() + result.reason)


def make_repo_zip(path, remote=None):
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('project-main/README.md', f'remote {remote or "local"}')
        archive.writestr('project-main/.gitignore', '*.pyc')
        archive.writestr('project-main/package.json', '{}')
        archive.writestr('project-main/src/main.js', 'x')


class TestZipInspection(unittest.TestCase):
    def test_repository_origins(self):
        cases = [('github.com/abhishroy/repo', 'personal', 'abhishroy'),
                 ('github.com/abhishek-roy_adevinta/repo', 'company', 'abhishek-roy_adevinta'),
                 ('github.mpi-internal.com/team/repo', 'company_internal', 'mpi-internal'),
                 (None, 'unknown', None)]
        with tempfile.TemporaryDirectory() as tmp:
            for index, (remote, origin, owner) in enumerate(cases):
                path = pathlib.Path(tmp)/f'{index}.zip'; make_repo_zip(path, remote)
                result = inspect_zip(path)
                self.assertTrue(result.is_repository)
                self.assertEqual((result.origin, result.owner), (origin, owner))

    def test_ordinary_and_corrupt_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            ordinary = pathlib.Path(tmp)/'holiday-main.zip'
            with zipfile.ZipFile(ordinary, 'w') as archive:
                archive.writestr('holiday-main/photo.jpg', b'image')
            self.assertFalse(inspect_zip(ordinary).is_repository)
            corrupt = pathlib.Path(tmp)/'bad.zip'; corrupt.write_bytes(b'not zip')
            self.assertTrue(inspect_zip(corrupt).corrupted)
            self.assertEqual(set(pathlib.Path(tmp).iterdir()), {ordinary, corrupt})

    def test_company_archive_excluded_from_approve_all(self):
        self.assertIn(Category.REPOSITORY_ARCHIVE, SAFE_CATEGORIES)
        info = FileInfo(path=pathlib.Path('/tmp/company.zip'), filename='company.zip', extension='.zip',
                        category=Category.REPOSITORY_ARCHIVE, confidence=.9,
                        proposed_destination=None, work_review=True, archive_origin='company')
        plan = ReviewPlan.from_inventory([info], ScanStats(), SAFE_CATEGORIES)
        self.assertEqual(plan.operations, [])


class TestOpenFileFailSafe(unittest.TestCase):
    @patch('roy_safety.subprocess.run')
    def test_success(self, run):
        run.return_value.returncode=0; run.return_value.stdout='p1\nn/tmp/a\n'
        checker=SafetyChecker(base_config()); checker.prepare_open_files()
        self.assertEqual(checker.open_file_state, 'KNOWN')

    def _assert_unknown(self, side_effect=None, returncode=0, stdout='garbage'):
        with patch('roy_safety.subprocess.run') as run:
            if side_effect: run.side_effect=side_effect
            else: run.return_value.returncode=returncode; run.return_value.stdout=stdout
            checker=SafetyChecker(base_config()); checker.prepare_open_files()
            self.assertEqual(checker.open_file_state, 'OPEN_FILE_STATE_UNKNOWN')
            self.assertIsNone(checker.open_files)

    def test_timeout_nonzero_missing_and_malformed(self):
        self._assert_unknown(subprocess.TimeoutExpired('lsof', 1))
        self._assert_unknown(returncode=1, stdout='')
        self._assert_unknown(FileNotFoundError())
        self._assert_unknown(returncode=0, stdout='malformed')


class TestExecutionValidator(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.home=pathlib.Path(self.temp.name)
        self.source=self.home/'Desktop'/'a.txt'; self.source.parent.mkdir(); self.source.write_text('hello')
        self.dest=self.home/'Documents'/'Organized'/'a.txt'; (self.home/'Documents').mkdir()
        stat=self.source.stat()
        self.operation=PlanOperation(str(self.source), str(self.dest), 'Documents', .9, 'test',
                                     'approved', stat.st_size, 'Desktop', stat.st_mtime)

    def tearDown(self): self.temp.cleanup()

    def validator(self, checker=None):
        config=base_config(allowed_destination_roots=[str(self.home/'Documents')]); config['machine_profile']='personal'
        with patch('roy_safety.pathlib.Path.home', return_value=self.home):
            checker=checker or SafetyChecker(config)
        checker.open_files=set(); checker.open_file_state='KNOWN'
        return ExecutionValidator(config, checker)

    def test_safe_and_collision(self):
        self.assertTrue(self.validator().validate(self.operation).safe)
        self.dest.parent.mkdir(); self.dest.write_text('existing')
        self.assertEqual(self.validator().validate(self.operation).reason, 'collision')

    def test_changed_newly_open_and_protected_destination(self):
        self.source.write_text('changed')
        self.assertEqual(self.validator().validate(self.operation).reason, 'source_changed_review_again')
        self.source.write_text('hello'); stat=self.source.stat(); self.operation.mtime=stat.st_mtime
        validator=self.validator(); validator.safety.open_files={self.source.resolve()}
        self.assertEqual(validator.validate(self.operation).reason, 'open_file')
        self.operation.destination='/System/a.txt'
        self.assertIn(self.validator().validate(self.operation).reason, {'protected_path', 'outside_allowed'})

    def test_unknown_open_state_and_planning_only(self):
        validator=self.validator(); validator.safety.open_file_state='OPEN_FILE_STATE_UNKNOWN'
        self.assertEqual(validator.validate(self.operation).reason, 'open_file_state_unknown')
        validator.config['safety']['planning_only']=True
        self.assertEqual(validator.validate(self.operation).reason, 'planning_only')


if __name__ == '__main__':
    unittest.main()
