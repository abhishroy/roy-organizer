"""Planning and review primitives for ROY Organizer (no file execution)."""
import json
import os
import pathlib
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Iterable, List, Optional, Set

from roy_classify import Category, FileInfo


SAFE_CATEGORIES = {
    Category.SCREENSHOTS, Category.IMAGES, Category.VIDEOS, Category.AUDIO,
    Category.ARCHIVES, Category.INSTALLERS, Category.DOCUMENTS, Category.TRAVEL,
    Category.CV_CAREER, Category.FINANCE, Category.CERTIFICATES,
    Category.PERSONAL, Category.DATA,
    Category.REPOSITORY_ARCHIVE,
}

CATEGORY_CHOICES = {
    '1': Category.SCREENSHOTS, '2': Category.IMAGES, '3': Category.DOCUMENTS,
    '4': Category.VIDEOS, '5': Category.ARCHIVES, '6': Category.INSTALLERS,
    '7': Category.TRAVEL, '8': Category.CV_CAREER, '9': Category.FINANCE,
    'R': Category.REPOSITORY_ARCHIVE,
}


@dataclass
class PlanOperation:
    source: str
    destination: Optional[str]
    category: str
    confidence: float
    reason: str
    decision: str = 'pending'
    size: int = 0
    source_folder: str = 'Unknown'
    mtime: float = 0.0
    archive_origin: Optional[str] = None


def source_folder(path: pathlib.Path, home: Optional[pathlib.Path] = None) -> str:
    home = home or pathlib.Path.home()
    try:
        relative = path.relative_to(home)
        return relative.parts[0] if relative.parts else 'Unknown'
    except ValueError:
        for part in path.parts:
            if part in {'Desktop', 'Downloads', 'Documents', 'Pictures', 'Movies'}:
                return part
    return 'Unknown'


def parse_category_choices(value: str) -> Set[Category]:
    """Parse comma-separated menu choices. Blank and invalid input select none."""
    tokens = {token.strip().upper() for token in value.split(',') if token.strip()}
    if 'A' in tokens:
        return set(SAFE_CATEGORIES)
    return {CATEGORY_CHOICES[token] for token in tokens if token in CATEGORY_CHOICES}


def filter_needs_review(files: Iterable[FileInfo], *, extension: Optional[str] = None,
                        source: Optional[str] = None, min_size: Optional[int] = None,
                        max_size: Optional[int] = None, modified_after: Optional[datetime] = None,
                        search: Optional[str] = None) -> List[FileInfo]:
    """Filter NeedsReview inventory without ever creating move proposals."""
    result = [item for item in files if item.category == Category.NEEDS_REVIEW]
    if extension:
        extension = extension.lower()
        if not extension.startswith('.'):
            extension = '.' + extension
        result = [item for item in result if item.extension.lower() == extension]
    if source:
        result = [item for item in result if source_folder(item.path) == source]
    if min_size is not None:
        result = [item for item in result if item.size >= min_size]
    if max_size is not None:
        result = [item for item in result if item.size <= max_size]
    if modified_after:
        result = [item for item in result if item.modified and item.modified >= modified_after]
    if search:
        search = search.lower()
        result = [item for item in result if search in item.filename.lower()]
    return result


