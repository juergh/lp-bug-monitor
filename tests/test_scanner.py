"""Tests for incremental scan updates and state transitions."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from lp_bug_monitor.scanner import scan_incremental


def test_scan_incremental_removes_newly_closed_bugs():
    ubuntu_mock = MagicMock()
    sp_mock = MagicMock()
    ubuntu_mock.getSourcePackage.return_value = sp_mock
    ubuntu_mock.getSeries.return_value = None

    # Existing state with bug 100
    existing_bugs = {
        "100": {
            "id": 100,
            "title": "Existing Bug",
            "package": "linux-firmware",
            "tasks": [
                {
                    "target": "linux-firmware (Ubuntu)",
                    "status": "In Progress",
                    "is_complete": False,
                }
            ],
        }
    }

    # Simulate bug 100 now having all tasks closed
    closed_task_1 = MagicMock()
    closed_task_1.bug_target_name = "linux-firmware (Ubuntu)"
    closed_task_1.bug_target_display_name = "linux-firmware (Ubuntu)"
    closed_task_1.status = "Fix Released"
    closed_task_1.is_complete = True
    closed_task_1.assignee = None
    closed_task_1.web_link = "https://bugs.launchpad.net/bugs/100"
    closed_task_1.date_created = None
    closed_task_1.date_closed = None

    bug_100 = MagicMock()
    bug_100.id = 100
    bug_100.title = "Existing Bug"
    bug_100.bug_tasks = [closed_task_1]
    bug_100.activity = []

    modified_task = MagicMock()
    modified_task.bug = bug_100
    sp_mock.searchTasks.return_value = [modified_task]

    updated = scan_incremental(
        ubuntu=ubuntu_mock,
        packages=["linux-firmware"],
        series_list=[],
        existing_bugs=existing_bugs,
        since_utc=datetime.now(UTC),
    )

    # Bug 100 should be removed from updated state
    assert "100" not in updated
    assert len(updated) == 0


def test_scan_incremental_adds_new_bug():
    ubuntu_mock = MagicMock()
    sp_mock = MagicMock()
    ubuntu_mock.getSourcePackage.return_value = sp_mock
    ubuntu_mock.getSeries.return_value = None

    existing_bugs = {}

    open_task = MagicMock()
    open_task.bug_target_name = "linux-firmware (Ubuntu)"
    open_task.bug_target_display_name = "linux-firmware (Ubuntu)"
    open_task.status = "New"
    open_task.is_complete = False
    open_task.assignee = None
    open_task.web_link = "https://bugs.launchpad.net/bugs/200"
    open_task.date_created = None
    open_task.date_closed = None

    bug_200 = MagicMock()
    bug_200.id = 200
    bug_200.title = "Brand New Bug"
    bug_200.web_link = "https://bugs.launchpad.net/bugs/200"
    bug_200.bug_tasks = [open_task]
    bug_200.activity = []
    bug_200.date_created = datetime.now(UTC)
    bug_200.date_last_updated = datetime.now(UTC)
    bug_200.date_last_message = None
    bug_200.owner = None
    bug_200.tags = []

    modified_task = MagicMock()
    modified_task.bug = bug_200
    sp_mock.searchTasks.return_value = [modified_task]

    updated = scan_incremental(
        ubuntu=ubuntu_mock,
        packages=["linux-firmware"],
        series_list=[],
        existing_bugs=existing_bugs,
        since_utc=datetime.now(UTC),
    )

    assert "200" in updated
    assert updated["200"]["title"] == "Brand New Bug"
    assert len(updated["200"]["tasks"]) == 1
    assert updated["200"]["tasks"][0]["status"] == "New"
