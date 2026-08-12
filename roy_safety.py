"""
ROY Organizer - Safety Module
Core safety checks and path validation.
"""
import os
import pathlib
import subprocess
from typing import List, Set, Optional
from dataclasses import dataclass


@dataclass
class SafetyCheckResult:
    """Result of a safety check."""
    safe: bool
    reason: str
    skip_reason: Optional[str] = None


class SafetyChecker:
    """Validates paths and operations for safety."""
    
    def __init__(self, config: dict):
        self.config = config
        self.safety_config = config.get('safety', {})
        self.protected_paths = self._expand_paths(
            self.safety_config.get('protected_paths', [])
        )
        self.work_terms = set(
            term.lower() for term in 
            config.get('classification', {}).get('work_terms', [])
        )
        self.skip_hidden = self.safety_config.get('skip_hidden', True)
        self.skip_git_repos = self.safety_config.get('skip_git_repos', True)
    
    def _expand_paths(self, paths: List[str]) -> List[pathlib.Path]:
        """Expand user paths and return as Path objects."""
        expanded = []
        for p in paths:
            try:
                expanded.append(pathlib.Path(os.path.expanduser(p)).resolve())
            except Exception:
                pass
        return expanded
    
    def is_protected(self, path: pathlib.Path) -> SafetyCheckResult:
        """Check if a path is in a protected system location."""
        try:
            resolved = path.resolve()
        except Exception:
            return SafetyCheckResult(False, "Cannot resolve path", "unresolvable")
        
        for protected in self.protected_paths:
            try:
                if resolved.is_relative_to(protected):
                    return SafetyCheckResult(
                        False, 
                        f"Path is under protected location: {protected}",
                        "protected_path"
                    )
            except Exception:
                # If relative_to fails, check string containment
                if str(protected) in str(resolved):
                    return SafetyCheckResult(
                        False,
                        f"Path contains protected location: {protected}",
                        "protected_path"
                    )
        
        return SafetyCheckResult(True, "Path is not protected")
    
    def is_hidden(self, path: pathlib.Path) -> bool:
        """Check if a file/directory is hidden (any component starts with .)."""
        # Check all path components
        for part in path.parts:
            if part.startswith('.'):
                return True
        return False
    
    def is_in_git_repo(self, path: pathlib.Path) -> bool:
        """Check if a path is inside a Git repository."""
        if not self.skip_git_repos:
            return False
        
        try:
            current = path if path.is_dir() else path.parent
            for parent in [current] + list(current.parents):
                # A .git directory in the user's home must not make every
                # normal file below it look like part of a Git repository.
                if parent == pathlib.Path.home():
                    break
                if (parent / '.git').exists():
                    return True
        except Exception:
            pass
        return False
    
    def has_work_terms(self, path: pathlib.Path) -> bool:
        """Check if path contains work-related terms."""
        path_str = str(path).lower()
        for term in self.work_terms:
            if term in path_str:
                return True
        return False
    
    def is_open_by_app(self, path: pathlib.Path) -> bool:
        """Check if a file is currently open by an application (macOS)."""
        if not self.safety_config.get('skip_open_files', True):
            return False
        
        try:
            # Use lsof to check if file is open
            result = subprocess.run(
                ['lsof', str(path)],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0 and result.stdout.strip()
        except Exception:
            # If we can't check, assume it's not open (conservative)
            return False
    
    def check_source(self, path: pathlib.Path) -> SafetyCheckResult:
        """Comprehensive safety check for a source file."""
        # Check if protected
        protected_result = self.is_protected(path)
        if not protected_result.safe:
            return protected_result
        
        # Check if hidden
        if self.skip_hidden and self.is_hidden(path):
            return SafetyCheckResult(
                False, "Hidden file", "hidden_file"
            )
        
        # Check if in Git repo
        if self.is_in_git_repo(path):
            return SafetyCheckResult(
                False, "File is in a Git repository", "git_repo"
            )
        
        # Check for work terms
        if self.has_work_terms(path):
            return SafetyCheckResult(
                False, "Path contains work-related terms", "work_data"
            )
        
        # Check if open by app
        if self.is_open_by_app(path):
            return SafetyCheckResult(
                False, "File is currently open by an application", "open_file"
            )
        
        return SafetyCheckResult(True, "Safe to process")
    
    def check_destination(self, dest: pathlib.Path, source: pathlib.Path) -> SafetyCheckResult:
        """Check if destination is safe."""
        # Don't overwrite existing files
        if dest.exists():
            return SafetyCheckResult(
                False, f"Destination already exists: {dest}", "collision"
            )
        
        # Check if destination is protected
        protected_result = self.is_protected(dest)
        if not protected_result.safe:
            return protected_result
        
        # Ensure destination is within allowed target directories
        allowed_roots = [
            pathlib.Path.home() / 'Desktop',
            pathlib.Path.home() / 'Downloads',
            pathlib.Path.home() / 'Documents',
            pathlib.Path.home() / 'Pictures',
            pathlib.Path.home() / 'Movies',
        ]
        
        try:
            dest_resolved = dest.resolve()
            allowed = any(
                dest_resolved.is_relative_to(root.resolve()) 
                for root in allowed_roots
            )
            if not allowed:
                return SafetyCheckResult(
                    False, 
                    f"Destination outside allowed directories: {dest}",
                    "outside_allowed"
                )
        except Exception:
            return SafetyCheckResult(
                False, "Cannot validate destination path", "invalid_dest"
            )
        
        return SafetyCheckResult(True, "Destination is safe")


def get_safety_checker(config: dict) -> SafetyChecker:
    """Factory function to create a SafetyChecker."""
    return SafetyChecker(config)
