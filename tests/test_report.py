"""Tests for HTML report generation."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lp_bug_monitor.report import generate_html_report, get_bug_packages


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
    assert "Open Bug on Launchpad" not in content
    assert "Created (UTC)" in content
    assert "2026-04-10 03:11" in content
    assert 'data-created="2026-04-10T03:11:23+00:00"' in content
    assert "sortTable('created')" in content
    assert "sortTable('flame')" in content
    assert "col-flame" in content
    assert "data-flame" in content
    assert "Importance" in content
    assert "filter-series" in content
    assert '<option value="noble">noble (1)</option>' in content
    assert '<option value="questing">' not in content
    assert 'data-series="[&quot;noble&quot;]"' in content


def test_generate_html_report_with_info_added_flag(tmp_path: Path):
    out_file = tmp_path / "info_added.html"
    bugs = {
        "999": {
            "id": 999,
            "title": "Needs info bug",
            "package": "linux-firmware",
            "has_activity_after_incomplete": True,
            "tasks": [
                {
                    "target": "linux-firmware (Ubuntu)",
                    "status": "Incomplete",
                    "importance": "High",
                    "is_complete": False,
                }
            ],
        }
    }
    generate_html_report(bugs=bugs, output_path=out_file)
    content = out_file.read_text(encoding="utf-8")
    assert "⚠️ Info Added" in content
    assert 'data-info-added="true"' in content
    assert "__info_added__" in content


def test_generate_html_report_series_filter_option_a(tmp_path: Path):
    out_file = tmp_path / "series_report.html"
    bugs = {
        "101": {
            "id": 101,
            "title": "Bug active in noble, fixed in jammy",
            "package": "linux-firmware",
            "tasks": [
                {
                    "target": "linux-firmware (Ubuntu Noble)",
                    "status": "In Progress",
                    "is_complete": False,
                },
                {
                    "target": "linux-firmware (Ubuntu Jammy)",
                    "status": "Fix Released",
                    "is_complete": True,
                },
            ],
        },
        "102": {
            "id": 102,
            "title": "Bug active in jammy, fixed in noble",
            "package": "linux-firmware",
            "tasks": [
                {
                    "target": "linux-firmware (Ubuntu Noble)",
                    "status": "Fix Released",
                    "is_complete": True,
                },
                {
                    "target": "linux-firmware (Ubuntu Jammy)",
                    "status": "Triaged",
                    "is_complete": False,
                },
            ],
        },
        "103": {
            "id": 103,
            "title": "Bug without any series nominations",
            "package": "linux-firmware",
            "tasks": [
                {
                    "target": "linux-firmware (Ubuntu)",
                    "status": "Confirmed",
                    "is_complete": False,
                },
            ],
        },
    }
    generate_html_report(bugs=bugs, output_path=out_file)
    content = out_file.read_text(encoding="utf-8")

    # Both series exist with count 1 (Option A: only open tasks count)
    assert '<option value="jammy">jammy (1)</option>' in content
    assert '<option value="noble">noble (1)</option>' in content
    assert '<option value="__none__">No nominations (1)</option>' in content

    # Row 101 only targets noble; row 102 only targets jammy; row 103 has no series
    assert 'id="row-101"' in content
    assert 'data-series="[&quot;noble&quot;]"' in content
    assert 'id="row-102"' in content
    assert 'data-series="[&quot;jammy&quot;]"' in content
    assert 'id="row-103"' in content
    assert 'data-series="[]"' in content


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


def test_generate_html_report_with_workflow_url(tmp_path: Path):
    out_file = tmp_path / "wf_url.html"
    wf_url = "https://github.com/juergh/lp-bug-monitor/actions/workflows/sync.yaml"
    generate_html_report(
        bugs={},
        output_path=out_file,
        workflow_url=wf_url,
    )
    assert out_file.is_file()
    content = out_file.read_text(encoding="utf-8")
    assert f'via <a href="{wf_url}" target="_blank" rel="noopener">GitHub Action</a>.' in content
    assert f'href="{wf_url}"' in content
    assert 'id="btn-regenerate"' in content
    assert "🔄 Regenerate ↗" in content


def test_generate_html_report_without_workflow_url(tmp_path: Path):
    out_file = tmp_path / "no_wf_url.html"
    generate_html_report(
        bugs={},
        output_path=out_file,
        workflow_url=None,
    )
    assert out_file.is_file()
    content = out_file.read_text(encoding="utf-8")
    assert "GitHub Action" not in content
    assert "btn-regenerate" not in content
    assert "🔄 Regenerate ↗" not in content


def test_get_bug_packages():
    # Bug with stale linux-firmware in packages, but open task on linux-firmware-intel-wireless
    bug_retargeted = {
        "id": 2160682,
        "package": "linux-firmware",
        "packages": ["linux-firmware", "linux-firmware-intel-wireless"],
        "tasks": [
            {
                "target": "linux (Ubuntu)",
                "status": "Incomplete",
                "is_complete": False,
            },
            {
                "target": "linux-firmware-intel-wireless (Ubuntu)",
                "status": "Incomplete",
                "is_complete": False,
            },
        ],
    }
    assert get_bug_packages(bug_retargeted) == ["linux-firmware-intel-wireless"]

    # Bug with multiple active packages
    bug_multi = {
        "id": 200,
        "package": "pkg-a",
        "packages": ["pkg-a", "pkg-b"],
        "tasks": [
            {"target": "pkg-a (Ubuntu)", "status": "New", "is_complete": False},
            {"target": "pkg-b (Ubuntu)", "status": "New", "is_complete": False},
        ],
    }
    assert get_bug_packages(bug_multi) == ["pkg-a", "pkg-b"]


def test_generate_html_report_retargeted_package_display(tmp_path: Path):
    out_file = tmp_path / "retargeted.html"
    bugs = {
        "2160682": {
            "id": 2160682,
            "title": "Nova Lake WiFi firmware",
            "package": "linux-firmware",
            "packages": ["linux-firmware", "linux-firmware-intel-wireless"],
            "tasks": [
                {
                    "target": "linux-firmware-intel-wireless (Ubuntu)",
                    "status": "Incomplete",
                    "is_complete": False,
                }
            ],
        }
    }
    generate_html_report(bugs=bugs, output_path=out_file)
    content = out_file.read_text(encoding="utf-8")

    # Table column and row metadata must show linux-firmware-intel-wireless, NOT linux-firmware
    assert '<span class="package-pill">linux-firmware-intel-wireless</span>' in content
    assert '<span class="package-pill">linux-firmware</span>' not in content
    assert 'data-package="linux-firmware-intel-wireless"' in content
    assert 'data-packages="[&quot;linux-firmware-intel-wireless&quot;]"' in content
    assert '<option value="linux-firmware-intel-wireless">linux-firmware-intel-wireless</option>' in content
    assert '<option value="linux-firmware">linux-firmware</option>' not in content
