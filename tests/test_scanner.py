"""Tests for incremental scan updates and state transitions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from lp_bug_monitor.scanner import (
    BugRecord,
    TaskRecord,
    detect_activity_after_incomplete,
    extract_bug_record,
    extract_package_name,
    extract_series_name,
    scan_incremental,
)


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


def test_task_record_importance():
    t = TaskRecord(
        target="linux-firmware (Ubuntu)",
        target_display="Ubuntu",
        status="New",
        is_complete=False,
        importance="High",
    )
    d = t.to_dict()
    assert d["importance"] == "High"
    restored = TaskRecord.from_dict(d)
    assert restored.importance == "High"


def test_bug_record_activity_after_incomplete_roundtrip():
    b = BugRecord(
        id=300,
        title="Incomplete test bug",
        web_link="https://bugs.launchpad.net/bugs/300",
        package="linux-firmware",
        has_activity_after_incomplete=True,
    )
    d = b.to_dict()
    assert d["has_activity_after_incomplete"] is True
    restored = BugRecord.from_dict(d)
    assert restored.has_activity_after_incomplete is True


def test_detect_activity_after_incomplete():
    now = datetime(2026, 10, 14, 12, 0, 0, tzinfo=UTC)
    incomplete_time = now - timedelta(hours=2)

    task = TaskRecord(
        target="linux-firmware (Ubuntu)",
        target_display="Ubuntu",
        status="Incomplete",
        is_complete=False,
    )

    act_entry = MagicMock()
    act_entry.whatchanged = "status: linux-firmware (Ubuntu)"
    act_entry.newvalue = "Incomplete"
    act_entry.datechanged = incomplete_time

    # Bug with a comment posted after it was marked incomplete
    bug_with_reply = MagicMock()
    bug_with_reply.activity = [act_entry]
    bug_with_reply.date_last_message = incomplete_time + timedelta(hours=1)
    bug_with_reply.date_last_updated = incomplete_time + timedelta(hours=1)

    assert detect_activity_after_incomplete(bug_with_reply, [task]) is True

    # Bug where no comment or activity occurred after incomplete
    bug_without_reply = MagicMock()
    bug_without_reply.activity = [act_entry]
    bug_without_reply.date_last_message = incomplete_time - timedelta(days=1)
    bug_without_reply.date_last_updated = incomplete_time

    assert detect_activity_after_incomplete(bug_without_reply, [task]) is False


def test_extract_series_name():
    assert extract_series_name("linux-firmware (Ubuntu Noble)") == "noble"
    assert extract_series_name("linux-firmware (Ubuntu Jammy)") == "jammy"
    assert extract_series_name("linux-firmware (Ubuntu)") is None
    assert extract_series_name("upstream") is None

    mock_task = MagicMock()
    mock_task.distro_series.name = "focal"
    assert extract_series_name(lp_task=mock_task) == "focal"

    mock_link_task = MagicMock()
    mock_link_task.distro_series = None
    mock_link_task.distro_series_link = "https://api.launchpad.net/1.0/ubuntu/plucky"
    assert extract_series_name(lp_task=mock_link_task) == "plucky"


def test_task_record_series():
    t = TaskRecord(
        target="linux-firmware (Ubuntu Noble)",
        target_display="Noble",
        status="In Progress",
        is_complete=False,
        series="noble",
    )
    d = t.to_dict()
    assert d["series"] == "noble"
    restored = TaskRecord.from_dict(d)
    assert restored.series == "noble"

    # Backward compatibility fallback from target string
    legacy_dict = {
        "target": "linux-firmware (Ubuntu Jammy)",
        "target_display": "Jammy",
        "status": "In Progress",
        "is_complete": False,
    }
    legacy_task = TaskRecord.from_dict(legacy_dict)
    assert legacy_task.series == "jammy"


def test_bug_record_open_series():
    t_noble = TaskRecord(
        target="linux-firmware (Ubuntu Noble)",
        target_display="Noble",
        status="In Progress",
        is_complete=False,
        series="noble",
    )
    t_jammy = TaskRecord(
        target="linux-firmware (Ubuntu Jammy)",
        target_display="Jammy",
        status="Fix Released",
        is_complete=True,
        series="jammy",
    )
    t_distro = TaskRecord(
        target="linux-firmware (Ubuntu)",
        target_display="Ubuntu",
        status="Fix Released",
        is_complete=True,
        series=None,
    )
    bug = BugRecord(
        id=500,
        title="Series bug",
        web_link="https://bugs.launchpad.net/bugs/500",
        package="linux-firmware",
        tasks=[t_noble, t_jammy, t_distro],
    )
    assert bug.open_series == ["noble"]
    assert bug.all_series == ["jammy", "noble"]


def test_extract_package_name():
    assert extract_package_name("linux-firmware (Ubuntu)") == "linux-firmware"
    assert extract_package_name("linux-firmware-intel-wireless (Ubuntu Noble)") == "linux-firmware-intel-wireless"
    assert extract_package_name("linux (Ubuntu)") == "linux"
    assert extract_package_name("upstream") is None
    assert extract_package_name("") is None

    mock_task = MagicMock()
    mock_task.source_package_name = "linux-firmware-intel-graphics"
    assert extract_package_name(lp_task=mock_task) == "linux-firmware-intel-graphics"


def test_scan_incremental_drops_stale_retargeted_package():
    ubuntu_mock = MagicMock()
    sp_mock = MagicMock()
    ubuntu_mock.getSourcePackage.return_value = sp_mock
    ubuntu_mock.getSeries.return_value = None

    # Bug 2160682 previously was recorded under linux-firmware
    existing_bugs = {
        "2160682": {
            "id": 2160682,
            "title": "Retargeted bug",
            "package": "linux-firmware",
            "packages": ["linux-firmware"],
            "tasks": [
                {
                    "target": "linux-firmware (Ubuntu)",
                    "status": "Incomplete",
                    "is_complete": False,
                }
            ],
        }
    }

    # On Launchpad, the task was retargeted to linux-firmware-intel-wireless
    retargeted_task = MagicMock()
    retargeted_task.bug_target_name = "linux-firmware-intel-wireless (Ubuntu)"
    retargeted_task.bug_target_display_name = "linux-firmware-intel-wireless (Ubuntu)"
    retargeted_task.status = "Incomplete"
    retargeted_task.is_complete = False
    retargeted_task.assignee = None
    retargeted_task.web_link = "https://bugs.launchpad.net/bugs/2160682"
    retargeted_task.date_created = None
    retargeted_task.date_closed = None

    bug_retargeted = MagicMock()
    bug_retargeted.id = 2160682
    bug_retargeted.title = "Retargeted bug"
    bug_retargeted.web_link = "https://bugs.launchpad.net/bugs/2160682"
    bug_retargeted.bug_tasks = [retargeted_task]
    bug_retargeted.activity = []
    bug_retargeted.date_created = datetime.now(UTC)
    bug_retargeted.date_last_updated = datetime.now(UTC)
    bug_retargeted.date_last_message = None
    bug_retargeted.owner = None
    bug_retargeted.tags = []

    modified_task = MagicMock()
    modified_task.bug = bug_retargeted
    sp_mock.searchTasks.return_value = [modified_task]

    updated = scan_incremental(
        ubuntu=ubuntu_mock,
        packages=["linux-firmware", "linux-firmware-intel-wireless"],
        series_list=[],
        existing_bugs=existing_bugs,
        since_utc=datetime.now(UTC),
    )

    assert "2160682" in updated
    assert updated["2160682"]["package"] == "linux-firmware-intel-wireless"
    assert updated["2160682"]["packages"] == ["linux-firmware-intel-wireless"]


def test_extract_bug_record_filters_stale_packages():
    open_task = MagicMock()
    open_task.bug_target_name = "linux-firmware-intel-wireless (Ubuntu Noble)"
    open_task.bug_target_display_name = "Noble"
    open_task.status = "Incomplete"
    open_task.is_complete = False
    open_task.assignee = None
    open_task.web_link = ""
    open_task.date_created = None
    open_task.date_closed = None

    lp_bug = MagicMock()
    lp_bug.id = 2160682
    lp_bug.title = "Firmware bug"
    lp_bug.web_link = "https://bugs.launchpad.net/bugs/2160682"
    lp_bug.bug_tasks = [open_task]
    lp_bug.activity = []
    lp_bug.date_created = datetime.now(UTC)
    lp_bug.date_last_updated = datetime.now(UTC)
    lp_bug.date_last_message = None
    lp_bug.owner = None
    lp_bug.tags = []

    # Suppose matched_packages had stale linux-firmware along with intel-wireless
    record = extract_bug_record(
        lp_bug,
        matched_packages={"linux-firmware", "linux-firmware-intel-wireless"},
    )
    assert record is not None
    assert record.package == "linux-firmware-intel-wireless"
    assert record.packages == ["linux-firmware-intel-wireless"]
