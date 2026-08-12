#!/usr/bin/env python3
"""
ROY Organizer - Main Entry Point
Local Mac File Butler for safe file organization.
"""
import os
import sys
import pathlib
import argparse
import json
import pickle
from datetime import datetime
from typing import Optional, List

# Use stdlib only - no external dependencies
from roy_scan import Scanner, create_scanner, ScanStats
from roy_classify import FileInfo, Category, create_classifier
from roy_transactions import (
    TransactionLog, FileMover, 
    create_transaction_log, create_file_mover
)
from roy_safety import SafetyChecker, get_safety_checker
from roy_plan import (CATEGORY_CHOICES, DEFAULT_SOURCE_NAMES, ReviewPlan,
                      filter_needs_review, parse_category_choices,
                      parse_source_choices)
from roy_config import load_config, save_config
from roy_analytics import organization_score, recommendations, storage_overview
from roy_tui import launch as launch_tui
from roy_gui import launch as launch_gui
from roy_demo import run_demo
from roy_pilot import (PilotExecutor, format_pilot_block, missing_plan_sources,
                       PILOT_PREFIX, SCREENSHOT_PREFIX, load_blocked_screenshots,
                       pilot_summary, save_blocked_screenshots,
                       screenshot_summary, select_pilot_operations,
                       select_screenshot_operations)
from roy_doctor import print_diagnostics


def print_banner():
    """Print the ROY Organizer banner."""
    print("╭──────────────────────────────────────╮")
    print("│           ROY ORGANIZER              │")
    print("│        Local Mac File Butler         │")
    print("╰──────────────────────────────────────╯")
    print()


def print_stats(stats: ScanStats):
    """Print scan statistics."""
    # Summary
    print("┌────────────────────────────────────────┐")
    print("│           SCAN SUMMARY                 │")
    print("├────────────────────────────────────────┤")
    print(f"│ Total Files:      {stats.total_files:>10,} │")
    print(f"│ Total Size:       {format_size(stats.total_size):>10} │")
    print(f"│ Skipped (safety): {stats.skipped:>10,} │")
    print(f"│ Needs Review:     {stats.needs_review:>10,} │")
    print(f"│ Work Review:      {stats.work_review:>10,} │")
    print(f"│ Duplicate Pairs:  {len(stats.duplicates):>10,} │")
    print("└────────────────────────────────────────┘")
    print()
    print(f"Open-file state: {getattr(stats, 'open_file_state', 'UNKNOWN')}")
    if getattr(stats, 'open_file_error', None):
        print("Planning may continue, but execution validation is blocked.")
    print()
    
    # By category
    if stats.by_category:
        print("Files by Category:")
        print("  Category                    Count    %")
        print("  " + "-" * 40)
        for cat, count in sorted(stats.by_category.items(), key=lambda x: -x[1]):
            pct = (count / stats.total_files * 100) if stats.total_files > 0 else 0
            print(f"  {cat:<28} {count:>6,}  {pct:>5.1f}%")
        print()
    
    # By folder
    if stats.by_folder:
        print("Files by Source Folder:")
        for folder, count in sorted(stats.by_folder.items(), key=lambda x: -x[1]):
            print(f"  {folder:<20} {count:>6,}")
        print()
    
    # Special categories
    print("Special Categories:")
    print(f"  Screenshots:      {stats.screenshots:>6,}")
    print(f"  Archives:         {stats.archives:>6,}")
    print(f"  Installers:       {stats.installers:>6,}")
    print(f"  Videos:           {stats.videos:>6,}")
    print(f"  PDFs:             {stats.pdfs:>6,}")
    print(f"  Code Projects:    {stats.code_folders:>6,}")
    print(f"  Unclassified:     {stats.unclassified:>6,}")
    print()
    
    # Largest files
    if stats.largest_files:
        print("Largest Files (Top 20):")
        print("  File                                    Size       Category")
        print("  " + "-" * 65)
        for f in stats.largest_files:
            name = f.filename[:40]
            print(f"  {name:<40} {format_size(f.size):>10}  {f.category.value}")
        print()
    
    # Duplicates
    if stats.duplicates:
        print("Duplicate Candidates (Top 20):")
        print("  Original                              Duplicate                             Size")
        print("  " + "-" * 85)
        for orig, dup in stats.duplicates[:20]:
            o_name = orig.filename[:35]
            d_name = dup.filename[:35]
            print(f"  {o_name:<35}  {d_name:<35}  {format_size(orig.size):>10}")
        print()


