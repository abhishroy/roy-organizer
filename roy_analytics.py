"""Deterministic explainability, organization score, and storage analytics."""
from collections import Counter, defaultdict
from typing import Iterable

from roy_classify import Category, FileInfo


def explain(item: FileInfo) -> list[str]:
    signals = []
    if item.category == Category.SCREENSHOTS:
        signals += ['Matches macOS screenshot naming pattern',
                    f'{item.extension.upper().lstrip(".")} image',
                    'Screenshot date detected from filename',
                    'Pictures/Screenshots is configured destination']
    elif item.category == Category.REPOSITORY_ARCHIVE:
        signals += ['Repository structure detected inside ZIP',
                    f'Origin: {item.archive_origin or "unknown"}']
    elif item.protection_type:
        signals += [f'Protected: {item.protection_type}', 'No file contents or credentials displayed']
    else:
        signals.append(item.reason or 'Deterministic classification rule')
        if item.extension:
            signals.append(f'File extension: {item.extension}')
    return signals


def organization_score(files: Iterable[FileInfo], stats) -> dict:
    """Return a deterministic tidiness indicator, not a system-health claim.

    Each source begins at 100 and loses up to 70 points based on the fraction of
    safe files with a proposed destination, plus up to 20 for NeedsReview and 10
    for exact duplicate candidates. The overall score is the rounded mean.
    """
    files = list(files)
    by_source = defaultdict(list)
    for item in files:
        parts = item.path.parts
        source = next((part for part in parts if part in {'Desktop','Downloads','Documents','Pictures','Movies'}), 'Other')
        by_source[source].append(item)
    scores = {}
    for source, items in by_source.items():
        total = max(1, len(items))
        movable = sum(bool(item.proposed_destination) and not item.work_review for item in items)
        review = sum(item.needs_review or item.category == Category.NEEDS_REVIEW for item in items)
        penalty = min(70, round(70 * movable / total)) + min(20, round(20 * review / total))
        scores[source] = max(0, 100 - penalty)
    duplicate_penalty = min(10, round(10 * len(stats.duplicates) / max(1, stats.total_files)))
    scores['Duplicates'] = 100 - duplicate_penalty
    overall = round(sum(scores.values()) / max(1, len(scores)))
    return {'overall': overall, 'sources': scores,
            'label': 'Organization score (deterministic planning indicator)'}


def storage_overview(files: Iterable[FileInfo], stats) -> dict:
    by_category = Counter()
    for item in files:
        by_category[item.category.value] += item.size
    duplicate_bytes = sum(dup.size for _, dup in stats.duplicates)
    return {'total': stats.total_size, 'by_category': dict(by_category),
            'exact_duplicate_bytes': duplicate_bytes,
            'largest': [(item.filename, item.size, item.category.value) for item in stats.largest_files]}


def recommendations(files: Iterable[FileInfo], stats) -> list[str]:
    counts = Counter(item.category.value for item in files)
    items = []
    if counts['Screenshots']:
        items.append(f"Organize {counts['Screenshots']:,} screenshots")
    if counts['Archives']:
        items.append(f"Review {counts['Archives']:,} general archives")
    if stats.duplicates:
        items.append(f"Review {len(stats.duplicates):,} exact duplicate candidates")
    if counts['Installers']:
        items.append(f"Review {counts['Installers']:,} installers")
    return items
