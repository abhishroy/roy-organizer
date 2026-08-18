"""Explicitly gated, screenshot-only real execution pilot."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import pathlib
import re
import shutil
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

from roy_plan import DEFAULT_SOURCE_NAMES, PlanOperation, ReviewPlan, source_folder
from roy_safety import SafetyChecker
from roy_validate import ExecutionValidator


PILOT_LIMIT = 20
PILOT_PREFIX = "pilot-"
SCREENSHOT_PREFIX = "screenshots-"
IMAGE_PREFIX = "images-"
SCREENSHOT_CHUNK_SIZE = 100
CONTROLLED_PREFIXES = (PILOT_PREFIX, SCREENSHOT_PREFIX, IMAGE_PREFIX)


@dataclass
class PilotRecord:
    event: str
    batch_id: str
    timestamp: str
    source: str
    destination: str
    operation: str
    size: int
    mtime: float
    reason: str
    validation_result: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def strong_file_hash(path: pathlib.Path) -> str:
    """Return a streaming SHA-256 digest without retaining file contents."""
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def same_stable_file_content(source: pathlib.Path, destination: pathlib.Path) -> bool:
    """Hash two regular files and reject content that changes during comparison."""
    source_before = source.stat()
    destination_before = destination.stat()
    if source_before.st_size != destination_before.st_size:
        return False
    source_hash = strong_file_hash(source)
    destination_hash = strong_file_hash(destination)
    source_after = source.stat()
    destination_after = destination.stat()
    source_stable = (source_before.st_size, source_before.st_mtime_ns) == (
        source_after.st_size, source_after.st_mtime_ns)
    destination_stable = (destination_before.st_size, destination_before.st_mtime_ns) == (
        destination_after.st_size, destination_after.st_mtime_ns)
    return source_stable and destination_stable and source_hash == destination_hash


class PilotJournal:
    """Durable append-only pilot journal; contents never include file data."""

    def __init__(self, path: pathlib.Path):
        self.path = path

    def append(self, record: PilotRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as handle:
            handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def records(self) -> list[PilotRecord]:
        if not self.path.exists():
            return []
        result = []
        for number, line in enumerate(self.path.read_text().splitlines(), 1):
            try:
                result.append(PilotRecord(**json.loads(line)))
            except (json.JSONDecodeError, TypeError) as error:
                raise ValueError(f"corrupt_pilot_log_line_{number}") from error
        return result

    def last_batch(self, prefixes: tuple[str, ...] = CONTROLLED_PREFIXES) -> Optional[str]:
        for record in reversed(self.records()):
            if record.batch_id.startswith(prefixes):
                return record.batch_id
        return None

    def last_active_batch(self, prefixes: tuple[str, ...] = CONTROLLED_PREFIXES) -> Optional[str]:
        """Return the newest batch with a move that has not been undone."""
        records = self.records()
        batches = []
        for record in records:
            if record.batch_id.startswith(prefixes) and record.batch_id not in batches:
                batches.append(record.batch_id)
        for batch_id in reversed(batches):
            moved = set()
            for record in records:
                if record.batch_id != batch_id or record.operation != 'move':
                    continue
                if record.event == 'executed':
                    moved.add(record.source)
                elif (record.event == 'prepared'
                      and pathlib.Path(record.destination).exists()
                      and not pathlib.Path(record.source).exists()):
                    moved.add(record.source)
            undone = {record.source for record in records
                      if record.batch_id == batch_id and record.event == 'undone'}
            if moved - undone:
                return batch_id
        return None

    @staticmethod
    def run_id(batch_id: str) -> str:
        return batch_id.rsplit('-batch-', 1)[0] if '-batch-' in batch_id else batch_id

    def run_batch_ids(self, run_id: str) -> list[str]:
        return sorted({record.batch_id for record in self.records()
                       if self.run_id(record.batch_id) == run_id})

    def last_run(self, prefixes: tuple[str, ...] = CONTROLLED_PREFIXES) -> Optional[str]:
        batch_id = self.last_batch(prefixes)
        return self.run_id(batch_id) if batch_id else None

    def last_active_run(self, prefixes: tuple[str, ...]) -> Optional[str]:
        batch_id = self.last_active_batch(prefixes)
        return self.run_id(batch_id) if batch_id else None


def select_pilot_operations(plan: ReviewPlan) -> list[PlanOperation]:
    """Select at most 20 approved screenshots, never any other category."""
    return [operation for operation in plan.operations
            if operation.decision == "approved" and operation.category == "Screenshots"][:PILOT_LIMIT]


def select_screenshot_operations(plan: ReviewPlan) -> list[PlanOperation]:
    """Select every approved screenshot and no operation from another category."""
    selected = [operation for operation in plan.operations
                if operation.decision == "approved" and operation.category == "Screenshots"]
    return sorted(selected, key=lambda operation: (operation.source, operation.destination or ''))


def select_image_operations(plan: ReviewPlan) -> list[PlanOperation]:
    """Select every explicitly approved image and no other category."""
    selected = [operation for operation in plan.operations
                if operation.decision == "approved" and operation.category == "Images"]
    return sorted(selected, key=lambda operation: (operation.source, operation.destination or ''))


def image_destination_uses_dated_layout(operation: PlanOperation,
                                        destination_root: pathlib.Path) -> bool:
    """Reject saved flat image plans after the dated collection policy changed."""
    try:
        relative = pathlib.Path(operation.destination or '').absolute().relative_to(
            destination_root.absolute())
    except ValueError:
        return False
    parts = relative.parts
    if not parts:
        return False
    if parts[0] == 'Travel':
        if len(parts) != 5:
            return False
        year, month = parts[2], parts[3]
    elif parts[0] in {'Camera', 'WhatsApp', 'Other'}:
        if len(parts) != 4:
            return False
        year, month = parts[1], parts[2]
    else:
        return False
    return bool(re.fullmatch(r'\d{4}', year) and
                re.fullmatch(r'\d{4}-\d{2}', month) and month.startswith(year + '-'))


def save_blocked_screenshots(path: pathlib.Path, run_id: str,
                             operations: Iterable[PlanOperation],
                             blocked: Iterable[tuple[str, str]]) -> None:
    """Persist blocked operations locally so they can be validated and retried."""
    by_source = {operation.source: operation for operation in operations}
    items = []
    for source, reason in blocked:
        operation = by_source.get(source)
        if operation:
            items.append({'operation': asdict(operation), 'blocked_reason': reason})
    payload = {'run_id': run_id, 'created_at': _now(), 'operations': items}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def load_blocked_screenshots(path: pathlib.Path) -> list[PlanOperation]:
    """Load a local retry report without relaxing plan-operation validation."""
    payload = json.loads(path.read_text())
    items = payload.get('operations', [])
    if not isinstance(items, list):
        raise ValueError('malformed_blocked_screenshot_report')
    try:
        return [PlanOperation(**item['operation']) for item in items]
    except (KeyError, TypeError) as error:
        raise ValueError('malformed_blocked_screenshot_report') from error


def missing_plan_sources(plan: ReviewPlan) -> list[str]:
    """Return every distinct source path that has disappeared since planning."""
    missing = []
    seen = set()
    for operation in plan.operations:
        if operation.source in seen:
            continue
        seen.add(operation.source)
        if not pathlib.Path(operation.source).exists():
            missing.append(operation.source)
    return missing


class PilotExecutor:
    def __init__(self, config: dict, journal_path: pathlib.Path,
                 *, home: Optional[pathlib.Path] = None,
                 checker_factory: Callable[[dict], SafetyChecker] = SafetyChecker):
        self.config = config
        supplied_home = home or pathlib.Path.home()
        self.home = supplied_home.resolve()
        self.destination_root_lexical = supplied_home.absolute() / "Pictures" / "Screenshots"
        self.destination_root = (self.home / "Pictures" / "Screenshots").resolve()
        self.scan_roots = tuple(self._expand(path) for path in config.get("scan_paths", []))
        self.journal = PilotJournal(journal_path)
        self.checker_factory = checker_factory

    def _expand(self, value: str) -> pathlib.Path:
        if value == "~":
            return self.home
        if value.startswith("~/"):
            return (self.home / value[2:]).resolve()
        return pathlib.Path(value).resolve()

    @staticmethod
    def _inside(path: pathlib.Path, root: pathlib.Path) -> bool:
        try:
            return path.resolve(strict=False).is_relative_to(root)
        except (OSError, ValueError):
            return False

    def _precheck(self, operation: PlanOperation) -> Optional[str]:
        source = pathlib.Path(operation.source)
        destination = pathlib.Path(operation.destination or "")
        if operation.decision != "approved":
            return "operation_not_explicitly_approved"
        if operation.category != "Screenshots":
            return "pilot_allows_screenshots_only"
        if operation.archive_origin in {"company", "company_internal"}:
            return "company_repository_archive"
        if source.is_symlink() or destination.is_symlink():
            return "symlink_rejected"
        if '..' in destination.parts:
            return "destination_path_traversal"
        if not any(self._inside(source, root) for root in self.scan_roots):
            return "source_outside_configured_scan_roots"
        try:
            lexical_parent = destination.absolute().parent.relative_to(
                self.destination_root_lexical)
        except ValueError:
            return "destination_outside_screenshot_tree"
        current_parent = self.destination_root_lexical
        for component in lexical_parent.parts:
            current_parent = current_parent / component
            if current_parent.is_symlink():
                return "destination_parent_symlink"
        try:
            destination.parent.resolve(strict=False).relative_to(
                self.destination_root.resolve())
        except ValueError:
            return "destination_outside_screenshot_tree"
        current = self.destination_root
        for component in lexical_parent.parts:
            current = current / component
            if current.is_symlink():
                return "destination_parent_symlink"
        if not self._inside(destination, self.destination_root):
            return "destination_outside_screenshot_tree"
        return None

    def _validator(self) -> ExecutionValidator:
        validation_config = copy.deepcopy(self.config)
        validation_config.setdefault("safety", {})["planning_only"] = False
        validation_config["safety"]["skip_open_files"] = True
        validation_config["safety"]["allowed_destination_roots"] = [str(self.destination_root_lexical)]
        checker = self.checker_factory(validation_config)
        checker.prepare_open_files()
        return ExecutionValidator(validation_config, checker)

    def validate(self, operation: PlanOperation) -> str:
        reason = self._precheck(operation)
        if reason:
            return f"BLOCKED reason={reason}"
        result = self._validator().validate(operation)
        return result.status if result.safe else f"BLOCKED reason={result.reason}"

    def destination_diagnostics(self, destination: pathlib.Path) -> dict:
        """Expose the validator's read-only destination diagnostics."""
        return self._validator().destination_diagnostics(destination)

    def execute(self, operations: Iterable[PlanOperation], confirmation: str) -> dict:
        return self._execute_batch(list(operations)[:PILOT_LIMIT], confirmation,
                                   "EXECUTE PILOT", PILOT_PREFIX, PILOT_LIMIT)

    def execute_screenshots(self, operations: Iterable[PlanOperation], confirmation: str,
                            progress: Optional[Callable[[dict], None]] = None) -> dict:
        """Execute deterministic, independently recoverable screenshot batches."""
        selected = sorted(list(operations), key=lambda operation: (operation.source,
                                                                    operation.destination or ''))
        if confirmation != "EXECUTE SCREENSHOTS":
            return {"batch_id": None, "executed": 0,
                    "blocked": [("screenshots", "exact_confirmation_required")],
                    "already_organized": [], "batches": [], "unprocessed": []}
        run_id = SCREENSHOT_PREFIX + datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%S-") + uuid.uuid4().hex[:8]
        batch_results = []
        total_executed = 0
        all_blocked = []
        all_already_organized = []
        started = time.monotonic()
        total_batches = (len(selected) + SCREENSHOT_CHUNK_SIZE - 1) // SCREENSHOT_CHUNK_SIZE
        for offset in range(0, len(selected), SCREENSHOT_CHUNK_SIZE):
            number = offset // SCREENSHOT_CHUNK_SIZE + 1
            batch_id = f"{run_id}-batch-{number:04d}"
            result = self._execute_batch(
                selected[offset:offset + SCREENSHOT_CHUNK_SIZE], confirmation,
                "EXECUTE SCREENSHOTS", SCREENSHOT_PREFIX, SCREENSHOT_CHUNK_SIZE,
                batch_id=batch_id, stop_on_block=False)
            batch_results.append(result)
            total_executed += result['executed']
            all_blocked.extend(result['blocked'])
            all_already_organized.extend(result['already_organized'])
            processed = total_executed + len(all_blocked) + len(all_already_organized)
            elapsed = time.monotonic() - started
            remaining = max(0, len(selected) - processed)
            estimate = (elapsed / processed * remaining) if processed else None
            if progress:
                progress({'run_id': run_id, 'batch': number, 'batches': total_batches,
                          'moved': result['executed'], 'blocked': len(result['blocked']),
                          'elapsed': elapsed, 'remaining': remaining, 'estimate': estimate})
        processed_count = sum(result['executed'] + len(result['blocked']) +
                              len(result['already_organized'])
                              for result in batch_results)
        return {"run_id": run_id, "batch_id": batch_results[-1]['batch_id'] if batch_results else None,
                "executed": total_executed, "blocked": all_blocked,
                "already_organized": all_already_organized,
                "batches": batch_results, "unprocessed": selected[processed_count:]}

    def _execute_batch(self, selected: list[PlanOperation], confirmation: str,
                       required_confirmation: str, batch_prefix: str,
                       chunk_size: int, *, batch_id: Optional[str] = None,
                       stop_on_block: bool = False) -> dict:
        if confirmation != required_confirmation:
            return {"batch_id": None, "executed": 0,
                    "blocked": [("screenshots", "exact_confirmation_required")]}
        batch_id = batch_id or (batch_prefix + datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%S-") + uuid.uuid4().hex[:8])
        executed = 0
        blocked = []
        already_organized = []
        for chunk_start in range(0, len(selected), chunk_size):
            for operation in selected[chunk_start:chunk_start + chunk_size]:
                validation = self.validate(operation)  # fresh lsof snapshot and full validator per move
                source = pathlib.Path(operation.source)
                destination = pathlib.Path(operation.destination or "")
                if validation == "BLOCKED reason=collision":
                    if (source.is_file() and destination.is_file() and
                            not source.is_symlink() and not destination.is_symlink()):
                        try:
                            if same_stable_file_content(source, destination):
                                already_organized.append(operation.source)
                                self.journal.append(PilotRecord(
                                    "already_organized_duplicate", batch_id, _now(),
                                    str(source), str(destination), "duplicate_noop",
                                    operation.size, operation.mtime, operation.reason,
                                    "ALREADY_ORGANIZED_DUPLICATE"))
                                continue
                        except OSError:
                            pass
                if validation != "SAFE_TO_EXECUTE":
                    blocked.append((operation.source, validation.removeprefix("BLOCKED reason=")))
                    if stop_on_block:
                        return {"batch_id": batch_id, "executed": executed, "blocked": blocked,
                                "already_organized": already_organized}
                    continue
                prepared = PilotRecord("prepared", batch_id, _now(), str(source), str(destination),
                                       "move", operation.size, operation.mtime, operation.reason, validation)
                self.journal.append(prepared)
                try:
                    missing = []
                    current = destination.parent
                    while current != self.destination_root and not current.exists():
                        missing.append(current)
                        current = current.parent
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    for directory in reversed(missing):
                        self.journal.append(PilotRecord(
                            "created_directory", batch_id, _now(), "", str(directory),
                            "create_directory", 0, 0.0, "Validated category destination parent",
                            "SAFE_TO_CREATE_DIRECTORY"))
                    shutil.move(str(source), str(destination))
                except OSError as error:
                    blocked.append((operation.source, f"filesystem_error_{type(error).__name__}"))
                    if stop_on_block:
                        return {"batch_id": batch_id, "executed": executed, "blocked": blocked,
                                "already_organized": already_organized}
                    continue
                self.journal.append(PilotRecord("executed", batch_id, _now(), str(source),
                                               str(destination), "move", operation.size,
                                               operation.mtime, operation.reason, validation))
                executed += 1
        return {"batch_id": batch_id, "executed": executed, "blocked": blocked,
                "already_organized": already_organized}

    def _batch_state(self, batch_id: str) -> dict[str, list[PilotRecord]]:
        state: dict[str, list[PilotRecord]] = {}
        for record in self.journal.records():
            if record.batch_id == batch_id and record.operation in {'move', 'undo'}:
                state.setdefault(record.source, []).append(record)
        return state

    def _created_directories(self, batch_id: str) -> list[pathlib.Path]:
        records = self.journal.records()
        removed = {record.destination for record in records
                   if record.batch_id == batch_id and record.event == 'removed_directory'}
        created = {record.destination for record in records
                   if record.batch_id == batch_id and record.event == 'created_directory'}
        return sorted((pathlib.Path(value) for value in created - removed),
                      key=lambda value: len(value.parts), reverse=True)

    def verify_run(self, run_id: str) -> dict:
        batch_ids = self.journal.run_batch_ids(run_id)
        if not batch_ids:
            return {"run_id": run_id, "batch_id": None, "consistent": True,
                    "moved": 0, "anomalies": []}
        moved = 0
        anomalies = []
        state = {}
        for related_batch in batch_ids:
            state.update(self._batch_state(related_batch))
        for source_value, records in state.items():
            source = pathlib.Path(source_value)
            destination = pathlib.Path(records[-1].destination)
            events = {record.event for record in records}
            if "undone" in events:
                if not source.exists() or destination.exists():
                    anomalies.append(f"undo_state_mismatch:{source}")
            elif destination.exists() and not source.exists():
                moved += 1
                if "executed" not in events:
                    anomalies.append(f"interrupted_after_move:{source}")
            elif source.exists() and not destination.exists():
                if "executed" in events:
                    anomalies.append(f"executed_but_source_present:{source}")
            else:
                anomalies.append(f"filesystem_state_ambiguous:{source}")
        return {"run_id": run_id, "batch_id": batch_ids[-1], "consistent": not anomalies,
                "moved": moved, "anomalies": anomalies}

    def verify_last(self) -> dict:
        run_id = self.journal.last_run()
        if not run_id:
            return {"run_id": None, "batch_id": None, "consistent": True,
                    "moved": 0, "anomalies": []}
        return self.verify_run(run_id)

    def undo_last(self, prefixes: tuple[str, ...] = CONTROLLED_PREFIXES) -> dict:
        batch_id = self.journal.last_active_batch(prefixes)
        if not batch_id:
            return {"batch_id": None, "undone": 0, "blocked": []}
        return self._undo_batch(batch_id)

    def _undo_batch(self, batch_id: str) -> dict:
        undone = 0
        blocked = []
        state = self._batch_state(batch_id)
        for source_value, records in reversed(list(state.items())):
            if any(record.event == "undone" for record in records):
                continue
            source = pathlib.Path(source_value)
            destination = pathlib.Path(records[-1].destination)
            if source.exists():
                blocked.append((source_value, "original_source_reappeared"))
                continue
            if not destination.exists() or not destination.is_file() or destination.is_symlink():
                blocked.append((source_value, "pilot_destination_missing_or_invalid"))
                continue
            if destination.stat().st_size != records[-1].size:
                blocked.append((source_value, "pilot_destination_changed"))
                continue
            if not self._inside(destination, self.destination_root):
                blocked.append((source_value, "destination_outside_screenshot_tree"))
                continue
            if not any(self._inside(source, root) for root in self.scan_roots):
                blocked.append((source_value, "original_source_outside_configured_scan_roots"))
                continue
            source.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(destination), str(source))
            except OSError as error:
                blocked.append((source_value, f"filesystem_error_{type(error).__name__}"))
                continue
            last = records[-1]
            self.journal.append(PilotRecord("undone", batch_id, _now(), source_value,
                                           str(destination), "undo", last.size, last.mtime,
                                           last.reason, "SAFE_TO_UNDO"))
            undone += 1
        for directory in self._created_directories(batch_id):
            if not self._inside(directory, self.destination_root) or directory == self.destination_root:
                continue
            try:
                directory.rmdir()  # succeeds only for an empty directory
            except (FileNotFoundError, OSError):
                continue
            self.journal.append(PilotRecord(
                "removed_directory", batch_id, _now(), "", str(directory),
                "remove_directory", 0, 0.0, "Undo ROY-created empty directory",
                "SAFE_TO_REMOVE_EMPTY_DIRECTORY"))
        return {"batch_id": batch_id, "undone": undone, "blocked": blocked}

    def run_summary(self, run_id: str) -> dict:
        records = self.journal.records()
        batch_ids = self.journal.run_batch_ids(run_id)
        executed = [record for record in records if record.batch_id in batch_ids
                    and record.event == 'executed']
        duplicates = [record for record in records if record.batch_id in batch_ids
                      and record.event == 'already_organized_duplicate']
        undone = {record.source for record in records if record.batch_id in batch_ids
                  and record.event == 'undone'}
        verification = self.verify_run(run_id)
        run_type = 'Images' if run_id.startswith(IMAGE_PREFIX) else 'Screenshots'
        return {'run_id': run_id, 'type': run_type,
                'timestamp': min((record.timestamp for record in executed + duplicates), default=''),
                'moved': len(executed), 'already_organized': len(duplicates),
                'batches': len(batch_ids),
                'verified': verification['consistent'],
                'undo_available': any(record.source not in undone for record in executed)}

    def screenshot_run_summary(self, run_id: str) -> dict:
        return self.run_summary(run_id)

    def undo_screenshot_run(self, run_id: Optional[str] = None) -> dict:
        run_id = run_id or self.journal.last_active_run((SCREENSHOT_PREFIX,))
        if not run_id:
            return {'run_id': None, 'undone': 0, 'blocked': [], 'batches': []}
        results = []
        undone = 0
        blocked = []
        for batch_id in reversed(self.journal.run_batch_ids(run_id)):
            active = self.journal.last_active_batch((batch_id,))
            if not active:
                continue
            result = self._undo_batch(batch_id)
            results.append(result)
            undone += result['undone']
            blocked.extend(result['blocked'])
            if result['blocked']:
                break
        return {'run_id': run_id, 'undone': undone, 'blocked': blocked,
                'batches': results}

    def history(self) -> list[dict]:
        run_ids = []
        for record in self.journal.records():
            run_id = self.journal.run_id(record.batch_id)
            if run_id.startswith((SCREENSHOT_PREFIX, IMAGE_PREFIX)) and run_id not in run_ids:
                run_ids.append(run_id)
        return [self.run_summary(run_id) for run_id in reversed(run_ids)]


