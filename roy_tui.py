"""Dependency-free interactive terminal home for ROY Organizer."""
import pathlib
import pickle

from roy_analytics import organization_score, storage_overview

MENU = [
    ('1', 'Organize Screenshots', 'review'), ('2', 'Review Downloads', 'review'),
    ('3', 'Images', 'review'), ('4', 'Documents', 'review'), ('5', 'Videos', 'review'),
    ('6', 'General Archives', 'review'), ('7', 'Repository Archives', 'review'),
    ('8', 'Duplicate Finder', 'duplicates'), ('9', 'Needs Review', 'review'),
    ('P', 'Protected Files', 'protected'), ('S', 'Storage Report', 'storage'),
    ('O', 'Organization Score', 'score'), ('H', 'Help', 'help'), ('Q', 'Quit', 'quit'),
]


def menu_action(value: str) -> str:
    value = value.strip().upper()
    return next((action for key, _, action in MENU if key == value), 'unknown')


def dashboard_text(config: dict, files, stats) -> str:
    profile = config.get('machine_profile', 'personal').replace('_', ' ').title()
    protected = sum(getattr(stats, 'protected_by_reason', {}).values())
    proposed = sum(bool(item.proposed_destination) and not item.work_review for item in files)
    lines = [
        '╭────────────────────────────────────────────────────────────╮',
        '│                     ROY ORGANIZER                          │',
        '│                Safe Mac File Butler                       │',
        '├────────────────────────────────────────────────────────────┤',
        f'  Machine Profile: {profile}', f'  Open-file state: {stats.open_file_state}',
        f'  Files scanned: {stats.total_files:,}', f'  Proposed organization: {proposed:,}',
        f'  Protected: {protected:,}', f'  Needs review: {stats.needs_review:,}',
        f'  Duplicate candidates: {len(stats.duplicates):,}',
        '├────────────────────────────────────────────────────────────┤']
    lines += [f'  [{key}] {label}' for key, label, _ in MENU]
    lines.append('╰────────────────────────────────────────────────────────────╯')
    return '\n'.join(lines)


def launch(config: dict, handlers: dict) -> None:
    scan_file = pathlib.Path('data/last_scan.pkl')
    if not scan_file.exists():
        print('No scan found. Run: roy scan')
        return
    with scan_file.open('rb') as handle:
        files, stats = pickle.load(handle)
    while True:
        print(dashboard_text(config, files, stats))
        action = menu_action(input('Choose: '))
        if action == 'quit':
            return
        if action == 'help':
            print('Use a menu key. Review is planning-only; no real execution is available.')
        elif action == 'score':
            print(organization_score(files, stats))
        elif action == 'storage':
            print(storage_overview(files, stats))
        elif action in handlers:
            handlers[action]()
        else:
            print('Unknown choice. Press H for help.')
