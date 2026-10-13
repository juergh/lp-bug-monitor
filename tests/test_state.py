"""Tests for state persistence and incremental tracking."""

from __future__ import annotations

from pathlib import Path

from lp_bug_monitor.state import get_default_state, load_state, save_state


def test_load_nonexistent_state(tmp_path: Path):
    nonexistent = tmp_path / "does_not_exist.json"
    state = load_state(nonexistent)
    assert state == get_default_state()
    assert state["bugs"] == {}
    assert state["last_scan_utc"] is None


def test_save_and_load_roundtrip(tmp_path: Path):
    state_file = tmp_path / "bugs_state.json"
    payload = {
        "last_scan_utc": "2026-10-13T10:00:00+00:00",
        "packages": ["linux-firmware", "linux-firmware-raspi"],
        "bugs": {
            "12345": {
                "id": 12345,
                "title": "Firmware load failure",
                "package": "linux-firmware",
                "tasks": [
                    {
                        "target": "linux-firmware (Ubuntu)",
                        "status": "In Progress",
                        "is_complete": False,
                    }
                ],
            }
        },
    }

    save_state(state_file, payload)
    assert state_file.is_file()

    loaded = load_state(state_file)
    assert loaded["last_scan_utc"] == "2026-10-13T10:00:00+00:00"
    assert loaded["packages"] == ["linux-firmware", "linux-firmware-raspi"]
    assert "12345" in loaded["bugs"]
    assert loaded["bugs"]["12345"]["title"] == "Firmware load failure"


def test_load_corrupted_state(tmp_path: Path):
    corrupt_file = tmp_path / "corrupt.json"
    corrupt_file.write_text("NOT VALID JSON! {{{", encoding="utf-8")

    state = load_state(corrupt_file)
    assert state == get_default_state()