class ImageExecutor(PilotExecutor):
    """Controlled image only executor that reuses the validated move engine."""

    def __init__(self, config: dict, journal_path: pathlib.Path,
                 *, home: Optional[pathlib.Path] = None,
                 checker_factory: Callable[[dict], SafetyChecker] = SafetyChecker):
        super().__init__(config, journal_path, home=home, checker_factory=checker_factory)
        configured = config.get('destinations', {}).get('Images', '~/Pictures/Organized')
        if configured == '~':
            lexical = self.home
        elif str(configured).startswith('~/'):
            lexical = self.home / str(configured)[2:]
        else:
            lexical = pathlib.Path(configured).absolute()
        self.destination_root_lexical = lexical.absolute()
        self.destination_root = lexical.resolve(strict=False)

    def _precheck(self, operation: PlanOperation) -> Optional[str]:
        source = pathlib.Path(operation.source)
        destination = pathlib.Path(operation.destination or '')
        if operation.decision != 'approved':
            return 'operation_not_explicitly_approved'
        if operation.category != 'Images':
            return 'image_mode_allows_images_only'
        if operation.archive_origin in {'company', 'company_internal'}:
            return 'company_repository_archive'
        if source.is_symlink() or destination.is_symlink():
            return 'symlink_rejected'
        if '..' in destination.parts:
            return 'destination_path_traversal'
        if not any(self._inside(source, root) for root in self.scan_roots):
            return 'source_outside_configured_scan_roots'
        try:
            lexical_parent = destination.absolute().parent.relative_to(
                self.destination_root_lexical)
        except ValueError:
            return 'destination_outside_image_tree'
        current = self.destination_root_lexical
        for component in lexical_parent.parts:
            current = current / component
            if current.is_symlink():
                return 'destination_parent_symlink'
        try:
            destination.parent.resolve(strict=False).relative_to(
                self.destination_root.resolve(strict=False))
        except ValueError:
            return 'destination_outside_image_tree'
        if not self._inside(destination, self.destination_root):
            return 'destination_outside_image_tree'
        return None

    def execute_images(self, operations: Iterable[PlanOperation], confirmation: str,
                       progress: Optional[Callable[[dict], None]] = None) -> dict:
        selected = sorted(list(operations), key=lambda operation: (
            operation.source, operation.destination or ''))
        if confirmation != 'EXECUTE IMAGES':
            return {'run_id': None, 'batch_id': None, 'executed': 0,
                    'blocked': [('images', 'exact_confirmation_required')],
                    'already_organized': [], 'batches': [], 'unprocessed': []}
        run_id = IMAGE_PREFIX + datetime.now(timezone.utc).strftime(
            '%Y%m%dT%H%M%S-') + uuid.uuid4().hex[:8]
        batches = []
        executed = 0
        blocked = []
        duplicates = []
        started = time.monotonic()
        total_batches = (len(selected) + SCREENSHOT_CHUNK_SIZE - 1) // SCREENSHOT_CHUNK_SIZE
        for offset in range(0, len(selected), SCREENSHOT_CHUNK_SIZE):
            number = offset // SCREENSHOT_CHUNK_SIZE + 1
            result = self._execute_batch(
                selected[offset:offset + SCREENSHOT_CHUNK_SIZE], confirmation,
                'EXECUTE IMAGES', IMAGE_PREFIX, SCREENSHOT_CHUNK_SIZE,
                batch_id=f'{run_id}-batch-{number:04d}', stop_on_block=False)
            batches.append(result)
            executed += result['executed']
            blocked.extend(result['blocked'])
            duplicates.extend(result['already_organized'])
            processed = executed + len(blocked) + len(duplicates)
            elapsed = time.monotonic() - started
            remaining = max(0, len(selected) - processed)
            estimate = elapsed / processed * remaining if processed else None
            if progress:
                progress({'run_id': run_id, 'batch': number, 'batches': total_batches,
                          'moved': result['executed'], 'blocked': len(result['blocked']),
                          'elapsed': elapsed, 'remaining': remaining, 'estimate': estimate})
        processed = sum(item['executed'] + len(item['blocked']) +
                        len(item['already_organized']) for item in batches)
        return {'run_id': run_id, 'batch_id': batches[-1]['batch_id'] if batches else None,
                'executed': executed, 'blocked': blocked,
                'already_organized': duplicates, 'batches': batches,
                'unprocessed': selected[processed:]}

    def undo_image_run(self, run_id: Optional[str] = None) -> dict:
        run_id = run_id or self.journal.last_active_run((IMAGE_PREFIX,))
        return self.undo_screenshot_run(run_id) if run_id else {
            'run_id': None, 'undone': 0, 'blocked': [], 'batches': []}