class ReviewPlan:
    """Persistent, local-only set of proposed operations and decisions."""

    def __init__(self, operations: Optional[List[PlanOperation]] = None,
                 selected_categories: Optional[Iterable[str]] = None,
                 selected_sources: Optional[Iterable[str]] = None,
                 protected_code: int = 0, protected_work: int = 0,
                 duplicate_pairs: int = 0):
        self.operations = operations or []
        self.selected_categories = list(selected_categories or [])
        self.selected_sources = list(selected_sources or [])
        self.protected_code = protected_code
        self.protected_work = protected_work
        self.duplicate_pairs = duplicate_pairs

    @classmethod
    def from_inventory(cls, files: Iterable[FileInfo], stats,
                       categories: Iterable[Category], sources: Iterable[str] = ()):
        categories = set(categories)
        sources = set(sources)
        operations = []
        for item in files:
            folder = source_folder(item.path)
            if item.category not in categories or (sources and folder not in sources):
                continue
            if item.category not in SAFE_CATEGORIES or item.work_review or not item.proposed_destination:
                continue
            operations.append(PlanOperation(
                source=str(item.path), destination=str(item.proposed_destination),
                category=item.category.value, confidence=item.confidence,
                reason=item.reason, size=item.size, source_folder=folder,
                mtime=item.modified.timestamp() if item.modified else 0.0,
                archive_origin=item.archive_origin,
            ))
        return cls(
            operations, [c.value for c in categories], sorted(sources),
            protected_code=stats.by_category.get(Category.CODE.value, 0),
            protected_work=stats.work_review,
            duplicate_pairs=len(stats.duplicates),
        )

    def filtered(self, *, category: Optional[str] = None,
                 source: Optional[str] = None, extension: Optional[str] = None,
                 min_size: Optional[int] = None, max_size: Optional[int] = None,
                 modified_after: Optional[str] = None, search: Optional[str] = None):
        result = self.operations
        if category:
            result = [op for op in result if op.category == category]
        if source:
            result = [op for op in result if op.source_folder == source]
        if extension:
            suffix = extension.lower()
            if not suffix.startswith('.'):
                suffix = '.' + suffix
            result = [op for op in result if pathlib.Path(op.source).suffix.lower() == suffix]
        if min_size is not None:
            result = [op for op in result if op.size >= min_size]
        if max_size is not None:
            result = [op for op in result if op.size <= max_size]
        if modified_after:
            cutoff = datetime.fromisoformat(modified_after)
            result = [op for op in result if pathlib.Path(op.source).stat().st_mtime >= cutoff.timestamp()]
        if search:
            term = search.lower()
            result = [op for op in result if term in pathlib.Path(op.source).name.lower()]
        return result

    def decide(self, operations: Iterable[PlanOperation], decision: str) -> None:
        if decision not in {'approved', 'skipped', 'pending'}:
            raise ValueError('Invalid plan decision')
        for operation in operations:
            operation.decision = decision

    def change_destination(self, operation: PlanOperation, destination: pathlib.Path) -> None:
        root = pathlib.Path(os.path.expanduser(str(destination)))
        operation.destination = str(root / pathlib.Path(operation.source).name)

    def grouped(self, operations: Optional[Iterable[PlanOperation]] = None,
                by: str = 'destination'):
        groups = defaultdict(list)
        for operation in operations or self.operations:
            if by == 'destination':
                key = str(pathlib.Path(operation.destination).parent) if operation.destination else 'None'
            elif by == 'source':
                key = operation.source_folder
            elif by == 'extension':
                key = pathlib.Path(operation.source).suffix.lower() or '(none)'
            elif by == 'confidence':
                key = f'{int(operation.confidence * 10) * 10}-{int(operation.confidence * 10) * 10 + 9}%'
            else:
                raise ValueError('Unsupported grouping')
            groups[key].append(operation)
        return dict(groups)

    def summary(self) -> dict:
        counts = Counter(op.decision for op in self.operations)
        by_category = Counter(op.category for op in self.operations if op.decision == 'approved')
        return {
            'approved': counts['approved'], 'skipped': counts['skipped'],
            'pending': counts['pending'],
            'data_to_move': sum(op.size for op in self.operations if op.decision == 'approved'),
            'by_category': dict(by_category), 'protected_code': self.protected_code,
            'protected_work': self.protected_work, 'duplicate_pairs': self.duplicate_pairs,
        }

    def save(self, path: pathlib.Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'version': 1, 'selected_categories': self.selected_categories,
            'selected_sources': self.selected_sources,
            'protected_code': self.protected_code, 'protected_work': self.protected_work,
            'duplicate_pairs': self.duplicate_pairs,
            'operations': [asdict(operation) for operation in self.operations],
        }
        path.write_text(json.dumps(payload, indent=2))

    @classmethod
    def load(cls, path: pathlib.Path):
        payload = json.loads(path.read_text())
        return cls(
            [PlanOperation(**item) for item in payload.get('operations', [])],
            payload.get('selected_categories'), payload.get('selected_sources'),
            payload.get('protected_code', 0), payload.get('protected_work', 0),
            payload.get('duplicate_pairs', 0),
        )
