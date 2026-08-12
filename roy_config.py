"""Configuration loading and validation for ROY Organizer."""
import json
import pathlib
from typing import Any, Dict, List

VERSION = "0.1.0"
PROFILES = {"personal", "developer", "company_managed", "developer_company_managed"}


def load_config(path: pathlib.Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open() as handle:
        return json.load(handle)


def save_config(config: Dict[str, Any], path: pathlib.Path) -> None:
    with path.open('w') as handle:
        json.dump(config, handle, indent=2)


def validate_config(config: Dict[str, Any]) -> List[str]:
    errors = []
    if config.get('machine_profile') not in PROFILES:
        errors.append('machine_profile must be a supported profile')
    if not isinstance(config.get('scan_paths'), list) or not config.get('scan_paths'):
        errors.append('scan_paths must be a non-empty list')
    safety = config.get('safety')
    if not isinstance(safety, dict):
        errors.append('safety configuration is required')
    elif safety.get('planning_only') is not True:
        errors.append('planning_only must remain true for Early Preview')
    return errors
