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
from roy_classify import FileInfo, Category
from roy_transactions import (
    TransactionLog, FileMover, 
    create_transaction_log, create_file_mover
)
from roy_safety import SafetyChecker, get_safety_checker


def load_config(config_path: pathlib.Path) -> dict:
    """Load configuration from JSON file."""
    if config_path.exists():
        with open(config_path, 'r') as f:
            return json.load(f)
    return {}


def save_config(config: dict, config_path: pathlib.Path):
    """Save configuration to JSON file."""
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)


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
    
    # dry-run
    dry_run_parser = subparsers.add_parser('dry-run', help='Dry run organization')
    dry_run_parser.add_argument('--yes', '-y', action='store_true', help='Auto-confirm')
    
    # organize
    subparsers.add_parser('organize', help='Organize files')
    
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
    elif args.command == 'dry-run':
        cmd_dry_run(args, config)
    elif args.command == 'organize':
        cmd_organize(args, config)
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
        cmd_undo(args, config)
    elif args.command == 'status':
        cmd_status(args, config)
    elif args.command == 'config':
        cmd_config(args, config)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
