"""Load and validate a clinic YAML configuration file."""

import os
import yaml
from pathlib import Path


def load_clinic_config(path: str) -> dict:
    resolved = Path(path).resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Clinic config not found: {resolved}")

    with open(resolved, "r") as fh:
        config = yaml.safe_load(fh)

    # Substitute env vars inside string values (e.g. ${GOOGLE_CALENDAR_ID})
    config = _expand_env(config)
    return config


def _expand_env(obj):
    if isinstance(obj, str):
        return os.path.expandvars(obj)
    if isinstance(obj, dict):
        return {k: _expand_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env(i) for i in obj]
    return obj
