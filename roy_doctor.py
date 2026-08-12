"""Read-only environment diagnostics."""
import os
import pathlib
import platform
import shutil
import sys

from roy_ai import LocalAI
from roy_config import VERSION, validate_config
from roy_safety import SafetyChecker


def diagnose(config: dict) -> list[dict]:
    checks = []
    def add(name, ok, detail): checks.append({'name': name, 'ok': bool(ok), 'detail': str(detail)})
    add('Version', True, VERSION)
    add('Operating system', platform.system() == 'Darwin', platform.platform())
    add('Python', sys.version_info >= (3, 10), platform.python_version())
    errors = validate_config(config); add('Configuration', not errors, '; '.join(errors) or 'valid')
    add('Machine profile', bool(config.get('machine_profile')), config.get('machine_profile', 'missing'))
    for value in config.get('scan_paths', []):
        path = pathlib.Path(os.path.expanduser(value))
        add(f'Scan root {path.name}', path.exists() and os.access(path, os.R_OK), 'readable' if path.exists() else 'missing')
    checker = SafetyChecker(config); checker.prepare_open_files()
    add('Open-file detection', checker.open_file_state == 'KNOWN', checker.open_file_state)
    add('Protected paths', bool(checker.protected_paths), f'{len(checker.protected_paths)} configured')
    add('Ollama (optional)', bool(shutil.which('ollama')), 'available' if shutil.which('ollama') else 'not installed')
    try:
        import tkinter
        gui = True
    except ImportError:
        gui = False
    add('GUI', gui, 'Tkinter available' if gui else 'Tkinter unavailable')
    add('Real execution', config.get('safety', {}).get('planning_only') is True, 'blocked (planning_only)')
    return checks


def print_diagnostics(config: dict) -> bool:
    checks = diagnose(config)
    print('\nROY Doctor — read-only\n')
    for check in checks:
        print(f"[{'OK' if check['ok'] else 'WARN'}] {check['name']}: {check['detail']}")
    return all(check['ok'] for check in checks if check['name'] not in {'Operating system','Ollama (optional)','GUI'})
