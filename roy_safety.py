"""
ROY Organizer - Safety Module
Core safety checks and path validation.
"""
import os
import pathlib
import subprocess
from typing import List, Set, Optional
from dataclasses import dataclass
from roy_inspect import inspect_kubeconfig


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
        self.open_files: Optional[Set[pathlib.Path]] = None
        self.open_file_state = "NOT_CHECKED"
        self.open_file_error: Optional[str] = None
        self.project_markers = {
            '.git', '.github', '.gitlab', 'package.json', 'pyproject.toml',
            'requirements.txt', 'Cargo.toml', 'go.mod', 'pom.xml', 'build.gradle',
            'Dockerfile', 'docker-compose.yml', 'Makefile', 'Gemfile',
            'composer.json', 'CMakeLists.txt', 'Package.swift', 'gradlew', 'mvnw'
        }
        self._project_cache = {}
        home = pathlib.Path.home()
        self.developer_roots = self._expand_paths([
            '~/.ssh', '~/.aws', '~/.kube', '~/.azure', '~/.config/gcloud',
            '~/.terraform.d', '~/.docker', '~/.vscode', '~/.config/git',
            '~/.oh-my-zsh', '~/.nvm', '~/.cargo', '~/.config/mise', '~/.asdf',
            '~/.codex', '~/.claude', '~/.ollama', '~/.config/opencode',
            '~/.continue', '~/.cursor', '~/Library', '/opt/homebrew', '/usr/local'
        ])
        self.developer_files = {
            '.zshrc', '.zprofile', '.zlogin', '.zlogout', '.zshenv', '.zsh_history',
            '.gitconfig', '.git-credentials'
        }
    
    def _expand_paths(self, paths: List[str]) -> List[pathlib.Path]:
        """Expand user paths and return as Path objects."""
        expanded = []
        for p in paths:
            try:
                if p == '~':
                    value = pathlib.Path.home()
                elif p.startswith('~/'):
                    value = pathlib.Path.home() / p[2:]
                else:
                    value = pathlib.Path(p)
                expanded.append(value.resolve())
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

    def is_in_software_project(self, path: pathlib.Path) -> bool:
        """Return True when a path is below a directory with a project marker."""
        try:
            current = path if path.is_dir() else path.parent
            visited = []
            for parent in [current] + list(current.parents):
                if parent == pathlib.Path.home():
                    break
                if parent in self._project_cache:
                    result = self._project_cache[parent]
                    for item in visited:
                        self._project_cache[item] = result
                    return result
                visited.append(parent)
                if any((parent / marker).exists() for marker in self.project_markers):
                    for item in visited:
                        self._project_cache[item] = True
                    return True
                try:
                    if any(parent.glob('*.tf')):
                        for item in visited:
                            self._project_cache[item] = True
                        return True
                except OSError:
                    pass
            for item in visited:
                self._project_cache[item] = False
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

    def is_developer_config(self, path: pathlib.Path) -> bool:
        """Explicitly protect developer configuration independent of hidden rules."""
        try:
            resolved = path.resolve()
            if any(resolved.is_relative_to(root) for root in self.developer_roots):
                return True
        except (OSError, ValueError):
            return True
        name = path.name.lower()
        if name in {value.lower() for value in self.developer_files}:
            return True
        if name.startswith('.zcompdump') or name.endswith('.code-workspace'):
            return True
        if '.vscode' in path.parts or name in {'tasks.json', 'launch.json'} and '.vscode' in path.parts:
            return True
        return False

    def is_company_security_path(self, path: pathlib.Path) -> bool:
        terms = ('workspace one', 'airwatch', 'crowdstrike', 'falcon',
                 'globalprotect', 'paloaltonetworks', '/mdm/', 'security profiles')
        value = str(path).lower()
        return any(term in value for term in terms)
    
    def prepare_open_files(self) -> None:
        """Snapshot open files once for the whole scan using lsof field output."""
        if not self.safety_config.get('skip_open_files', True):
            self.open_files = set()
            self.open_file_state = "DISABLED"
            return
        try:
            result = subprocess.run(
                ['lsof', '-Fn'],
                capture_output=True,
                text=True,
                timeout=self.safety_config.get('lsof_timeout', 30)
            )
            self.open_files = {
                pathlib.Path(line[1:]).resolve()
                for line in result.stdout.splitlines()
                if line.startswith('n/')
            }
            if result.returncode != 0:
                raise RuntimeError(f"lsof exited with status {result.returncode}")
            malformed = result.stdout.strip() and not any(
                line.startswith(('p', 'f', 'n')) for line in result.stdout.splitlines())
            if malformed:
                raise ValueError("malformed lsof output")
            self.open_file_state = "KNOWN"
            self.open_file_error = None
        except (OSError, subprocess.TimeoutExpired, RuntimeError, ValueError) as error:
            self.open_files = None
            self.open_file_state = "OPEN_FILE_STATE_UNKNOWN"
            self.open_file_error = type(error).__name__

    def is_open_by_app(self, path: pathlib.Path) -> bool:
        """Check a scan-level snapshot rather than spawning once per file."""
        if not self.safety_config.get('skip_open_files', True):
            return False
        if self.open_files is None:
            if self.open_file_state == "NOT_CHECKED":
                self.prepare_open_files()
            if self.open_file_state == "OPEN_FILE_STATE_UNKNOWN":
                return False
        try:
            return path.resolve() in self.open_files
        except Exception:
            return False
    
    def check_source(self, path: pathlib.Path) -> SafetyCheckResult:
        """Comprehensive safety check for a source file."""
        # Check if protected
        protected_result = self.is_protected(path)
        if not protected_result.safe:
            return protected_result

        if self.is_company_security_path(path):
            return SafetyCheckResult(False, "Protected company security tooling", "company_security")

        if self.is_developer_config(path):
            return SafetyCheckResult(False, "Protected developer configuration", "developer_config")

        # Check if hidden
        if self.skip_hidden and self.is_hidden(path):
            return SafetyCheckResult(
                False, "Hidden file", "hidden_file"
            )
        
        # Protect complete software projects, not only their Git metadata.
        if self.is_in_software_project(path):
            return SafetyCheckResult(
                False, "File is inside a software project", "software_project"
            )

        if inspect_kubeconfig(path):
            return SafetyCheckResult(False, "Protected: Kubernetes configuration", "kubernetes_config")
        
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
        configured_roots = self.safety_config.get('allowed_destination_roots')
        allowed_roots = self._expand_paths(configured_roots) if configured_roots else [
            pathlib.Path.home() / 'Desktop', pathlib.Path.home() / 'Downloads',
            pathlib.Path.home() / 'Documents', pathlib.Path.home() / 'Pictures',
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
