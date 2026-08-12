"""
ROY Organizer - Scanner Module
Scans directories and builds file inventory.
"""
import os
import pathlib
import hashlib
import json
from datetime import datetime
from typing import List, Dict, Optional, Iterator
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from roy_classify import FileInfo, Classifier, create_classifier, Category
from roy_safety import SafetyChecker, get_safety_checker, SafetyCheckResult
from roy_inspect import inspect_zip


@dataclass
class ScanStats:
    """Statistics from a scan."""
    total_files: int = 0
    total_size: int = 0
    by_category: Dict[str, int] = None
    by_folder: Dict[str, int] = None
    largest_files: List[FileInfo] = None
    oldest_files: List[FileInfo] = None
    duplicates: List[tuple] = None
    screenshots: int = 0
    archives: int = 0
    installers: int = 0
    videos: int = 0
    pdfs: int = 0
    code_folders: int = 0
    unclassified: int = 0
    skipped: int = 0
    needs_review: int = 0
    work_review: int = 0
    protected_by_reason: Dict[str, int] = None
    open_file_state: str = "NOT_CHECKED"
    open_file_error: Optional[str] = None
    
    def __post_init__(self):
        if self.by_category is None:
            self.by_category = {}
        if self.by_folder is None:
            self.by_folder = {}
        if self.largest_files is None:
            self.largest_files = []
        if self.oldest_files is None:
            self.oldest_files = []
        if self.duplicates is None:
            self.duplicates = []
        if self.protected_by_reason is None:
            self.protected_by_reason = {}


