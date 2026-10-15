"""Tests for CLI argument parsing and package file resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from lp_bug_monitor.cli import create_parser, load_packages_from_file, parse_args, resolve_packages


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
            "--verbose",
        ]
    )
    assert args.output == Path("custom.html")
    assert args.state_file == Path("custom_state.json")
    assert args.title == "Kernel Bugs"
    assert args.full
    assert args.series == ["noble", "jammy"]
    assert args.verbose
