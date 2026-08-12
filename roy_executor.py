"""Sandbox-only executor and undo engine for Early Preview."""
import json
import pathlib
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from roy_plan import PlanOperation
from roy_safety import SafetyChecker
from roy_validate import ExecutionValidator


@dataclass
class ExecutionRecord:
    batch_id: str
    timestamp: str
    source: str
    destination: str
    operation: str
    size: int
    mtime: float
    reason: str
    validation_result: str


class SandboxExecutor:
    def __init__(self, sandbox_root: pathlib.Path, log_path: pathlib.Path):
        self.root = sandbox_root.resolve()
        temp_root = pathlib.Path('/tmp').resolve()
        if not self.root.is_relative_to(temp_root):
            raise ValueError('Early Preview execution is restricted to /tmp')
        self.log_path = pathlib.Path(log_path)

    def _inside(self, path: pathlib.Path) -> bool:
        try:
            return path.resolve().is_relative_to(self.root)
        except OSError:
            return False

    def _validator(self) -> ExecutionValidator:
        config = {'machine_profile': 'personal', 'classification': {'work_terms': []},
                  'safety': {'planning_only': False, 'protected_paths': [],
                             'skip_hidden': True, 'skip_git_repos': True,
                             'skip_open_files': True,
                             'allowed_destination_roots': [str(self.root)]}}
        checker = SafetyChecker(config)
        checker.open_files = set(); checker.open_file_state = 'KNOWN'
        return ExecutionValidator(config, checker)

    def execute(self, operation: PlanOperation, batch_id: str,
                validator: ExecutionValidator = None) -> str:
        source = pathlib.Path(operation.source); destination = pathlib.Path(operation.destination or '')
        if not self._inside(source) or not self._inside(destination):
            return 'BLOCKED reason=outside_sandbox'
        result = (validator or self._validator()).validate(operation)
        if not result.safe:
            return f'BLOCKED reason={result.reason}'
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
        except OSError as error:
            return f'BLOCKED reason=filesystem_error_{type(error).__name__}'
        record = ExecutionRecord(batch_id, datetime.now(timezone.utc).isoformat(),
                                 str(source), str(destination), 'move', operation.size,
                                 operation.mtime, operation.reason, result.status)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open('a') as handle:
            handle.write(json.dumps(asdict(record)) + '\n')
        return 'EXECUTED'

    def records(self) -> list[ExecutionRecord]:
        if not self.log_path.exists():
            return []
        records = []
        for line in self.log_path.read_text().splitlines():
            try:
                records.append(ExecutionRecord(**json.loads(line)))
            except (json.JSONDecodeError, TypeError):
                raise ValueError('corrupted transaction log')
        return records

    def undo(self, batch_id: str) -> int:
        records = [record for record in self.records() if record.batch_id == batch_id]
        restored = 0
        for record in reversed(records):
            source = pathlib.Path(record.source); destination = pathlib.Path(record.destination)
            if not self._inside(source) or not self._inside(destination):
                continue
            if not destination.exists() or source.exists():
                continue
            source.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(destination), str(source)); restored += 1
        return restored
