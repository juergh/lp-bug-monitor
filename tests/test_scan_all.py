"""Tests for multi-set scanning (scan-all) and the dashboard index page."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from lp_bug_monitor.cli import discover_sets, main, set_title


def make_set(
    data_dir: Path,
    name: str,
    packages: list[str],
    bugs: dict | None = None,
    last_scan: str | None = "2026-11-09T08:00:00+00:00",
) -> Path:
    """Create a package set directory with packages.txt and a state file."""
    set_dir = data_dir / name
    set_dir.mkdir(parents=True)
    (set_dir / "packages.txt").write_text("\n".join(packages) + "\n", encoding="utf-8")
    state = {"last_scan_utc": last_scan, "packages": packages, "bugs": bugs or {}}
    (set_dir / "bugs-state.json").write_text(json.dumps(state), encoding="utf-8")
    return set_dir


def test_set_title():
    assert set_title("firmware") == "Ubuntu Bug Status — firmware"


def test_discover_sets(tmp_path: Path):
    make_set(tmp_path, "systemd", ["systemd"])
    make_set(tmp_path, "firmware", ["linux-firmware"])

    # Not sets: directory without packages.txt, hidden directory, stray file
    (tmp_path / "notaset").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "packages.txt").write_text("something\n", encoding="utf-8")
    (tmp_path / "loose.txt").write_text("pkg\n", encoding="utf-8")

    sets = discover_sets(tmp_path)
    assert [d.name for d in sets] == ["firmware", "systemd"]


def test_discover_sets_missing_dir(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        discover_sets(tmp_path / "nope")


def test_scan_all_missing_dir(tmp_path: Path):
    assert main(["scan-all", str(tmp_path / "nope")]) == 1


def test_scan_all_no_sets(tmp_path: Path):
    (tmp_path / "empty").mkdir()
    assert main(["scan-all", str(tmp_path)]) == 1


def test_scan_all_report_only_generates_dashboards_and_index(tmp_path: Path):
    make_set(
        tmp_path,
        "firmware",
        ["linux-firmware"],
        bugs={"111": {"id": 111, "package": "linux-firmware", "title": "Bug A", "tasks": []}},
    )
    make_set(tmp_path, "systemd", ["systemd"], bugs={})

    exit_code = main(["scan-all", "--no-scan", "--no-workflow-url", str(tmp_path)])
    assert exit_code == 0

    firmware_html = (tmp_path / "firmware" / "index.html").read_text(encoding="utf-8")
    assert "Ubuntu Bug Status — firmware" in firmware_html
    assert "Bug A" in firmware_html

    systemd_html = (tmp_path / "systemd" / "index.html").read_text(encoding="utf-8")
    assert "Ubuntu Bug Status — systemd" in systemd_html

    index_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert 'href="firmware/index.html"' in index_html
    assert 'href="systemd/index.html"' in index_html
    assert "Open bugs: <strong>1</strong>" in index_html
    assert "Open bugs: <strong>0</strong>" in index_html
    assert "Packages: <strong>1</strong>" in index_html
    assert "2026-11-09 08:00 UTC" in index_html


def test_scan_all_report_only_uses_state_packages(tmp_path: Path):
    """A set's report-only run passes the packages recorded in its state file."""
    make_set(tmp_path, "firmware", ["linux-firmware"], bugs={})
    # Empty packages.txt: report-only mode falls back to state packages
    (tmp_path / "firmware" / "packages.txt").write_text("# nothing\n", encoding="utf-8")

    with patch("lp_bug_monitor.cli.generate_html_report") as mock_generate_html:
        exit_code = main(["scan-all", "--no-scan", "--no-workflow-url", str(tmp_path)])
    assert exit_code == 0
    assert mock_generate_html.call_args.kwargs["packages_scanned"] == ["linux-firmware"]


@patch("lp_bug_monitor.cli.get_launchpad")
@patch("lp_bug_monitor.cli.get_ubuntu_distribution")
@patch("lp_bug_monitor.cli.get_active_series", return_value=["noble"])
@patch("lp_bug_monitor.cli.load_state")
@patch("lp_bug_monitor.cli.save_state")
@patch("lp_bug_monitor.cli.scan_full", return_value={})
def test_scan_all_shares_connection_and_scans_each_set(
    mock_scan_full,
    mock_save_state,
    mock_load_state,
    mock_get_series,
    mock_get_distro,
    mock_get_lp,
    tmp_path: Path,
):
    make_set(tmp_path, "firmware", ["linux-firmware"])
    make_set(tmp_path, "systemd", ["systemd"])
    mock_load_state.return_value = {"last_scan_utc": None, "packages": [], "bugs": {}}

    exit_code = main(["scan-all", "--full", str(tmp_path)])
    assert exit_code == 0

    # One shared Launchpad connection for all sets
    assert mock_get_lp.call_count == 1
    assert mock_scan_full.call_count == 2
    scanned_pkgs = {c.kwargs["packages"][0] for c in mock_scan_full.call_args_list}
    assert scanned_pkgs == {"linux-firmware", "systemd"}

    # State saved per set
    assert mock_save_state.call_count == 2
    saved_paths = {c.args[0] for c in mock_save_state.call_args_list}
    assert saved_paths == {
        tmp_path / "firmware" / "bugs-state.json",
        tmp_path / "systemd" / "bugs-state.json",
    }

    # Landing page generated
    assert (tmp_path / "index.html").is_file()


@patch("lp_bug_monitor.cli.get_launchpad")
@patch("lp_bug_monitor.cli.get_ubuntu_distribution")
@patch("lp_bug_monitor.cli.get_active_series", return_value=["noble"])
@patch("lp_bug_monitor.cli.load_state")
@patch("lp_bug_monitor.cli.save_state")
@patch("lp_bug_monitor.cli.scan_full", return_value={})
def test_scan_all_dry_run_keeps_state(
    mock_scan_full,
    mock_save_state,
    mock_load_state,
    mock_get_series,
    mock_get_distro,
    mock_get_lp,
    tmp_path: Path,
):
    make_set(tmp_path, "firmware", ["linux-firmware"])
    mock_load_state.return_value = {"last_scan_utc": None, "packages": [], "bugs": {}}

    exit_code = main(["scan-all", "--full", "--dry-run", str(tmp_path)])
    assert exit_code == 0
    assert mock_scan_full.called
    assert not mock_save_state.called


@patch("lp_bug_monitor.cli.generate_html_report")
def test_scan_all_failure_isolation_and_partial_index(mock_generate_html, tmp_path: Path):
    """A failing set does not abort the remaining sets; the index page only
    links the dashboards that were generated successfully."""
    make_set(tmp_path, "aaa", ["pkg-a"])
    make_set(tmp_path, "bbb", ["pkg-b"])
    mock_generate_html.side_effect = [Exception("boom"), None]

    exit_code = main(["scan-all", "--no-scan", str(tmp_path)])
    assert exit_code == 1

    index_html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "bbb" in index_html
    assert "aaa" not in index_html


@patch("lp_bug_monitor.cli.get_launchpad")
@patch("lp_bug_monitor.cli.get_ubuntu_distribution")
def test_scan_all_connect_failure_returns_error(mock_get_distro, mock_get_lp, tmp_path: Path):
    make_set(tmp_path, "firmware", ["linux-firmware"])
    mock_get_lp.side_effect = Exception("connection refused")

    exit_code = main(["scan-all", str(tmp_path)])
    assert exit_code == 1
    assert not mock_get_distro.called
