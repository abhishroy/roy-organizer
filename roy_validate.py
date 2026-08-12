"""Fail-closed validation for future execution. Does not move files."""
import os
import pathlib
import stat
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

    @staticmethod
    def _configured_destination_roots(values) -> list[pathlib.Path]:
        """Expand roots without resolving away a symlink at the root itself."""
        return [pathlib.Path(os.path.expanduser(str(value))).absolute() for value in values]

    @staticmethod
    def _mode_allows_directory_creation(path: pathlib.Path) -> bool:
        """Check effective Unix mode permissions without trusting sandboxed os.access."""
        try:
            metadata = path.stat()
        except OSError:
            return False
        if not stat.S_ISDIR(metadata.st_mode):
            return False
        if os.geteuid() == metadata.st_uid:
            required = stat.S_IWUSR | stat.S_IXUSR
        elif metadata.st_gid in os.getgroups():
            required = stat.S_IWGRP | stat.S_IXGRP
        else:
            required = stat.S_IWOTH | stat.S_IXOTH
        return metadata.st_mode & required == required

    def destination_diagnostics(self, destination: pathlib.Path) -> dict:
        """Return read-only destination facts without exposing file contents."""
        configured = self.safety.safety_config.get('allowed_destination_roots', [])
        roots = self._configured_destination_roots(configured)
        resolved_destination = destination.resolve(strict=False)
        root = next((candidate for candidate in roots
                     if resolved_destination.is_relative_to(candidate.resolve(strict=False))), None)
        nearest = destination.parent
        while not nearest.exists() and nearest != nearest.parent:
            nearest = nearest.parent
        return {
            'expanded_destination_root': str(root) if root else None,
            'resolved_destination_root': str(root.resolve(strict=False)) if root else None,
            'root_exists': root.exists() if root else False,
            'root_is_dir': root.is_dir() if root else False,
            'root_is_symlink': root.is_symlink() if root else False,
            'root_os_access_writable': os.access(root, os.W_OK) if root else False,
            'nearest_existing_parent': str(nearest),
            'nearest_parent_os_access_writable': os.access(nearest, os.W_OK),
            'nearest_parent_mode_creatable': self._mode_allows_directory_creation(nearest),
            'under_approved_root': root is not None,
        }

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
        parent_result = self.validate_destination_parent(destination)
        if not parent_result.safe:
            return parent_result
        destination_result = self.safety.check_destination(destination, source)
        if not destination_result.safe:
            return self.blocked(destination_result.skip_reason or 'destination_blocked')
        return ValidationResult('SAFE_TO_EXECUTE')

    def validate_destination_parent(self, destination: pathlib.Path) -> ValidationResult:
        """Distinguish missing-but-creatable parents from unsafe parent paths."""
        if '..' in destination.parts:
            return self.blocked('destination_path_traversal')
        configured = self.safety.safety_config.get('allowed_destination_roots', [])
        roots = self._configured_destination_roots(configured)
        try:
            resolved = destination.resolve(strict=False)
            root = next((candidate for candidate in roots
                         if resolved.is_relative_to(candidate.resolve())), None)
        except (OSError, ValueError):
            return self.blocked('destination_parent_unresolvable')
        if root is None:
            return self.blocked('outside_allowed')
        if not root.exists() or not root.is_dir() or root.is_symlink():
            return self.blocked('approved_destination_root_missing_or_invalid')
        try:
            relative_parent = destination.parent.resolve(strict=False).relative_to(root.resolve())
        except ValueError:
            return self.blocked('outside_allowed')
        current = root
        for component in relative_parent.parts:
            current = current / component
            if current.is_symlink():
                return self.blocked('destination_parent_symlink')
            if current.exists() and not current.is_dir():
                return self.blocked('destination_parent_not_directory')
            protected = self.safety.is_protected(current)
            if not protected.safe or self.safety.is_developer_config(current):
                return self.blocked('destination_parent_protected')
        existing_parent = destination.parent
        while not existing_parent.exists() and existing_parent != root:
            existing_parent = existing_parent.parent
        if not self._mode_allows_directory_creation(existing_parent):
            return self.blocked('destination_parent_permission_denied')
        return ValidationResult('SAFE_TO_EXECUTE')
