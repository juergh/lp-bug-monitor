"""Tests for CLI argument parsing and package file resolution."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from lp_bug_monitor.cli import (
    DEFAULT_WORKFLOW_URL,
    create_parser,
    load_packages_from_file,
    main,
    parse_args,
    resolve_packages,
)


def test_load_packages_from_file(tmp_path: Path):
    pkg_file = tmp_path / "packages.txt"
    pkg_file.write_text(
        """
        # Firmware source packages
        linux-firmware
        linux-firmware-raspi   # Raspberry Pi firmware

        # Wireless packages:
        linux-firmware-intel-wireless
        linux-firmware-broadcom-wireless

        # Empty lines and commented lines should be skipped:
        # linux-firmware-mediatek

        linux-firmware  # Duplicate should be deduplicated
        """,
        encoding="utf-8",
    )

    packages = load_packages_from_file(pkg_file)
    assert packages == [
        "linux-firmware",
        "linux-firmware-broadcom-wireless",
        "linux-firmware-intel-wireless",
        "linux-firmware-raspi",
    ]


def test_load_packages_from_nonexistent_file(tmp_path: Path):
    missing_file = tmp_path / "missing.txt"
    with pytest.raises(FileNotFoundError):
        load_packages_from_file(missing_file)


def test_parse_args_positional():
    args = parse_args(["linux-firmware", "systemd"])
    assert args.pos_packages == ["linux-firmware", "systemd"]
    assert args.packages is None
    assert args.packages_file is None
    assert args.output == Path("bugs.html")
    assert args.state_file == Path("bugs-state.json")
    assert not args.full
    assert args.workflow_url == DEFAULT_WORKFLOW_URL


def test_resolve_packages_positional():
    parser = create_parser()
    args = parse_args(["linux-firmware", "systemd"])
    pkgs = resolve_packages(args, parser)
    assert pkgs == ["linux-firmware", "systemd"]


def test_resolve_packages_flag():
    parser = create_parser()
    args = parse_args(["-p", "udev", "systemd"])
    pkgs = resolve_packages(args, parser)
    assert pkgs == ["systemd", "udev"]


def test_resolve_packages_file(tmp_path: Path):
    pkg_file = tmp_path / "pkgs.txt"
    pkg_file.write_text("linux-firmware\nlinux-firmware-raspi\n", encoding="utf-8")

    parser = create_parser()
    args = parse_args(["-f", str(pkg_file)])
    pkgs = resolve_packages(args, parser)
    assert pkgs == ["linux-firmware", "linux-firmware-raspi"]


def test_resolve_packages_combined(tmp_path: Path):
    pkg_file = tmp_path / "pkgs.txt"
    pkg_file.write_text("linux-firmware\n", encoding="utf-8")

    parser = create_parser()
    args = parse_args(["-f", str(pkg_file), "systemd", "-p", "openssl"])
    pkgs = resolve_packages(args, parser)
    assert pkgs == ["linux-firmware", "openssl", "systemd"]


def test_resolve_packages_none_fails():
    parser = create_parser()
    args = parse_args([])
    with pytest.raises(SystemExit):
        resolve_packages(args, parser)


def test_parse_args_custom_options():
    args = parse_args(
        [
            "linux-firmware",
            "-o",
            "custom.html",
            "--state-file",
            "custom_state.json",
            "--title",
            "Kernel Bugs",
            "--full",
            "-s",
            "noble",
            "jammy",
            "--workflow-url",
            "https://example.com/custom/workflow",
            "--verbose",
        ]
    )
    assert args.output == Path("custom.html")
    assert args.state_file == Path("custom_state.json")
    assert args.title == "Kernel Bugs"
    assert args.full
    assert args.series == ["noble", "jammy"]
    assert args.workflow_url == "https://example.com/custom/workflow"
    assert args.verbose


def test_parse_args_no_workflow_url():
    args = parse_args(["linux-firmware", "--no-workflow-url"])
    assert args.workflow_url is None


def test_parse_args_no_scan():
    args = parse_args(["--no-scan"])
    assert args.no_scan is True

    args_alias = parse_args(["--report-only"])
    assert args_alias.no_scan is True

    args_default = parse_args(["linux-firmware"])
    assert args_default.no_scan is False


def test_resolve_packages_no_scan_empty():
    parser = create_parser()
    args = parse_args(["--no-scan"])
    pkgs = resolve_packages(args, parser)
    assert pkgs == []


def test_main_no_scan_missing_state_file(tmp_path: Path):
    missing = tmp_path / "missing-state.json"
    exit_code = main(["--no-scan", "--state-file", str(missing)])
    assert exit_code == 1


@patch("lp_bug_monitor.cli.get_launchpad")
@patch("lp_bug_monitor.cli.save_state")
@patch("lp_bug_monitor.cli.generate_html_report")
def test_main_no_scan_success(mock_generate_html, mock_save_state, mock_get_lp, tmp_path: Path):
    state_file = tmp_path / "bugs-state.json"
    state_data = {
        "last_scan_utc": "2026-10-15T12:00:00+00:00",
        "packages": ["linux-firmware"],
        "bugs": {
            "123": {
                "id": 123,
                "package": "linux-firmware",
                "title": "Test bug",
                "tasks": [],
            }
        },
    }
    state_file.write_text(json.dumps(state_data), encoding="utf-8")
    out_html = tmp_path / "bugs.html"

    exit_code = main(["--no-scan", "--state-file", str(state_file), "-o", str(out_html)])
    assert exit_code == 0
    assert not mock_get_lp.called
    assert not mock_save_state.called
    assert mock_generate_html.called
    kwargs = mock_generate_html.call_args.kwargs
    assert "123" in kwargs["bugs"]
    assert kwargs["packages_scanned"] == ["linux-firmware"]
    assert kwargs["scan_time_utc"].isoformat() == "2026-10-15T12:00:00+00:00"


@patch("lp_bug_monitor.cli.get_launchpad")
@patch("lp_bug_monitor.cli.save_state")
@patch("lp_bug_monitor.cli.generate_html_report")
def test_main_no_scan_cli_packages_override(mock_generate_html, mock_save_state, mock_get_lp, tmp_path: Path):
    state_file = tmp_path / "bugs-state.json"
    state_data = {
        "last_scan_utc": "2026-10-15T12:00:00+00:00",
        "packages": ["linux-firmware"],
        "bugs": {},
    }
    state_file.write_text(json.dumps(state_data), encoding="utf-8")

    exit_code = main(["systemd", "udev", "--no-scan", "--state-file", str(state_file)])
    assert exit_code == 0
    assert not mock_get_lp.called
    assert mock_generate_html.called
    assert mock_generate_html.call_args.kwargs["packages_scanned"] == ["systemd", "udev"]


@patch("lp_bug_monitor.cli.get_launchpad")
@patch("lp_bug_monitor.cli.save_state")
@patch("lp_bug_monitor.cli.generate_html_report")
def test_main_no_scan_with_json_export(mock_generate_html, mock_save_state, mock_get_lp, tmp_path: Path):
    state_file = tmp_path / "bugs-state.json"
    json_out = tmp_path / "exported.json"
    state_data = {
        "last_scan_utc": "2026-10-15T12:00:00+00:00",
        "packages": ["linux-firmware"],
        "bugs": {"456": {"id": 456, "package": "linux-firmware", "title": "Firmware error"}},
    }
    state_file.write_text(json.dumps(state_data), encoding="utf-8")

    exit_code = main(["--no-scan", "--state-file", str(state_file), "--json", str(json_out)])
    assert exit_code == 0
    assert json_out.is_file()
    exported = json.loads(json_out.read_text(encoding="utf-8"))
    assert "456" in exported["bugs"]


@patch("lp_bug_monitor.cli.get_launchpad")
@patch("lp_bug_monitor.cli.get_ubuntu_distribution")
@patch("lp_bug_monitor.cli.get_active_series")
@patch("lp_bug_monitor.cli.save_state")
@patch("lp_bug_monitor.cli.generate_html_report")
@patch("lp_bug_monitor.cli.scan_full")
@patch("lp_bug_monitor.cli.scan_incremental")
@patch("lp_bug_monitor.cli.load_state")
def test_packages_added_triggers_auto_full_scan(
    mock_load_state,
    mock_scan_incremental,
    mock_scan_full,
    mock_generate_html,
    mock_save_state,
    mock_get_series,
    mock_get_distro,
    mock_get_lp,
):
    mock_load_state.return_value = {
        "last_scan_utc": "2026-10-14T10:00:00+00:00",
        "packages": ["linux-firmware"],
        "bugs": {},
    }
    mock_scan_full.return_value = {}

    exit_code = main(["linux-firmware", "systemd", "--dry-run"])
    assert exit_code == 0
    assert mock_scan_full.called
    assert not mock_scan_incremental.called


@patch("lp_bug_monitor.cli.get_launchpad")
@patch("lp_bug_monitor.cli.get_ubuntu_distribution")
@patch("lp_bug_monitor.cli.get_active_series")
@patch("lp_bug_monitor.cli.save_state")
@patch("lp_bug_monitor.cli.generate_html_report")
@patch("lp_bug_monitor.cli.scan_full")
@patch("lp_bug_monitor.cli.scan_incremental")
@patch("lp_bug_monitor.cli.load_state")
def test_packages_removed_triggers_auto_full_scan(
    mock_load_state,
    mock_scan_incremental,
    mock_scan_full,
    mock_generate_html,
    mock_save_state,
    mock_get_series,
    mock_get_distro,
    mock_get_lp,
):
    mock_load_state.return_value = {
        "last_scan_utc": "2026-10-14T10:00:00+00:00",
        "packages": ["linux-firmware", "systemd"],
        "bugs": {},
    }
    mock_scan_full.return_value = {}

    exit_code = main(["linux-firmware", "--dry-run"])
    assert exit_code == 0
    assert mock_scan_full.called
    assert not mock_scan_incremental.called


@patch("lp_bug_monitor.cli.get_launchpad")
@patch("lp_bug_monitor.cli.get_ubuntu_distribution")
@patch("lp_bug_monitor.cli.get_active_series")
@patch("lp_bug_monitor.cli.save_state")
@patch("lp_bug_monitor.cli.generate_html_report")
@patch("lp_bug_monitor.cli.scan_full")
@patch("lp_bug_monitor.cli.scan_incremental")
@patch("lp_bug_monitor.cli.load_state")
def test_packages_unchanged_keeps_incremental_scan(
    mock_load_state,
    mock_scan_incremental,
    mock_scan_full,
    mock_generate_html,
    mock_save_state,
    mock_get_series,
    mock_get_distro,
    mock_get_lp,
):
    mock_load_state.return_value = {
        "last_scan_utc": "2026-10-14T10:00:00+00:00",
        "packages": ["linux-firmware"],
        "bugs": {},
    }
    mock_scan_incremental.return_value = {}

    exit_code = main(["linux-firmware", "--dry-run"])
    assert exit_code == 0
    assert mock_scan_incremental.called
    assert not mock_scan_full.called
    assert mock_generate_html.called
    assert mock_generate_html.call_args.kwargs["workflow_url"] == DEFAULT_WORKFLOW_URL