def format_size(size: int) -> str:
    """Format file size human-readable."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def print_plan_summary(plan: ReviewPlan):
    """Print a planning-only final summary."""
    summary = plan.summary()
    print("\nFINAL PLAN\n")
    print(f"Approved moves:     {summary['approved']:>7,}")
    print(f"Skipped:            {summary['skipped']:>7,}")
    print(f"Pending review:     {summary['pending']:>7,}")
    print(f"Data to move:       {format_size(summary['data_to_move']):>10}")
    if summary['by_category']:
        print("\nBy category:")
        for category, count in sorted(summary['by_category'].items()):
            print(f"  {category:<20} {count:>7,}")
    approved_screenshots = [operation for operation in plan.operations
                            if operation.decision == 'approved'
                            and operation.category == Category.SCREENSHOTS.value]
    if approved_screenshots:
        source_counts = {name: 0 for name in DEFAULT_SOURCE_NAMES}
        for operation in approved_screenshots:
            source_counts[operation.source_folder] = source_counts.get(
                operation.source_folder, 0) + 1
        print(f"\nScreenshots approved: {len(approved_screenshots):,}\n")
        for source in DEFAULT_SOURCE_NAMES:
            print(f"  {source:<12} {source_counts[source]:>7,}")
        print("\nDestination:\n\nPictures/\n└── Screenshots/")
    print("\nProtected:")
    print(f"  Code                {summary['protected_code']:>7,}")
    print(f"  Work Review         {summary['protected_work']:>7,}")
    print(f"\nDuplicate pairs:      {summary['duplicate_pairs']:>7,}")
    print("No duplicates will be deleted.")
    print("\nPlanning only: execution is disabled in Phase 2.")


def _show_needs_review(items, page=0, page_size=25):
    start = page * page_size
    print(f"\nNEEDS REVIEW — showing {start + 1}-{min(start + page_size, len(items))} of {len(items):,}")
    for item in items[start:start + page_size]:
        print(f"  {item.path}  ({format_size(item.size)})")


def _review_category(plan: ReviewPlan, category: Category):
    operations = plan.filtered(category=category.value)
    if not operations:
        return
    groups = plan.grouped(operations, by='destination')
    print(f"\n{category.value.upper()}\n\n{len(operations):,} files found.\n")
    print("Sources included:")
    for source, group in sorted(plan.grouped(operations, by='source').items()):
        print(f"  {source:<24} {len(group):>7,} files")
    print()
    print("Grouped by destination:")
    for destination, group in sorted(groups.items()):
        print(f"  {pathlib.Path(destination).name or destination:<24} {len(group):>7,} files")
    print("\n[A] Approve all  [M] Review destination groups  [I] Review files  [S] Skip all  [B] Back")
    choice = input("Choose: ").strip().upper()
    if choice == 'A':
        plan.decide(operations, 'approved')
    elif choice == 'S':
        plan.decide(operations, 'skipped')
    elif choice == 'M':
        dimension = input("Group by [D]estination [E]xtension [S]ource [C]onfidence: ").strip().upper()
        group_by = {'D': 'destination', 'E': 'extension', 'S': 'source', 'C': 'confidence'}.get(dimension, 'destination')
        selected_groups = plan.grouped(operations, by=group_by)
        for label, group in sorted(selected_groups.items()):
            answer = input(f"{label} ({len(group):,}) [A]pprove/[S]kip/[P]ending: ").strip().upper()
            if answer == 'A':
                plan.decide(group, 'approved')
            elif answer == 'S':
                plan.decide(group, 'skipped')
    elif choice == 'I':
        for index, operation in enumerate(operations, 1):
            print(_format_review_operation(operation, index, len(operations)))
            print(f"\nReason: {operation.reason}\nConfidence: {operation.confidence:.0%}")
            answer = input("[A]pprove [S]kip [C]hange destination [R]emaining similar [B]ack [Q]uit: ").strip().upper()
            if answer == 'A':
                plan.decide([operation], 'approved')
            elif answer == 'S':
                plan.decide([operation], 'skipped')
            elif answer == 'C':
                destination = input("Destination directory: ").strip()
                if destination:
                    plan.change_destination(operation, pathlib.Path(destination))
            elif answer == 'R':
                decision = input("Apply [A]pprove or [S]kip to this destination group: ").strip().upper()
                if decision in {'A', 'S'}:
                    similar = groups[str(pathlib.Path(operation.destination).parent)]
                    plan.decide(similar, 'approved' if decision == 'A' else 'skipped')
            elif answer in {'B', 'Q'}:
                break


def _format_review_operation(operation, index: int, total: int) -> str:
    """Render a proposal without hiding either side of the planned operation."""
    return (f"\n[{index}/{total}]\nCURRENT LOCATION\n{operation.source}\n\n"
            f"PROPOSED DESTINATION\n{operation.destination}")


def cmd_review(args, config: dict):
    """Interactively build or resume a local, planning-only review plan."""
    scan_path = pathlib.Path('data/last_scan.pkl')
    plan_path = pathlib.Path(config.get('review', {}).get('plan_file', 'data/current_plan.json'))
    if not scan_path.exists():
        print("No scan data found. Run 'roy scan' first.")
        return
    with open(scan_path, 'rb') as handle:
        files, stats = pickle.load(handle)

    if plan_path.exists():
        answer = input("Resume saved plan? [y/N]: ").strip().lower()
        if answer == 'y':
            plan = ReviewPlan.load(plan_path)
            for value in plan.selected_categories:
                try:
                    _review_category(plan, Category(value))
                except ValueError:
                    continue
                plan.save(plan_path)
            print_plan_summary(plan)
            input("\n[M] Modify later  [S] Save and exit  [Q] Quit: ")
            return

    profile = config.get('machine_profile', 'personal').replace('_', ' ').title()
    print("╭──────────────────────────────────────────╮")
    print("│              ROY ORGANIZER               │")
    print("│          Safe Planning Review            │")
    print("╰──────────────────────────────────────────╯\n")
    print(f"Machine profile: {profile}\n")
    reasons = getattr(stats, 'protected_by_reason', {})
    print("Protected:")
    print(f"  Software projects       {reasons.get('software_project', 0):>8,}")
    print(f"  Work/company files      {reasons.get('work_data', 0):>8,}")
    print(f"  Developer config        {reasons.get('developer_config', 0):>8,}")
    print(f"  Kubernetes configs      {reasons.get('kubernetes_config', 0):>8,}\n")
    print("Available for review:\n")
    for key, category in CATEGORY_CHOICES.items():
        if category == Category.REPOSITORY_ARCHIVE:
            personal = sum(f.category == category and f.archive_origin == 'personal' for f in files)
            unknown = sum(f.category == category and f.archive_origin == 'unknown' for f in files)
            company = sum(f.category == category and f.archive_origin in {'company', 'company_internal'} for f in files)
            print(f"[{key}] Personal/unknown repo ZIPs {personal + unknown:>6,} files")
            print(f"    Company repo ZIPs          {company:>6,} PROTECTED")
        else:
            print(f"[{key}] {category.value:<18} {stats.by_category.get(category.value, 0):>8,} files")
    print(f"[D] Duplicate review   {len(stats.duplicates):>8,} pairs")
    print(f"[N] Needs Review       {stats.needs_review:>8,} files")
    print("[P] Protected summary")
    print("\n[A] Select all safe categories\n[Q] Quit")
    raw = input("\nEnter choices (default: none): ").strip()
    if not raw or raw.upper() == 'Q':
        print("No categories selected.")
        return
    tokens = {token.strip().upper() for token in raw.split(',')}
    if 'P' in tokens:
        print_protected_summary(stats)
    if 'N' in tokens:
        page = 0
        review_items = filter_needs_review(files)
        while True:
            _show_needs_review(review_items, page)
            action = input("[N]ext [F]irst [E]xtension [O]source [Z]size [D]ate [/]search [Q]back: ").strip().upper()
            if action == 'N':
                page += 1
            elif action == 'F':
                page = 0
            elif action == 'E':
                review_items = filter_needs_review(files, extension=input("Extension: ").strip())
                page = 0
            elif action == 'O':
                review_items = filter_needs_review(files, source=input("Source: ").strip())
                page = 0
            elif action == 'Z':
                minimum = input("Minimum bytes (blank none): ").strip()
                maximum = input("Maximum bytes (blank none): ").strip()
                review_items = filter_needs_review(files, min_size=int(minimum) if minimum else None,
                                                   max_size=int(maximum) if maximum else None)
                page = 0
            elif action == 'D':
                value = input("Modified on/after YYYY-MM-DD: ").strip()
                review_items = filter_needs_review(files, modified_after=datetime.fromisoformat(value))
                page = 0
            elif action == '/':
                review_items = filter_needs_review(files, search=input("Filename search: ").strip())
                page = 0
            else:
                break
    if 'D' in tokens:
        print(f"\n{len(stats.duplicates):,} duplicate pairs are available for review. No deletion is planned.")
    categories = parse_category_choices(raw)
    if not categories:
        return
    source_raw = input(
        "Optional source filter "
        "[All sources] (Desktop, Downloads, Documents, Pictures, Movies): "
    ).strip()
    sources = parse_source_choices(source_raw, DEFAULT_SOURCE_NAMES)
    if not sources:
        print("Review scope: All configured scan roots (recursive)")
    else:
        print(f"Review scope: {', '.join(sorted(sources))} (recursive)")
    # Rebuild proposals with current destination policy so older scan snapshots
    # cannot carry source-relative Phase 1 destinations into a new plan.
    classifier = create_classifier(config)
    for item in files:
        item.proposed_destination = classifier.propose_destination(item, config)
    plan = ReviewPlan.from_inventory(files, stats, categories, sources)
    for category in sorted(categories, key=lambda value: value.value):
        _review_category(plan, category)
        plan.save(plan_path)
    print_plan_summary(plan)
    choice = input("\n[M] Modify later  [S] Save and exit  [Q] Quit: ").strip().upper()
    if choice in {'M', 'S'}:
        plan.save(plan_path)
        print(f"Plan saved to {plan_path}")


def generate_reports(files: List[FileInfo], stats: ScanStats, config: dict):
    """Generate report files."""
    import csv
    
    reports_dir = pathlib.Path(config.get('reports', {}).get('output_dir', 'reports'))
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    # Inventory CSV
    csv_path = reports_dir / config.get('reports', {}).get('inventory_csv', 'inventory.csv')
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'path', 'filename', 'extension', 'mime_type', 'file_type',
            'size', 'created', 'modified', 'category', 'confidence',
            'reason', 'proposed_destination', 'is_duplicate', 'duplicate_of',
            'hash', 'needs_review', 'work_review'
        ])
        for f in files:
            writer.writerow([
                f.path, f.filename, f.extension, f.mime_type, f.file_type,
                f.size, f.created.isoformat() if f.created else '',
                f.modified.isoformat() if f.modified else '',
                f.category.value, f.confidence, f.reason,
                str(f.proposed_destination) if f.proposed_destination else '',
                f.is_duplicate, str(f.duplicate_of) if f.duplicate_of else '',
                f.hash or '', f.needs_review, f.work_review
            ])
    
    # Inventory JSON
    json_path = reports_dir / config.get('reports', {}).get('inventory_json', 'inventory.json')
    with open(json_path, 'w') as f:
        json.dump([fi.to_dict() for fi in files], f, indent=2, default=str)
    
    # Summary Markdown
    md_path = reports_dir / config.get('reports', {}).get('summary_md', 'summary.md')
    with open(md_path, 'w') as f:
        f.write(f"# ROY Organizer Scan Report\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"## Summary\n\n")
        f.write(f"- **Total Files:** {stats.total_files:,}\n")
        f.write(f"- **Total Size:** {format_size(stats.total_size)}\n")
        f.write(f"- **Skipped (Safety):** {stats.skipped:,}\n")
        f.write(f"- **Needs Review:** {stats.needs_review:,}\n")
        f.write(f"- **Work Review Required:** {stats.work_review:,}\n")
        f.write(f"- **Duplicate Pairs:** {len(stats.duplicates):,}\n\n")
        
        f.write(f"## By Category\n\n")
        f.write(f"| Category | Count | Percentage |\n")
        f.write(f"|----------|-------|------------|\n")
        for cat, count in sorted(stats.by_category.items(), key=lambda x: -x[1]):
            pct = (count / stats.total_files * 100) if stats.total_files > 0 else 0
            f.write(f"| {cat} | {count:,} | {pct:.1f}% |\n")
        f.write(f"\n")
        
        f.write(f"## By Source Folder\n\n")
        f.write(f"| Folder | Count |\n")
        f.write(f"|--------|-------|\n")
        for folder, count in sorted(stats.by_folder.items(), key=lambda x: -x[1]):
            f.write(f"| {folder} | {count:,} |\n")
        f.write(f"\n")
        
        f.write(f"## Special Categories\n\n")
        f.write(f"- **Screenshots:** {stats.screenshots:,}\n")
        f.write(f"- **Archives:** {stats.archives:,}\n")
        f.write(f"- **Installers:** {stats.installers:,}\n")
        f.write(f"- **Videos:** {stats.videos:,}\n")
        f.write(f"- **PDFs:** {stats.pdfs:,}\n")
        f.write(f"- **Code Projects:** {stats.code_folders:,}\n")
        f.write(f"- **Unclassified:** {stats.unclassified:,}\n\n")
        
        if stats.duplicates:
            f.write(f"## Duplicate Candidates (Top 20)\n\n")
            f.write(f"| Original | Duplicate | Size |\n")
            f.write(f"|----------|-----------|------|\n")
            for orig, dup in stats.duplicates[:20]:
                f.write(f"| {orig.filename} | {dup.filename} | {format_size(orig.size)} |\n")
            f.write(f"\n")
    
    # Duplicates CSV
    if stats.duplicates:
        dup_csv_path = reports_dir / config.get('reports', {}).get('duplicates_csv', 'duplicates.csv')
        with open(dup_csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['original', 'duplicate', 'size', 'hash', 'suggested_action'])
            for orig, dup in stats.duplicates:
                writer.writerow([
                    orig.path, dup.path, orig.size, orig.hash or '',
                    'Move to ROY-Duplicate-Review'
                ])
    
    print(f"Reports generated in {reports_dir}/")
    print(f"  - {csv_path.name}")
    print(f"  - {json_path.name}")
    print(f"  - {md_path.name}")
    if stats.duplicates:
        print(f"  - {dup_csv_path.name}")


def print_protected_summary(stats: ScanStats):
    labels = {
        'software_project': 'Software projects', 'hidden_file': 'Hidden files',
        'work_data': 'Work/company files', 'open_file': 'Open files',
        'developer_config': 'Developer configuration',
        'kubernetes_config': 'Kubernetes configuration',
        'company_security': 'Company security tooling',
        'company_repository_archive': 'Company repository ZIPs',
        'protected_path': 'Protected system paths',
    }
    print("\nProtected files\n")
    reasons = getattr(stats, 'protected_by_reason', {})
    for key, label in labels.items():
        print(f"{label:<28} {reasons.get(key, 0):>10,}")
    print(f"{'Total':<28} {sum(reasons.values()):>10,}")
    print(f"\nOpen-file state: {getattr(stats, 'open_file_state', 'UNKNOWN')}")


def cmd_protected(args, config: dict):
    """Show read-only protected counts from the last scan."""
    scan_file = pathlib.Path('data/last_scan.pkl')
    if not scan_file.exists():
        print("No scan data found. Run 'roy scan' first.")
        return
    with open(scan_file, 'rb') as handle:
        _, stats = pickle.load(handle)
    print_protected_summary(stats)


def _load_scan():
    path = pathlib.Path('data/last_scan.pkl')
    if not path.exists():
        return None
    with path.open('rb') as handle:
        return pickle.load(handle)


def cmd_score(args, config: dict):
    scan = _load_scan()
    if not scan:
        print("No scan data found. Run 'roy scan' first.")
        return
    files, stats = scan
    result = organization_score(files, stats)
    print(f"\nROY ORGANIZATION SCORE\n\n{result['overall']} / 100\n")
    for source, score in sorted(result['sources'].items()):
        print(f"{source:<16} {score:>3}")
    print("\nRecommendations:")
    for index, value in enumerate(recommendations(files, stats), 1):
        print(f"{index}. {value}")
    print("\nThis is a deterministic organization indicator, not system health.")


def cmd_storage(args, config: dict):
    scan = _load_scan()
    if not scan:
        print("No scan data found. Run 'roy scan' first.")
        return
    files, stats = scan
    result = storage_overview(files, stats)
    print("\nStorage overview\n")
    for category, size in sorted(result['by_category'].items(), key=lambda item: -item[1]):
        print(f"{category:<24} {format_size(size):>10}")
    print(f"\nExact duplicate candidate storage: {format_size(result['exact_duplicate_bytes'])}")


def cmd_scan(args, config: dict):
    """Scan command."""
    scanner = create_scanner(config)
    files, stats = scanner.scan()
    
    # Store for later commands
    data_dir = pathlib.Path('data')
    data_dir.mkdir(parents=True, exist_ok=True)
    
    with open(data_dir / 'last_scan.pkl', 'wb') as f:
        pickle.dump((files, stats), f)
    
    print_stats(stats)
    return files, stats


def cmd_report(args, config: dict):
    """Report command."""
    data_dir = pathlib.Path('data')
    scan_file = data_dir / 'last_scan.pkl'
    
    if not scan_file.exists():
        print("No scan data found. Run 'roy scan' first.")
        return
    
    with open(scan_file, 'rb') as f:
        files, stats = pickle.load(f)
    
    print_stats(stats)
    generate_reports(files, stats, config)


def cmd_dry_run(args, config: dict):
    """Dry run command."""
    data_dir = pathlib.Path('data')
    scan_file = data_dir / 'last_scan.pkl'
    
    if not scan_file.exists():
        print("No scan data found. Run 'roy scan' first.")
        return
    
    with open(scan_file, 'rb') as f:
        files, stats = pickle.load(f)
    
    # Filter files that would be moved
    to_move = [f for f in files if f.proposed_destination and f.category != Category.NEEDS_REVIEW and not f.work_review]
    skipped = [f for f in files if f.work_review]
    needs_review = [f for f in files if f.needs_review or f.category == Category.NEEDS_REVIEW]
    duplicates = [f for f in files if f.is_duplicate]
    
    print("=" * 60)
    print("DRY RUN - No files will be moved")
    print("=" * 60)
    print()
    
    # Show proposed moves
    for f in to_move[:50]:  # Limit display
        print(f"→ MOVE: {f.path}")
        print(f"       → {f.proposed_destination}")
        print(f"       Reason: {f.reason}")
        print()
    
    if len(to_move) > 50:
        print(f"... and {len(to_move) - 50} more files")
        print()
    
    # Show skipped
    for f in skipped[:20]:
        print(f"⊘ SKIP: {f.path}")
        print(f"       Reason: Work data detected")
        print()
    
    # Summary
    total_size = sum(f.size for f in to_move)
    
    print("=" * 60)
    print("DRY RUN SUMMARY")
    print("=" * 60)
    print(f"Files Scanned:            {stats.total_files:,}")
    print(f"Files Proposed to Move:   {len(to_move):,}")
    print(f"Files Skipped (Work):     {len(skipped):,}")
    print(f"Needs Review:             {len(needs_review):,}")
    print(f"Potential Duplicates:     {len(duplicates):,}")
    print(f"Estimated Data to Move:   {format_size(total_size)}")
    print()
    
    # Ask for confirmation
    if config.get('dry_run', {}).get('ask_confirmation', True):
        if not args.yes:
            response = input("Proceed with these changes? [y/N]: ")
            if response.lower() != 'y':
                print("Aborted.")
                return
    
    # If confirmed, run organize
    if args.yes or response.lower() == 'y':
        cmd_organize(args, config)


def cmd_organize(args, config: dict):
    """Organize command - actually move files."""
    if config.get('safety', {}).get('planning_only', True):
        print("Execution is disabled in Phase 2. Use 'roy review' to build a plan.")
        return
    data_dir = pathlib.Path('data')
    scan_file = data_dir / 'last_scan.pkl'
    
    if not scan_file.exists():
        print("No scan data found. Run 'roy scan' first.")
        return
    
    with open(scan_file, 'rb') as f:
        files, stats = pickle.load(f)
    
    # Filter files to move
    to_move = [f for f in files if f.proposed_destination and f.category != Category.NEEDS_REVIEW and not f.work_review]
    
    if not to_move:
        print("No files to organize.")
        return
    
    # Initialize transaction log and mover
    transaction_log = create_transaction_log(config)
    mover = create_file_mover(config, transaction_log)
    mover.set_dry_run(False)
    
    # Generate batch ID
    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    print(f"ORGANIZING - Batch: {batch_id}")
    print()
    
    # Move files
    success = 0
    failed = 0
    
    for i, f in enumerate(to_move):
        print(f"[{i+1}/{len(to_move)}] Moving {f.filename}...", end=" ")
        if mover.move_file(f.path, f.proposed_destination, f.reason, batch_id):
            success += 1
            print("✓")
        else:
            failed += 1
            print("✗")
    
    print()
    print(f"Successfully moved: {success}")
    if failed > 0:
        print(f"Failed: {failed}")
    
    # Update scan data (remove moved files)
    remaining = [f for f in files if f not in to_move]
    with open(scan_file, 'wb') as f:
        pickle.dump((remaining, stats), f)


def cmd_undo(args, config: dict):
    """Undo command."""
    if config.get('safety', {}).get('planning_only', True):
        print("Execution is disabled in Phase 2. Undo is unavailable in planning-only mode.")
        return
    transaction_log = create_transaction_log(config)
    mover = create_file_mover(config, transaction_log)
    mover.set_dry_run(args.dry_run)
    
    if args.last:
        count = mover.undo_last_n(args.last)
        print(f"Undid {count} operations from last {args.last} batch(es)")
    elif args.batch:
        count = mover.undo_batch(args.batch)
        print(f"Undid {count} operations from batch {args.batch}")
    else:
        # Undo last batch
        last_batch = transaction_log.get_last_batch()
        if last_batch:
            count = mover.undo_batch(last_batch)
            print(f"Undid {count} operations from batch {last_batch}")
        else:
            print("No batches to undo")


def _pilot_executor(config: dict) -> PilotExecutor:
    log_path = pathlib.Path(config.get('logging', {}).get(
        'pilot_transaction_log', 'logs/pilot-transactions.jsonl'))
    return PilotExecutor(config, log_path)


def cmd_execute(args, config: dict):
    """Run only explicitly gated screenshot execution modes."""
    pilot_mode = getattr(args, 'pilot', False)
    screenshot_mode = getattr(args, 'screenshots', False)
    if not pilot_mode and not screenshot_mode:
        print("Unrestricted execution is disabled. Use --pilot or --screenshots.")
        return
    retry_mode = bool(getattr(args, 'retry_blocked', False))
    if retry_mode and not screenshot_mode:
        print("Blocked screenshot retry requires --screenshots.")
        return
    blocked_path = pathlib.Path(config.get('logging', {}).get(
        'blocked_screenshot_report', 'data/blocked-screenshots-latest.json'))
    plan_path = pathlib.Path(config.get('review', {}).get('plan_file', 'data/current_plan.json'))
    if retry_mode:
        if not blocked_path.exists():
            print("No blocked screenshot retry report found.")
            return
        try:
            operations = load_blocked_screenshots(blocked_path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            print(f"Blocked screenshot retry report is invalid: {error}")
            return
        plan = ReviewPlan(operations)
    elif not plan_path.exists():
        print("No saved review plan found.")
        return
    else:
        plan = ReviewPlan.load(plan_path)
    missing_sources = missing_plan_sources(plan)
    if missing_sources:
        print("STALE PLAN\n")
        print(f"The saved plan references {len(missing_sources):,} source file(s) that no longer exist.")
        print("No operations were processed. Generate a new plan before executing:")
        print("\n  python roy.py scan\n  python roy.py review")
        print("\nMissing source paths:")
        for source in missing_sources[:20]:
            print(f"  {source}")
        if len(missing_sources) > 20:
            print(f"  ... and {len(missing_sources) - 20:,} more")
        stale_source = blocked_path if retry_mode else plan_path
        print(f"\nThe stale input was retained for inspection: {stale_source}")
        return
    operations = (select_pilot_operations(plan) if pilot_mode
                  else select_screenshot_operations(plan))
    print(pilot_summary(operations) if pilot_mode else screenshot_summary(operations))
    if not operations:
        print("\nNo approved screenshot operations are eligible.")
        return
    required = "EXECUTE PILOT" if pilot_mode else "EXECUTE SCREENSHOTS"
    confirmation = input(f"\nType exactly {required} to continue: ")
    executor = _pilot_executor(config)
    def show_progress(progress):
        estimate = (f"{progress['estimate']:.1f} s" if progress['estimate'] is not None
                    else 'calculating')
        print(f"\nBatch {progress['batch']}/{progress['batches']}\n")
        print(f"Moved: {progress['moved']}")
        print(f"Blocked: {progress['blocked']}")
        print(f"Elapsed: {progress['elapsed']:.1f} s")
        print(f"Remaining: {progress['remaining']:,} files")
        print(f"Estimated: {estimate}")

    result = (executor.execute(operations, confirmation) if pilot_mode
              else executor.execute_screenshots(operations, confirmation, show_progress))
    if screenshot_mode:
        print(f"\nRun: {result['run_id']}")
        if result['blocked']:
            save_blocked_screenshots(blocked_path, result['run_id'], operations,
                                     result['blocked'])
            print(f"\nBlocked screenshots were left untouched and saved for retry:\n{blocked_path}")
            print("Retry with: python roy.py execute --screenshots --retry-blocked")
        elif retry_mode:
            save_blocked_screenshots(blocked_path, result['run_id'], operations, [])
            print("\nAll retry operations passed; the blocked retry list is now empty.")
    print(f"\nPilot batch: {result['batch_id'] or 'not started'}")
    print(f"Moved: {result['executed']}")
    print(f"Blocked: {len(result['blocked'])}")
    by_source = {operation.source: operation for operation in operations}
    for source, reason in result['blocked']:
        print(f"\nBLOCKED\n\n{format_pilot_block(by_source.get(source), reason)}")


def cmd_verify(args, config: dict):
    if not args.last:
        print("Verification requires --last.")
        return
    result = _pilot_executor(config).verify_last()
    print(f"Pilot batch: {result['batch_id'] or 'none'}")
    print(f"Moved files verified: {result['moved']}")
    print(f"Transaction log consistent: {'YES' if result['consistent'] else 'NO'}")
    print(f"Anomalies: {len(result['anomalies'])}")
    for anomaly in result['anomalies']:
        print(f"  {anomaly}")


def cmd_pilot_undo(config: dict):
    result = _pilot_executor(config).undo_last((PILOT_PREFIX,))
    print(f"Pilot batch: {result['batch_id'] or 'none'}")
    print(f"Restored: {result['undone']}")
    print(f"Blocked: {len(result['blocked'])}")
    for source, reason in result['blocked']:
        print(f"  BLOCKED {source}: {reason}")


def cmd_screenshot_undo(config: dict):
    executor = _pilot_executor(config)
    run_id = executor.journal.last_active_run((SCREENSHOT_PREFIX,))
    if not run_id:
        print("No active screenshot run is available to undo.")
        return
    summary = executor.screenshot_run_summary(run_id)
    print(f"UNDO SCREENSHOT RUN\n\nRun: {run_id}\n"
          f"Moved: {summary['moved']:,}\nBatches: {summary['batches']:,}\n"
          f"Verified: {'YES' if summary['verified'] else 'NO'}")
    if input("\nType exactly UNDO SCREENSHOTS to continue: ") != 'UNDO SCREENSHOTS':
        print("Undo cancelled.")
        return
    result = executor.undo_screenshot_run(run_id)
    print(f"Screenshot run: {result['run_id'] or 'none'}")
    print(f"Restored: {result['undone']}")
    print(f"Blocked: {len(result['blocked'])}")
    for source, reason in result['blocked']:
        print(f"  BLOCKED {source}: {reason}")


def cmd_history(args, config: dict):
    runs = _pilot_executor(config).history()
    if not runs:
        print("No screenshot runs recorded.")
        return
    for index, run in enumerate(runs, 1):
        print(f"Run {index}\n\nID: {run['run_id']}\nType: {run['type']}\n"
              f"Date: {run['timestamp'][:19] or 'unknown'}\nMoved: {run['moved']:,}\n"
              f"Batches: {run['batches']:,}\nVerified: {'YES' if run['verified'] else 'NO'}\n"
              f"Undo available: {'YES' if run['undo_available'] else 'NO'}\n")


def cmd_status(args, config: dict):
    """Status command - show transaction log summary."""
    transaction_log = create_transaction_log(config)
    transactions = transaction_log.all_transactions()
    
    if not transactions:
        print("No transactions recorded")
        return
    
    # Group by batch
    batches = {}
    for t in transactions:
        if t.batch_id:
            if t.batch_id not in batches:
                batches[t.batch_id] = {'total': 0, 'reversed': 0, 'operations': []}
            batches[t.batch_id]['total'] += 1
            if t.reversed:
                batches[t.batch_id]['reversed'] += 1
            batches[t.batch_id]['operations'].append(t)
    
    print("Transaction History:")
    print("  Batch ID                    Ops  Rev  Status      Timestamp")
    print("  " + "-" * 70)
    for batch_id, info in sorted(batches.items(), reverse=True):
        status = "REVERSED" if info['reversed'] == info['total'] else "ACTIVE"
        first_txn = info['operations'][0]
        print(f"  {batch_id:<28} {info['total']:>3}  {info['reversed']:>3}  {status:<10}  {first_txn.timestamp[:19]}")


def cmd_config(args, config: dict):
    """Config command."""
    config_path = pathlib.Path("config.json")
    
    if args.show:
        print(json.dumps(config, indent=2))
    elif args.edit:
        import subprocess
        subprocess.run([os.environ.get('EDITOR', 'nano'), str(config_path)])
    elif args.set:
        # Set a config value
        keys = args.set.split('.')
        d = config
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        # Try to parse as JSON, fallback to string
        try:
            value = json.loads(args.value)
        except json.JSONDecodeError:
            value = args.value
        d[keys[-1]] = value
        save_config(config, config_path)
        print(f"Set {args.set} = {args.value}")
    else:
        print(f"Config file: {config_path}")
        print("Use --show to display, --edit to edit, --set key.path value to modify")


def cmd_screenshots(args, config: dict):
    """Screenshots command - organize screenshots specifically."""
    data_dir = pathlib.Path('data')
    scan_file = data_dir / 'last_scan.pkl'
    
    if not scan_file.exists():
        print("No scan data found. Run 'roy scan' first.")
        return
    
    with open(scan_file, 'rb') as f:
        files, stats = pickle.load(f)
    
    screenshots = [f for f in files if f.category == Category.SCREENSHOTS]
    
    print(f"Found {len(screenshots)} screenshots")
    
    if args.organize and config.get('safety', {}).get('planning_only', True):
        print("Execution is disabled in Phase 2. Use 'roy review'.")
        return
    if args.dry_run or args.organize:
        transaction_log = create_transaction_log(config)
        mover = create_file_mover(config, transaction_log)
        mover.set_dry_run(args.dry_run)
        
        batch_id = datetime.now().strftime("%Y%m%d_%H%M%S_screenshots")
        
        for f in screenshots:
            if f.proposed_destination:
                mover.move_file(f.path, f.proposed_destination, "Screenshot organization", batch_id)
        
        if not args.dry_run:
            print(f"Organized {len(screenshots)} screenshots")


def cmd_downloads(args, config: dict):
    """Downloads command - organize downloads specifically."""
    data_dir = pathlib.Path('data')
    scan_file = data_dir / 'last_scan.pkl'
    
    if not scan_file.exists():
        print("No scan data found. Run 'roy scan' first.")
        return
    
    with open(scan_file, 'rb') as f:
        files, stats = pickle.load(f)
    
    downloads = [f for f in files if 'Downloads' in str(f.path)]
    
    print(f"Found {len(downloads)} files in Downloads")
    
    if args.organize and config.get('safety', {}).get('planning_only', True):
        print("Execution is disabled in Phase 2. Use 'roy review'.")
        return
    if args.dry_run or args.organize:
        transaction_log = create_transaction_log(config)
        mover = create_file_mover(config, transaction_log)
        mover.set_dry_run(args.dry_run)
        
        batch_id = datetime.now().strftime("%Y%m%d_%H%M%S_downloads")
        
        for f in downloads:
            if f.proposed_destination and f.category != Category.NEEDS_REVIEW:
                mover.move_file(f.path, f.proposed_destination, "Downloads organization", batch_id)
        
        if not args.dry_run:
            print("Organized Downloads")


def cmd_desktop(args, config: dict):
    """Desktop command - organize desktop specifically."""
    data_dir = pathlib.Path('data')
    scan_file = data_dir / 'last_scan.pkl'
    
    if not scan_file.exists():
        print("No scan data found. Run 'roy scan' first.")
        return
    
    with open(scan_file, 'rb') as f:
        files, stats = pickle.load(f)
    
    desktop = [f for f in files if 'Desktop' in str(f.path)]
    
    print(f"Found {len(desktop)} files on Desktop")
    
    if args.organize and config.get('safety', {}).get('planning_only', True):
        print("Execution is disabled in Phase 2. Use 'roy review'.")
        return
    if args.dry_run or args.organize:
        transaction_log = create_transaction_log(config)
        mover = create_file_mover(config, transaction_log)
        mover.set_dry_run(args.dry_run)
        
        batch_id = datetime.now().strftime("%Y%m%d_%H%M%S_desktop")
        
        for f in desktop:
            if f.proposed_destination and f.category != Category.NEEDS_REVIEW:
                mover.move_file(f.path, f.proposed_destination, "Desktop organization", batch_id)
        
        if not args.dry_run:
            print("Organized Desktop")


def cmd_duplicates(args, config: dict):
    """Duplicates command."""
    data_dir = pathlib.Path('data')
    scan_file = data_dir / 'last_scan.pkl'
    
    if not scan_file.exists():
        print("No scan data found. Run 'roy scan' first.")
        return
    
    with open(scan_file, 'rb') as f:
        files, stats = pickle.load(f)
    
    duplicates = [f for f in files if f.is_duplicate]
    
    print(f"Found {len(duplicates)} duplicate files")
    
    if args.report:
        reports_dir = pathlib.Path(config.get('reports', {}).get('output_dir', 'reports'))
        dup_csv = reports_dir / config.get('reports', {}).get('duplicates_csv', 'duplicates.csv')
        print(f"Duplicate report: {dup_csv}")
    
    if args.move_to_review and config.get('safety', {}).get('planning_only', True):
        print("Execution is disabled in Phase 2. Duplicate review is read-only.")
        return
    if args.move_to_review and not args.dry_run:
        # Move duplicates to review folder
        review_dir = pathlib.Path.home() / "Desktop" / "ROY-Duplicate-Review"
        review_dir.mkdir(parents=True, exist_ok=True)
        
        transaction_log = create_transaction_log(config)
        mover = create_file_mover(config, transaction_log)
        
        batch_id = datetime.now().strftime("%Y%m%d_%H%M%S_duplicates")
        
        for f in duplicates:
            dest = review_dir / f.filename
            # Handle collisions
            counter = 1
            while dest.exists():
                stem = f.path.stem
                suffix = f.path.suffix
                dest = review_dir / f"{stem}_{counter}{suffix}"
                counter += 1
            mover.move_file(f.path, dest, "Duplicate review", batch_id)
        
        print(f"Moved {len(duplicates)} duplicates to {review_dir}")


def cmd_large_files(args, config: dict):
    """Large files command."""
    data_dir = pathlib.Path('data')
    scan_file = data_dir / 'last_scan.pkl'
    
    if not scan_file.exists():
        print("No scan data found. Run 'roy scan' first.")
        return
    
    with open(scan_file, 'rb') as f:
        files, stats = pickle.load(f)
    
    thresholds = config.get('large_files', {}).get('thresholds', [])
    
    for threshold in thresholds:
        size = threshold['size']
        name = threshold['name']
        large = [f for f in files if f.size >= size]
        print(f"{name}: {len(large)} files")
        for f in large[:10]:
            print(f"  {format_size(f.size)} - {f.path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="ROY Organizer - Local Mac File Butler",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  scan          Scan configured directories and build inventory
  report        Show scan report and generate files
  review        Choose categories and build a resumable local plan
  protected     Show protected-file counts and reasons
  score         Show deterministic organization score
  storage       Show read-only storage analytics
  gui           Open beginner planning preview
  demo          Run synthetic sandbox execute/undo demonstration
  doctor        Run read-only installation and safety diagnostics
  dry-run       Show what would be moved without moving
  organize      Actually move files (requires confirmation)
  screenshots   Organize screenshots specifically
  downloads     Organize Downloads folder
  desktop       Organize Desktop folder
  duplicates    Show and handle duplicate files
  large-files   Report large files
  undo          Undo last organization batch
  status        Show transaction history
  config        Show or edit configuration

Examples:
  roy scan
  roy report
  roy dry-run
  roy organize
  roy screenshots --dry-run
  roy downloads --organize
  roy undo
  roy undo --last 2
  roy status
  config --show
        """
    )
    
    parser.add_argument('--config', default='config.json', help='Config file path')
    parser.add_argument('--yes', '-y', action='store_true', help='Auto-confirm prompts')
    parser.add_argument('--dry-run', action='store_true', help='Dry run mode')
    
    subparsers = parser.add_subparsers(dest='command', help='Command')
    
    # scan
    subparsers.add_parser('scan', help='Scan directories')
    
    # report
    subparsers.add_parser('report', help='Show report')

    # Interactive planning; controlled execution remains a separate command.
    subparsers.add_parser('review', help='Build or resume an interactive review plan')
    subparsers.add_parser('protected', help='Show protected-file summary')
    subparsers.add_parser('score', help='Show organization score')
    subparsers.add_parser('storage', help='Show storage analytics')
    subparsers.add_parser('gui', help='Open beginner planning preview')
    subparsers.add_parser('demo', help='Run safe synthetic sandbox demo')
    subparsers.add_parser('doctor', help='Run read-only diagnostics')
    
    # dry-run
    dry_run_parser = subparsers.add_parser('dry-run', help='Dry run organization')
    dry_run_parser.add_argument('--yes', '-y', action='store_true', help='Auto-confirm')
    
    # organize
    subparsers.add_parser('organize', help='Organize files')

    execute_parser = subparsers.add_parser('execute', help='Controlled screenshot execution')
    execute_modes = execute_parser.add_mutually_exclusive_group()
    execute_modes.add_argument('--pilot', action='store_true', help='Run 20-file screenshot pilot')
    execute_modes.add_argument('--screenshots', action='store_true', help='Run approved screenshot batch')
    execute_parser.add_argument('--retry-blocked', action='store_true',
                                help='Retry screenshots from the last blocked report')

    verify_parser = subparsers.add_parser('verify', help='Verify pilot transaction state')
    verify_parser.add_argument('--last', action='store_true', help='Verify most recent pilot batch')
    subparsers.add_parser('history', help='Show controlled screenshot run history')
    
    # screenshots
    ss_parser = subparsers.add_parser('screenshots', help='Organize screenshots')
    ss_parser.add_argument('--dry-run', action='store_true', help='Dry run')
    ss_parser.add_argument('--organize', action='store_true', help='Actually organize')
    
    # downloads
    dl_parser = subparsers.add_parser('downloads', help='Organize Downloads')
    dl_parser.add_argument('--dry-run', action='store_true', help='Dry run')
    dl_parser.add_argument('--organize', action='store_true', help='Actually organize')
    
    # desktop
    dt_parser = subparsers.add_parser('desktop', help='Organize Desktop')
    dt_parser.add_argument('--dry-run', action='store_true', help='Dry run')
    dt_parser.add_argument('--organize', action='store_true', help='Actually organize')
    
    # duplicates
    dup_parser = subparsers.add_parser('duplicates', help='Handle duplicates')
    dup_parser.add_argument('--report', action='store_true', help='Show report')
    dup_parser.add_argument('--move-to-review', action='store_true', help='Move to review folder')
    dup_parser.add_argument('--dry-run', action='store_true', help='Dry run')
    
    # large-files
    subparsers.add_parser('large-files', help='Report large files')
    
    # undo
    undo_parser = subparsers.add_parser('undo', help='Undo last batch')
    undo_parser.add_argument('--last', type=int, help='Undo last N batches')
    undo_parser.add_argument('--batch', help='Undo specific batch ID')
    undo_parser.add_argument('--dry-run', action='store_true', help='Dry run')
    undo_modes = undo_parser.add_mutually_exclusive_group()
    undo_modes.add_argument('--pilot', action='store_true', help='Undo most recent pilot batch only')
    undo_modes.add_argument('--screenshots', action='store_true', help='Undo most recent screenshot batch only')
    
    # status
    subparsers.add_parser('status', help='Show transaction status')
    
    # config
    config_parser = subparsers.add_parser('config', help='Show/edit config')
    config_parser.add_argument('--show', action='store_true', help='Show config')
    config_parser.add_argument('--edit', action='store_true', help='Edit config')
    config_parser.add_argument('--set', help='Set config value (key.path=value)')
    config_parser.add_argument('--value', help='Value for --set')
    
    args = parser.parse_args()
    
    # Load config
    config_path = pathlib.Path(args.config)
    config = load_config(config_path)
    
    # Override dry_run from args
    if args.dry_run:
        config['dry_run'] = config.get('dry_run', {})
        config['dry_run']['enabled'] = True
    
    # Print banner for non-config commands
    if args.command != 'config':
        print_banner()
    
    # Dispatch command
    if args.command == 'scan':
        cmd_scan(args, config)
    elif args.command == 'report':
        cmd_report(args, config)
    elif args.command == 'review':
        cmd_review(args, config)
    elif args.command == 'protected':
        cmd_protected(args, config)
    elif args.command == 'score':
        cmd_score(args, config)
    elif args.command == 'storage':
        cmd_storage(args, config)
    elif args.command == 'gui':
        launch_gui(config)
    elif args.command == 'demo':
        print(json.dumps(run_demo(), indent=2))
    elif args.command == 'doctor':
        print_diagnostics(config)
    elif args.command == 'dry-run':
        cmd_dry_run(args, config)
    elif args.command == 'organize':
        cmd_organize(args, config)
    elif args.command == 'execute':
        cmd_execute(args, config)
    elif args.command == 'verify':
        cmd_verify(args, config)
    elif args.command == 'history':
        cmd_history(args, config)
    elif args.command == 'screenshots':
        cmd_screenshots(args, config)
    elif args.command == 'downloads':
        cmd_downloads(args, config)
    elif args.command == 'desktop':
        cmd_desktop(args, config)
    elif args.command == 'duplicates':
        cmd_duplicates(args, config)
    elif args.command == 'large-files':
        cmd_large_files(args, config)
    elif args.command == 'undo':
        if args.pilot:
            cmd_pilot_undo(config)
        elif args.screenshots:
            cmd_screenshot_undo(config)
        else:
            cmd_undo(args, config)
    elif args.command == 'status':
        cmd_status(args, config)
    elif args.command == 'config':
        cmd_config(args, config)
    else:
        launch_tui(config, {
            'review': lambda: cmd_review(args, config),
            'protected': lambda: cmd_protected(args, config),
            'duplicates': lambda: cmd_duplicates(argparse.Namespace(report=True, move_to_review=False, dry_run=True), config),
        })


if __name__ == '__main__':
    main()
