"""Explicitly gated, screenshot-only real execution pilot."""
from __future__ import annotations

import copy
import json
import os
import pathlib
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

from roy_plan import PlanOperation, ReviewPlan, source_folder
from roy_safety import SafetyChecker
from roy_validate import ExecutionValidator


PILOT_LIMIT = 20
PILOT_PREFIX = "pilot-"


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

    def last_batch(self) -> Optional[str]:
        for record in reversed(self.records()):
            if record.batch_id.startswith(PILOT_PREFIX):
                return record.batch_id
        return None


def select_pilot_operations(plan: ReviewPlan) -> list[PlanOperation]:
    """Select at most 20 approved screenshots, never any other category."""
    return [operation for operation in plan.operations
            if operation.decision == "approved" and operation.category == "Screenshots"][:PILOT_LIMIT]


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
        selected = list(operations)[:PILOT_LIMIT]
        if confirmation != "EXECUTE PILOT":
            return {"batch_id": None, "executed": 0, "blocked": [("pilot", "exact_confirmation_required")]}
        batch_id = PILOT_PREFIX + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S-") + uuid.uuid4().hex[:8]
        executed = 0
        blocked = []
        for operation in selected:
            validation = self.validate(operation)  # fresh lsof snapshot and full validator per move
            if validation != "SAFE_TO_EXECUTE":
                blocked.append((operation.source, validation.removeprefix("BLOCKED reason=")))
                continue
            source = pathlib.Path(operation.source)
            destination = pathlib.Path(operation.destination or "")
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
                        "create_directory", 0, 0.0, "Validated pilot destination parent",
                        "SAFE_TO_CREATE_DIRECTORY"))
                shutil.move(str(source), str(destination))
            except OSError as error:
                blocked.append((operation.source, f"filesystem_error_{type(error).__name__}"))
                continue
            self.journal.append(PilotRecord("executed", batch_id, _now(), str(source),
                                           str(destination), "move", operation.size,
                                           operation.mtime, operation.reason, validation))
            executed += 1
        return {"batch_id": batch_id, "executed": executed, "blocked": blocked}

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

    def verify_last(self) -> dict:
        batch_id = self.journal.last_batch()
        if not batch_id:
            return {"batch_id": None, "consistent": True, "moved": 0, "anomalies": []}
        moved = 0
        anomalies = []
        for source_value, records in self._batch_state(batch_id).items():
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
        return {"batch_id": batch_id, "consistent": not anomalies,
                "moved": moved, "anomalies": anomalies}

    def undo_last(self) -> dict:
        batch_id = self.journal.last_batch()
        if not batch_id:
            return {"batch_id": None, "undone": 0, "blocked": []}
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


PILOT_BLOCK_EXPLANATIONS = {
    'destination_outside_screenshot_tree': (
        'Destination is outside the approved screenshot tree.',
        'Choose a destination beneath ~/Pictures/Screenshots/.'),
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
