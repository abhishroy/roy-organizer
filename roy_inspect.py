"""Bounded, local-only inspection for protected configs and ZIP archives."""
import pathlib
import re
import zipfile
from dataclasses import dataclass
from typing import Optional


MAX_CONFIG_BYTES = 256 * 1024
MAX_ZIP_METADATA_BYTES = 64 * 1024
MAX_ZIP_ENTRIES = 5000


def inspect_kubeconfig(path: pathlib.Path) -> bool:
    """Detect kubeconfig structure without parsing, logging, or returning secrets."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_CONFIG_BYTES:
            return False
        if path.suffix.lower() not in {'', '.yaml', '.yml', '.conf', '.config', '.txt'}:
            return False
        text = path.read_text(errors='ignore')
    except (OSError, UnicodeError):
        return False
    score = 0
    strong = 0
    signals = [
        (r'(?m)^\s*apiVersion\s*:\s*v1\s*$', 1, False),
        (r'(?m)^\s*kind\s*:\s*Config\s*$', 3, True),
        (r'(?m)^\s*clusters\s*:', 3, True),
        (r'(?m)^\s*contexts\s*:', 3, True),
        (r'(?m)^\s*current-context\s*:', 3, True),
        (r'(?m)^\s*users\s*:', 3, True),
        (r'(?m)^\s*server\s*:\s*https?://', 2, False),
        (r'(?m)^\s*client-certificate-data\s*:', 2, False),
        (r'(?m)^\s*client-key-data\s*:', 2, False),
        (r'(?m)^\s*token\s*:', 2, False),
    ]
    for pattern, points, is_strong in signals:
        if re.search(pattern, text):
            score += points
            strong += int(is_strong)
    return score >= 9 and strong >= 2


@dataclass
class ZipInspection:
    is_repository: bool = False
    origin: str = 'general'
    owner: Optional[str] = None
    confidence: float = 0.0
    reason: str = 'Ordinary archive'
    corrupted: bool = False


def inspect_zip(path: pathlib.Path) -> ZipInspection:
    """Inspect names and bounded metadata in-place; never extract or execute."""
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()[:MAX_ZIP_ENTRIES]
            names = [info.filename.lower() for info in infos]
            score = 0
            tests = [
                (lambda n: n.endswith('/readme.md') or n.endswith('/readme'), 1),
                (lambda n: n.endswith('/.gitignore'), 2),
                (lambda n: '/.github/' in n, 3),
                (lambda n: n.endswith('/.gitlab-ci.yml'), 3),
                (lambda n: n.endswith(('/package.json', '/pyproject.toml', '/cargo.toml',
                                        '/go.mod', '/pom.xml', '/build.gradle')), 3),
                (lambda n: n.endswith(('/dockerfile', '/docker-compose.yml')), 2),
                (lambda n: '/src/' in n, 2),
                (lambda n: '/tests/' in n, 1),
            ]
            for predicate, points in tests:
                if any(predicate(name) for name in names):
                    score += points
            evidence = ' '.join(names[:500])
            for info in infos:
                lower = info.filename.lower()
                if info.file_size <= MAX_ZIP_METADATA_BYTES and lower.endswith(
                        ('readme', 'readme.md', '.git/config', 'package.json', 'pyproject.toml')):
                    try:
                        evidence += ' ' + archive.read(info, MAX_ZIP_METADATA_BYTES).decode('utf-8', 'ignore').lower()
                    except (OSError, RuntimeError, zipfile.BadZipFile):
                        pass
            origin, owner = 'unknown', None
            if 'github.com/abhishroy' in evidence:
                origin, owner = 'personal', 'abhishroy'
            elif 'github.com/abhishek-roy_adevinta' in evidence:
                origin, owner = 'company', 'abhishek-roy_adevinta'
            elif 'github.mpi-internal.com' in evidence:
                origin, owner = 'company_internal', 'mpi-internal'
            is_repo = score >= 6
            if not is_repo:
                return ZipInspection()
            return ZipInspection(True, origin, owner, min(0.99, 0.5 + score / 20),
                                 'Repository structure detected')
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return ZipInspection(corrupted=True, reason='Unreadable or corrupted ZIP archive')