PILOT_BLOCK_EXPLANATIONS = {
    'destination_outside_screenshot_tree': (
        'Destination is outside the approved screenshot tree.',
        'Choose a destination beneath ~/Pictures/Screenshots/.'),
    'destination_outside_image_tree': (
        'Destination is outside the approved image tree.',
        'Choose a destination beneath the configured Images destination.'),
    'destination_outside_allowed_roots': (
        'Destination is outside configured destination roots.',
        'Choose an approved destination root.'),
    'outside_allowed': (
        'Destination is outside configured destination roots.',
        'Choose an approved destination root.'),
    'approved_destination_root_missing_or_invalid': (
        'The approved destination root is missing, invalid, or a symlink.',
        'Create or approve the destination root manually, then validate again.'),
    'destination_parent_symlink': (
        'A destination parent is a symlink.',
        'Choose a real directory beneath the approved destination root.'),
    'destination_parent_protected': (
        'A destination parent is protected.',
        'Choose a non-protected destination beneath an approved root.'),
    'destination_parent_permission_denied': (
        'The missing destination folder cannot be created with current permissions.',
        'Check ownership and permissions; do not use sudo.'),
    'destination_path_traversal': (
        'The destination contains path traversal.',
        'Choose a normalized destination beneath an approved root.'),
}


