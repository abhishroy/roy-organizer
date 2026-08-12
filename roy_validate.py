"""Fail-closed validation for future execution. Does not move files."""
import os
import pathlib
from dataclasses import dataclass

from roy_plan import PlanOperation
from roy_safety import SafetyChecker


@dataclass
class ValidationResult:
    status: str
    reason: str = ''

    @property
    def safe(self) -> bool:
        return self.status == 'SAFE_TO_EXECUTE'


class ExecutionValidator:
    """Validate a previously approved operation immediately before a future move."""

    def __init__(self, config: dict, safety_checker: SafetyChecker = None):
        self.config = config
        self.safety = safety_checker or SafetyChecker(config)

    def blocked(self, reason: str) -> ValidationResult:
        return ValidationResult('BLOCKED', reason)

    def validate(self, operation: PlanOperation) -> ValidationResult:
        if self.config.get('safety', {}).get('planning_only', True):
            return self.blocked('planning_only')
        if operation.decision != 'approved':
            return self.blocked('operation_not_explicitly_approved')
        if operation.archive_origin in {'company', 'company_internal'}:
            return self.blocked('company_repository_archive')
        if self.config.get('machine_profile') not in {
            'personal', 'developer', 'company_managed', 'developer_company_managed'}:
            return self.blocked('unsupported_machine_profile')
        if self.safety.open_file_state != 'KNOWN':
            return self.blocked('open_file_state_unknown')
        source = pathlib.Path(operation.source)
        destination = pathlib.Path(operation.destination) if operation.destination else None
        if not source.exists() or not source.is_file():
            return self.blocked('source_missing')
        stat = source.stat()
        if stat.st_size != operation.size or abs(stat.st_mtime - operation.mtime) > 0.000001:
            return self.blocked('source_changed_review_again')
        source_result = self.safety.check_source(source)
        if not source_result.safe:
            return self.blocked(source_result.skip_reason or 'source_protected')
        if destination is None:
            return self.blocked('destination_missing')
        destination_result = self.safety.check_destination(destination, source)
        if not destination_result.safe:
            return self.blocked(destination_result.skip_reason or 'destination_blocked')
        parent = destination.parent
        existing_parent = parent
        while not existing_parent.exists() and existing_parent != existing_parent.parent:
            existing_parent = existing_parent.parent
        if not existing_parent.is_dir() or not os.access(existing_parent, os.W_OK):
            return self.blocked('destination_parent_not_creatable')
        return ValidationResult('SAFE_TO_EXECUTE')
