"""Explicit, quarantined cleanup for screenshot-like macOS Finder aliases."""
from __future__ import annotations

import json
import ctypes
import pathlib
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

from roy_classify import Classifier
from roy_safety import SafetyChecker


@dataclass
class AliasCandidate:
    path: str
    target: Optional[str]
    status: str
    reason: str


def is_finder_alias(path: pathlib.Path) -> bool:
    """Identify Finder alias data without following symlinks or launching apps."""
    if path.is_symlink() or not path.is_file():
        return False
    try:
        result = subprocess.run(['file', '-b', str(path)], capture_output=True,
                                text=True, timeout=2, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and 'MacOS Alias file' in result.stdout


def resolve_finder_alias(path: pathlib.Path) -> Optional[pathlib.Path]:
    """Resolve with Foundation's no-UI API; never opens or executes a target."""
    try:
        from ctypes.util import find_library
        ctypes.CDLL(find_library('Foundation'))
        objc = ctypes.CDLL(find_library('objc'))
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        message = objc.objc_msgSend
        message.restype = ctypes.c_void_p
        ns_string = objc.objc_getClass(b'NSString')
        ns_url = objc.objc_getClass(b'NSURL')
        message.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p]
        path_string = message(ns_string, objc.sel_registerName(b'stringWithUTF8String:'),
                              str(path).encode())
        message.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        alias_url = message(ns_url, objc.sel_registerName(b'fileURLWithPath:'), path_string)
        error = ctypes.c_void_p()
        message.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                            ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p)]
        # NSURLBookmarkResolutionWithoutUI | NSURLBookmarkResolutionWithoutMounting
        target_url = message(
            ns_url, objc.sel_registerName(b'URLByResolvingAliasFileAtURL:options:error:'),
            alias_url, (1 << 8) | (1 << 9), ctypes.byref(error))
        if not target_url:
            return None
        message.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        target_path = message(target_url, objc.sel_registerName(b'path'))
        message.restype = ctypes.c_char_p
        encoded = message(target_path, objc.sel_registerName(b'UTF8String'))
        resolved = pathlib.Path(encoded.decode()) if encoded else None
        if resolved is not None and resolved.resolve(strict=False) == path.resolve(strict=False):
            return None
        return resolved
    except (AttributeError, OSError, TypeError, UnicodeError):
        return None


class ScreenshotAliasCleanup:
    """Discover aliases and quarantine only broken/redundant safe candidates."""

    def __init__(self, config: dict, *, home: Optional[pathlib.Path] = None,
                 resolver: Callable[[pathlib.Path], Optional[pathlib.Path]] = resolve_finder_alias,
                 detector: Callable[[pathlib.Path], bool] = is_finder_alias,
                 safety: Optional[SafetyChecker] = None,
                 journal_path: pathlib.Path = pathlib.Path('logs/alias-cleanup.jsonl')):
        self.config = config
        self.home = (home or pathlib.Path.home()).resolve()
        self.screenshot_root = (self.home / 'Pictures' / 'Screenshots').resolve()
        self.resolver = resolver
        self.detector = detector
        self.safety = safety or SafetyChecker(config)
        self.journal_path = journal_path
        self.classifier = Classifier(config)

    def discover(self) -> list[AliasCandidate]:
        if self.config.get('safety', {}).get('skip_open_files', True):
            self.safety.prepare_open_files()
        result = []
        for configured in self.config.get('scan_paths', []):
            root = pathlib.Path(str(configured).replace('~', str(self.home), 1))
            if not root.exists():
                continue
            for path in root.rglob('*'):
                if path.is_symlink() or not self.classifier.is_screenshot(path.name):
                    continue
                if not self.detector(path):
                    continue
                source_check = self.safety.check_source(path)
                if not source_check.safe:
                    result.append(AliasCandidate(str(path), None, 'retained',
                                                 source_check.skip_reason or 'protected'))
                    continue
                target = self.resolver(path)
                if target is None or not target.exists():
                    result.append(AliasCandidate(str(path), str(target) if target else None,
                                                 'broken', 'Alias target does not exist'))
                elif target.resolve().is_relative_to(self.screenshot_root):
                    result.append(AliasCandidate(str(path), str(target), 'redundant',
                                                 'Target is already organized'))
                else:
                    result.append(AliasCandidate(str(path), str(target), 'retained',
                                                 'Target is outside screenshot destination'))
        return result

    def quarantine(self, candidates: Iterable[AliasCandidate], confirmation: str) -> dict:
        eligible = [item for item in candidates if item.status in {'broken', 'redundant'}]
        if confirmation != 'DELETE SCREENSHOT ALIASES':
            return {'quarantined': 0, 'blocked': [('confirmation', 'exact_confirmation_required')]}
        if self.config.get('safety', {}).get('skip_open_files', True):
            self.safety.prepare_open_files()
        run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S-') + uuid.uuid4().hex[:8]
        # Quarantine means a run-specific folder in the current user's Trash.
        # ROY never empties Trash or permanently deletes these aliases.
        root = self.home / '.Trash' / 'ROY Organizer' / 'screenshot-aliases' / run_id
        trash = self.home / '.Trash'
        if self.home.is_symlink() or trash.is_symlink() or (trash.exists() and not trash.is_dir()):
            return {'run_id': run_id, 'quarantined': 0,
                    'blocked': [('trash', 'trash_path_unsafe')]}
        quarantined, blocked = 0, []
        for index, item in enumerate(eligible, 1):
            source = pathlib.Path(item.path)
            check = self.safety.check_source(source)
            if (not check.safe or source.is_symlink() or not self.detector(source)):
                blocked.append((item.path, check.skip_reason or 'alias_validation_failed'))
                continue
            target = self.resolver(source)
            currently_eligible = (target is None or not target.exists() or
                                  target.resolve().is_relative_to(self.screenshot_root))
            if not currently_eligible:
                blocked.append((item.path, 'alias_target_requires_review'))
                continue
            destination = root / f'{index:04d}-{source.name}'
            if destination.exists():
                blocked.append((item.path, 'quarantine_collision'))
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            self.journal_path.parent.mkdir(parents=True, exist_ok=True)
            record = {'event': 'alias_quarantined', 'run_id': run_id,
                      'timestamp': datetime.now(timezone.utc).isoformat(),
                      'source': str(source), 'quarantine': str(destination),
                      'status': item.status, 'reason': item.reason}
            with self.journal_path.open('a') as handle:
                handle.write(json.dumps(record, sort_keys=True) + '\n')
                handle.flush()
            quarantined += 1
        return {'run_id': run_id, 'quarantined': quarantined, 'blocked': blocked}


def alias_cleanup_summary(candidates: Iterable[AliasCandidate]) -> str:
    items = list(candidates)
    counts = {status: sum(item.status == status for item in items)
              for status in ('broken', 'redundant', 'retained')}
    paths = '\n'.join(f"  [{item.status.upper()}] {item.path}" for item in items) or '  None'
    deletes = counts['broken'] + counts['redundant']
    return (f"SCREENSHOT ALIAS CLEANUP\n\nTotal aliases found: {len(items):,}\n"
            f"Broken aliases: {counts['broken']:,}\nRedundant aliases: {counts['redundant']:,}\n"
            f"Aliases retained: {counts['retained']:,}\n\nPaths:\n{paths}\n\n"
            f"Deletes: {deletes:,} (moved to Trash; no permanent deletion)\nOverwrites: 0")