class Scanner:
    """Scans directories and classifies files."""
    
    def __init__(self, config: dict):
        self.config = config
        self.scan_paths = [
            pathlib.Path(os.path.expanduser(p)) 
            for p in config.get('scan_paths', [])
        ]
        self.classifier = create_classifier(config)
        self.safety_checker = get_safety_checker(config)
        self.duplicates_config = config.get('duplicates', {})
        self.min_duplicate_size = self.duplicates_config.get('min_size', 1024)
        self.use_hash = self.duplicates_config.get('use_hash', True)
        
        # For duplicate detection
        self.size_map: Dict[int, List[FileInfo]] = {}
        self.hash_map: Dict[str, FileInfo] = {}
    
    def should_scan(self, path: pathlib.Path) -> SafetyCheckResult:
        """Check if a path should be scanned, returning the safety check result."""
        # Skip if not a file
        if not path.is_file():
            return SafetyCheckResult(False, "Not a file", "not_file")
        
        # Safety check
        return self.safety_checker.check_source(path)
    
    def get_file_info(self, path: pathlib.Path) -> Optional[FileInfo]:
        """Get FileInfo for a file."""
        try:
            stat = path.stat()
            
            # Get MIME type
            mime_type = self.classifier.get_mime_type(path)
            file_type = self.classifier.get_file_type(path)
            
            file_info = FileInfo(
                path=path,
                filename=path.name,
                extension=path.suffix.lower(),
                mime_type=mime_type,
                file_type=file_type,
                size=stat.st_size,
                created=datetime.fromtimestamp(stat.st_birthtime) if hasattr(stat, 'st_birthtime') else datetime.fromtimestamp(stat.st_ctime),
                modified=datetime.fromtimestamp(stat.st_mtime),
            )
            
            # Classify
            file_info = self.classifier.classify(file_info)

            if file_info.extension == '.zip':
                archive = inspect_zip(path)
                if archive.is_repository:
                    file_info.category = Category.REPOSITORY_ARCHIVE
                    file_info.confidence = archive.confidence
                    file_info.reason = archive.reason
                    file_info.archive_origin = archive.origin
                    file_info.archive_owner = archive.owner
                    if archive.origin in {'company', 'company_internal'}:
                        file_info.work_review = True
                        file_info.protection_type = 'COMPANY_REPOSITORY_ARCHIVE'
                        file_info.reason = 'Company repository archive — manual review required'
            
            # Propose destination
            file_info.proposed_destination = self.classifier.propose_destination(file_info, self.config)
            
            return file_info
            
        except Exception as e:
            print(f"Error processing {path}: {e}")
            return None
    
    def compute_hash(self, path: pathlib.Path) -> Optional[str]:
        """Compute SHA-256 hash of a file."""
        try:
            sha256 = hashlib.sha256()
            with open(path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except Exception:
            return None
    
    def scan_directory(self, path: pathlib.Path) -> Iterator[pathlib.Path]:
        """Yield all files in a directory recursively."""
        try:
            for entry in path.rglob('*'):
                if entry.is_file():
                    yield entry
        except Exception as e:
            print(f"Error scanning {path}: {e}")
    
    def scan(self) -> tuple:
        """Scan all configured directories."""
        all_files = []
        stats = ScanStats()
        
        print("╭──────────────────────────────────────╮")
        print("│           ROY ORGANIZER              │")
        print("│        Local Mac File Butler         │")
        print("╰──────────────────────────────────────╯")
        print()
        
        # Collect all files first
        all_paths = []
        self.safety_checker.prepare_open_files()
        stats.open_file_state = self.safety_checker.open_file_state
        stats.open_file_error = self.safety_checker.open_file_error
        for scan_path in self.scan_paths:
            if scan_path.exists():
                print(f"Scanning {scan_path.name}........ ", end="", flush=True)
                count = 0
                for file_path in self.scan_directory(scan_path):
                    result = self.should_scan(file_path)
                    if result.safe:
                        all_paths.append(file_path)
                        count += 1
                    else:
                        stats.skipped += 1
                        reason = result.skip_reason or "unknown"
                        stats.protected_by_reason[reason] = stats.protected_by_reason.get(reason, 0) + 1
                        # Track work_review for skipped files
                        if result.skip_reason == "work_data":
                            stats.work_review += 1
                print(f"✓ ({count} files)")
            else:
                print(f"Scanning {scan_path.name}........ ⊘ (not found)")
        
        print(f"\nProcessing {len(all_paths)} files...")
        
        # Process files with thread pool for speed
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_path = {
                executor.submit(self.get_file_info, path): path 
                for path in all_paths
            }
            
            for i, future in enumerate(as_completed(future_to_path)):
                file_info = future.result()
                if file_info:
                    all_files.append(file_info)
                    
                    # Update stats
                    stats.total_files += 1
                    stats.total_size += file_info.size
                    
                    # By category
                    cat = file_info.category.value
                    stats.by_category[cat] = stats.by_category.get(cat, 0) + 1
                    
                    # By folder
                    try:
                        rel = file_info.path.relative_to(pathlib.Path.home())
                        folder = rel.parts[0] if rel.parts else "Unknown"
                    except Exception:
                        folder = "Unknown"
                    stats.by_folder[folder] = stats.by_folder.get(folder, 0) + 1
                    
                    # Track special categories
                    if file_info.category == Category.SCREENSHOTS:
                        stats.screenshots += 1
                    elif file_info.category == Category.ARCHIVES:
                        stats.archives += 1
                    elif file_info.category == Category.INSTALLERS:
                        stats.installers += 1
                    elif file_info.category == Category.VIDEOS:
                        stats.videos += 1
                    elif file_info.category == Category.DOCUMENTS and file_info.extension == '.pdf':
                        stats.pdfs += 1
                    elif file_info.category == Category.CODE:
                        stats.code_folders += 1
                    elif file_info.category == Category.NEEDS_REVIEW:
                        stats.unclassified += 1
                    
                    if file_info.needs_review:
                        stats.needs_review += 1
                    if file_info.work_review:
                        stats.work_review += 1
                    if file_info.protection_type:
                        key = file_info.protection_type.lower()
                        stats.protected_by_reason[key] = stats.protected_by_reason.get(key, 0) + 1
                    
                    # Track for duplicate detection
                    if file_info.size >= self.min_duplicate_size:
                        if file_info.size not in self.size_map:
                            self.size_map[file_info.size] = []
                        self.size_map[file_info.size].append(file_info)
                    
                    # Progress
                    if (i + 1) % 500 == 0:
                        print(f"  Processed {i + 1}/{len(all_paths)} files...")
        
        print(f"\nClassification complete. Detecting duplicates...")
        
        # Detect duplicates
        self._detect_duplicates(all_files, stats)
        
        # Find largest files
        stats.largest_files = sorted(all_files, key=lambda f: f.size, reverse=True)[:20]
        
        # Find oldest files
        stats.oldest_files = sorted(all_files, key=lambda f: f.created or datetime.max)[:20]
        
        print(f"Scan complete: {stats.total_files} files, {self._format_size(stats.total_size)}")
        return all_files, stats
    
    def _detect_duplicates(self, files: List[FileInfo], stats: ScanStats):
        """Detect duplicate files."""
        duplicate_pairs = []
        
        for size, file_list in self.size_map.items():
            if len(file_list) < 2:
                continue
            
            # Group by hash if enabled
            if self.use_hash:
                hash_groups = {}
                for f in file_list:
                    if f.hash is None:
                        f.hash = self.compute_hash(f.path)
                    if f.hash:
                        if f.hash not in hash_groups:
                            hash_groups[f.hash] = []
                        hash_groups[f.hash].append(f)
                
                for hash_val, group in hash_groups.items():
                    if len(group) > 1:
                        original = group[0]
                        for dup in group[1:]:
                            dup.is_duplicate = True
                            dup.duplicate_of = original.path
                            duplicate_pairs.append((original, dup))
            else:
                # Just by size and name similarity
                for i, f1 in enumerate(file_list):
                    for f2 in file_list[i+1:]:
                        if f1.filename == f2.filename:
                            f2.is_duplicate = True
                            f2.duplicate_of = f1.path
                            duplicate_pairs.append((f1, f2))
        
        stats.duplicates = duplicate_pairs
        print(f"Found {len(duplicate_pairs)} duplicate pairs")
    
    def _format_size(self, size: int) -> str:
        """Format file size human-readable."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"


def create_scanner(config: dict) -> Scanner:
    """Factory function to create a Scanner."""
    return Scanner(config)
