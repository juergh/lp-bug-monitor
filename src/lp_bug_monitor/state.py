"""Persistent state management for periodic incremental bug scans."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_default_state() -> dict[str, Any]:
    """Return default empty state dictionary."""
    return {
        "last_scan_utc": None,
        "packages": [],
        "bugs": {},
    }


def load_state(path: Path | str) -> dict[str, Any]:
    """Load scan state from a JSON file.

    If the file does not exist or is invalid, returns an empty default state.
    """
    state_file = Path(path)
    if not state_file.is_file():
        logger.debug("State file %s does not exist; starting with clean state", state_file)
        return get_default_state()

    try:
        with state_file.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                logger.warning("State file %s is not a dictionary; resetting state", state_file)
                return get_default_state()

            bugs = data.get("bugs")
            if not isinstance(bugs, dict):
                data["bugs"] = {}

            return data
    except Exception as e:
        logger.warning("Failed to load state file %s (%s); resetting state", state_file, e)
        return get_default_state()


def save_state(path: Path | str, data: dict[str, Any]) -> None:
    """Save scan state atomically to a JSON file."""
    state_file = Path(path).resolve()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = state_file.with_suffix(f"{state_file.suffix}.tmp.{os.getpid()}")

    try:
        with temp_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        temp_file.replace(state_file)
        logger.debug("Saved state with %d bugs to %s", len(data.get("bugs", {})), state_file)
    except Exception:
        if temp_file.exists():
            temp_file.unlink(missing_ok=True)
        raise