def format_pilot_block(operation: Optional[PlanOperation], reason: str) -> str:
    destination = operation.destination if operation else '(pilot)'
    explanation, suggestion = PILOT_BLOCK_EXPLANATIONS.get(
        reason, (reason.replace('_', ' ').capitalize() + '.', 'Review the operation and run validation again.'))
    return (f"Destination\n\n{destination}\n\nReason\n\n{explanation}\n\n"
            f"Suggestion\n\n{suggestion}")


def pilot_summary(operations: Iterable[PlanOperation], home: Optional[pathlib.Path] = None) -> str:
    selected = list(operations)
    roots = sorted({source_folder(pathlib.Path(operation.source), home) for operation in selected})
    total = sum(operation.size for operation in selected)
    root = (home or pathlib.Path.home()) / "Pictures" / "Screenshots"
    return ("REAL FILE PILOT\n\n"
            f"Files selected: {len(selected)} (maximum 20)\n"
            f"Total size: {total:,} bytes\n"
            f"Source roots represented: {', '.join(roots) or 'None'}\n"
            f"Destination root:\n{root}/\n\n"
            "Deletes: 0\nOverwrites: 0\nUndo logging: ENABLED")


def screenshot_summary(operations: Iterable[PlanOperation], home: Optional[pathlib.Path] = None) -> str:
    selected = list(operations)
    counts = {name: 0 for name in DEFAULT_SOURCE_NAMES}
    for operation in selected:
        folder = source_folder(pathlib.Path(operation.source), home)
        counts[folder] = counts.get(folder, 0) + 1
    total = sum(operation.size for operation in selected)
    root = (home or pathlib.Path.home()) / "Pictures" / "Screenshots"
    source_lines = '\n'.join(f"{name:<12}{counts[name]:>7,}" for name in DEFAULT_SOURCE_NAMES)
    return ("REAL SCREENSHOT ORGANIZATION\n\n"
            f"Screenshots approved: {len(selected):,}\n\n{source_lines}\n\n"
            f"Total size: {total:,} bytes\n\nDestination:\n\n"
            "Pictures/\n└── Screenshots/\n"
            f"({root}/)\n\nBatch size: {SCREENSHOT_CHUNK_SIZE}\n"
            "Deletes: 0\nOverwrites: 0\nUndo logging: ENABLED")


def image_summary(operations: Iterable[PlanOperation], config: dict,
                  home: Optional[pathlib.Path] = None) -> str:
    selected = list(operations)
    counts = {name: 0 for name in DEFAULT_SOURCE_NAMES}
    for operation in selected:
        folder = source_folder(pathlib.Path(operation.source), home)
        counts[folder] = counts.get(folder, 0) + 1
    total = sum(operation.size for operation in selected)
    configured = config.get('destinations', {}).get('Images', '~/Pictures/Organized')
    root = pathlib.Path(os.path.expanduser(str(configured)))
    source_lines = '\n'.join(f'{name:<12}{counts[name]:>7,}' for name in DEFAULT_SOURCE_NAMES)
    return ('REAL IMAGE ORGANIZATION\n\n'
            f'Images approved: {len(selected):,}\n\n{source_lines}\n\n'
            f'Total size: {total:,} bytes\n\nDestination root:\n{root}/\n\n'
            f'Batch size: {SCREENSHOT_CHUNK_SIZE}\nDeletes: 0\nOverwrites: 0\n'
            'Undo logging: ENABLED')
