"""Tests for HTML report generation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lp_bug_monitor.report import generate_html_report


def test_generate_html_report_empty(tmp_path: Path):
    out_file = tmp_path / "empty.html"
    generate_html_report(bugs={}, output_path=out_file)
    assert out_file.is_file()
    content = out_file.read_text(encoding="utf-8")
    assert "Ubuntu Bug Status (0 packages)" in content
    assert "No open bugs found!" in content


def test_generate_html_report_custom_title(tmp_path: Path):
    out_file = tmp_path / "custom_title.html"
    generate_html_report(bugs={}, output_path=out_file, title="Custom Kernel Tracker")
    assert out_file.is_file()
    content = out_file.read_text(encoding="utf-8")
    assert "Custom Kernel Tracker" in content


def test_generate_html_report_with_bugs(tmp_path: Path):
    out_file = tmp_path / "report.html"
    bugs = {
        "2147678": {
            "id": 2147678,
            "title": "linux-firmware: Add Lenovo ISH firmware",
            "web_link": "https://bugs.launchpad.net/bugs/2147678",
            "package": "linux-firmware",
            "date_created": "2026-04-10T03:11:23+00:00",
            "date_last_updated": "2026-07-10T16:14:37+00:00",
            "last_activity_time": "2026-07-10T16:14:37+00:00",
            "last_activity_summary": "linux-firmware (Noble): status changed to In Progress",
            "owner": "Aaron Ma",
            "tags": ["kernel-daily-bug", "oem-priority"],
            "tasks": [
                {
                    "target": "linux-firmware (Ubuntu)",
                    "target_display": "linux-firmware (Ubuntu)",
                    "status": "In Progress",
                    "is_complete": False,
                    "assignee": None,
                    "web_link": "https://bugs.launchpad.net/ubuntu/+source/linux-firmware/+bug/2147678",
                },
                {
                    "target": "linux-firmware (Ubuntu Noble)",
                    "target_display": "linux-firmware (Ubuntu Noble)",
                    "status": "In Progress",
                    "is_complete": False,
                    "assignee": "Aaron Ma",
                    "web_link": "https://bugs.launchpad.net/ubuntu/noble/+source/linux-firmware/+bug/2147678",
                },
                {
                    "target": "linux-firmware (Ubuntu Questing)",
                    "target_display": "linux-firmware (Ubuntu Questing)",
                    "status": "Won't Fix",
                    "is_complete": True,
                    "assignee": None,
                    "web_link": "",
                },
            ],
        }
    }

    scan_time = datetime(2026, 10, 13, 10, 0, 0, tzinfo=UTC)
    generate_html_report(
        bugs=bugs,
        output_path=out_file,
        scan_time_utc=scan_time,
        packages_scanned=["linux-firmware"],
    )

    assert out_file.is_file()
    content = out_file.read_text(encoding="utf-8")

    # Verify key details
    assert "Ubuntu Bug Status (1 package)" in content
    assert "#2147678" in content
    assert "linux-firmware: Add Lenovo ISH firmware" in content
    assert "Aaron Ma" in content
    assert "kernel-daily-bug" in content
    assert "toggleDetails(2147678)" in content
    assert "2 Open" in content
    assert "1 Closed" in content
    assert "details-2147678" in content
    assert "row-2147678" in content
    # Ensure importance is NOT in the HTML
    assert "importance" not in content.lower()


def test_generate_html_report_multiple_packages(tmp_path: Path):
    out_file = tmp_path / "multi_pkgs.html"
    generate_html_report(
        bugs={},
        output_path=out_file,
        packages_scanned=["linux-firmware", "systemd", "udev"],
    )
    assert out_file.is_file()
    content = out_file.read_text(encoding="utf-8")
    assert "Ubuntu Bug Status (3 packages)" in content
