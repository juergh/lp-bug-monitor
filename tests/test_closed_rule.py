"""Tests verifying the rule: 'A closed bug can not have any non-closed bug tasks'."""

from __future__ import annotations

from unittest.mock import MagicMock

from lp_bug_monitor.scanner import BugRecord, TaskRecord, extract_bug_record, is_bug_closed, is_ubuntu_task


def test_single_open_task_is_not_closed():
    task = TaskRecord(
        target="linux-firmware (Ubuntu)",
        target_display="linux-firmware (Ubuntu)",
        status="In Progress",
        is_complete=False,
    )
    assert not is_bug_closed([task])


def test_single_closed_task_is_closed():
    task = TaskRecord(
        target="linux-firmware (Ubuntu)",
        target_display="linux-firmware (Ubuntu)",
        status="Fix Released",
        is_complete=True,
    )
    assert is_bug_closed([task])


def test_all_tasks_complete_is_closed():
    tasks = [
        TaskRecord(target="linux-firmware (Ubuntu)", target_display="Ubuntu", status="Fix Released", is_complete=True),
        TaskRecord(
            target="linux-firmware (Ubuntu Noble)", target_display="Noble", status="Fix Released", is_complete=True
        ),
        TaskRecord(
            target="linux-firmware (Ubuntu Jammy)", target_display="Jammy", status="Won't Fix", is_complete=True
        ),
        TaskRecord(target="upstream", target_display="Upstream", status="Invalid", is_complete=True),
    ]
    assert is_bug_closed(tasks)


def test_multi_task_one_open_is_not_closed():
    """Even if distro task is Fix Released, if Noble task is In Progress, bug is NOT closed."""
    tasks = [
        TaskRecord(target="linux-firmware (Ubuntu)", target_display="Ubuntu", status="Fix Released", is_complete=True),
        TaskRecord(
            target="linux-firmware (Ubuntu Noble)", target_display="Noble", status="In Progress", is_complete=False
        ),
        TaskRecord(
            target="linux-firmware (Ubuntu Jammy)", target_display="Jammy", status="Won't Fix", is_complete=True
        ),
    ]
    assert not is_bug_closed(tasks)


def test_dict_tasks_support():
    tasks = [
        {"target": "linux-firmware (Ubuntu)", "status": "Fix Released", "is_complete": True},
        {"target": "linux-firmware (Ubuntu Noble)", "status": "Confirmed", "is_complete": False},
    ]
    assert not is_bug_closed(tasks)

    tasks_all_closed = [
        {"target": "linux-firmware (Ubuntu)", "status": "Fix Released", "is_complete": True},
        {"target": "linux-firmware (Ubuntu Noble)", "status": "Expired", "is_complete": True},
    ]
    assert is_bug_closed(tasks_all_closed)


def test_bug_record_properties():
    tasks = [
        TaskRecord(target="linux-firmware (Ubuntu)", target_display="Ubuntu", status="Fix Released", is_complete=True),
        TaskRecord(
            target="linux-firmware (Ubuntu Noble)", target_display="Noble", status="In Progress", is_complete=False
        ),
    ]
    bug = BugRecord(
        id=12345,
        title="Test Bug",
        web_link="https://bugs.launchpad.net/bugs/12345",
        package="linux-firmware",
        tasks=tasks,
    )
    assert not bug.is_closed
    assert len(bug.open_tasks) == 1
    assert bug.open_tasks[0].status == "In Progress"
    assert len(bug.closed_tasks) == 1
    assert bug.closed_tasks[0].status == "Fix Released"


def test_is_ubuntu_task_distinguishes_targets():
    ubuntu_task = TaskRecord(
        target="linux-firmware (Ubuntu)",
        target_display="linux-firmware (Ubuntu)",
        status="New",
        is_complete=False,
    )
    series_task = TaskRecord(
        target="linux-firmware (Ubuntu Noble)",
        target_display="Noble",
        status="New",
        is_complete=False,
    )
    upstream_task = TaskRecord(
        target="upstream",
        target_display="Upstream",
        status="New",
        is_complete=False,
    )
    product_task = TaskRecord(
        target="linux-firmware",
        target_display="linux-firmware",
        status="New",
        is_complete=False,
    )
    debian_task = TaskRecord(
        target="linux-firmware (Debian)",
        target_display="Debian",
        status="New",
        is_complete=False,
    )

    assert is_ubuntu_task(ubuntu_task) is True
    assert is_ubuntu_task(series_task) is True
    assert is_ubuntu_task(upstream_task) is False
    assert is_ubuntu_task(product_task) is False
    assert is_ubuntu_task(debian_task) is False


def test_open_upstream_task_ignored_when_ubuntu_tasks_closed():
    """Bug is closed if all Ubuntu tasks are complete, even if upstream task is still open."""
    tasks = [
        TaskRecord(target="linux-firmware (Ubuntu)", target_display="Ubuntu", status="Fix Released", is_complete=True),
        TaskRecord(target="upstream", target_display="Upstream", status="In Progress", is_complete=False),
    ]
    assert is_bug_closed(tasks) is True


def test_extract_bug_record_filters_non_ubuntu_tasks():
    mock_ubuntu_task = MagicMock()
    mock_ubuntu_task.bug_target_name = "linux-firmware (Ubuntu)"
    mock_ubuntu_task.bug_target_display_name = "linux-firmware (Ubuntu)"
    mock_ubuntu_task.status = "In Progress"
    mock_ubuntu_task.is_complete = False
    mock_ubuntu_task.assignee = None
    mock_ubuntu_task.web_link = "https://bugs.launchpad.net/ubuntu/+source/linux-firmware/+bug/123"
    mock_ubuntu_task.date_created = None
    mock_ubuntu_task.date_closed = None

    mock_upstream_task = MagicMock()
    mock_upstream_task.bug_target_name = "upstream"
    mock_upstream_task.bug_target_display_name = "Upstream"
    mock_upstream_task.status = "In Progress"
    mock_upstream_task.is_complete = False
    mock_upstream_task.assignee = None
    mock_upstream_task.web_link = "https://bugs.launchpad.net/upstream/+bug/123"
    mock_upstream_task.date_created = None
    mock_upstream_task.date_closed = None

    mock_bug = MagicMock()
    mock_bug.id = 123
    mock_bug.title = "Firmware issue"
    mock_bug.duplicate_of_link = None
    mock_bug.bug_tasks = [mock_ubuntu_task, mock_upstream_task]
    mock_bug.activity = []
    mock_bug.date_created = None
    mock_bug.date_last_updated = None
    mock_bug.date_last_message = None
    mock_bug.owner = None
    mock_bug.tags = []

    record = extract_bug_record(mock_bug, matched_packages={"linux-firmware"})
    assert record is not None
    assert len(record.tasks) == 1
    assert record.tasks[0].target == "linux-firmware (Ubuntu)"


def test_extract_bug_record_none_if_all_ubuntu_tasks_closed():
    mock_ubuntu_task = MagicMock()
    mock_ubuntu_task.bug_target_name = "linux-firmware (Ubuntu)"
    mock_ubuntu_task.bug_target_display_name = "linux-firmware (Ubuntu)"
    mock_ubuntu_task.status = "Fix Released"
    mock_ubuntu_task.is_complete = True
    mock_ubuntu_task.assignee = None
    mock_ubuntu_task.web_link = "https://bugs.launchpad.net/ubuntu/+source/linux-firmware/+bug/124"
    mock_ubuntu_task.date_created = None
    mock_ubuntu_task.date_closed = None

    mock_upstream_task = MagicMock()
    mock_upstream_task.bug_target_name = "upstream"
    mock_upstream_task.bug_target_display_name = "Upstream"
    mock_upstream_task.status = "In Progress"
    mock_upstream_task.is_complete = False
    mock_upstream_task.assignee = None
    mock_upstream_task.web_link = "https://bugs.launchpad.net/upstream/+bug/124"
    mock_upstream_task.date_created = None
    mock_upstream_task.date_closed = None

    mock_bug = MagicMock()
    mock_bug.id = 124
    mock_bug.title = "Closed in Ubuntu"
    mock_bug.duplicate_of_link = None
    mock_bug.bug_tasks = [mock_ubuntu_task, mock_upstream_task]

    record = extract_bug_record(mock_bug, matched_packages={"linux-firmware"})
    assert record is None


def _make_open_ubuntu_task():
    task = MagicMock()
    task.bug_target_name = "linux-firmware (Ubuntu)"
    task.bug_target_display_name = "linux-firmware (Ubuntu)"
    task.status = "Confirmed"
    task.is_complete = False
    task.assignee = None
    task.web_link = "https://bugs.launchpad.net/ubuntu/+source/linux-firmware/+bug/2141209"
    task.date_created = None
    task.date_closed = None
    return task


def test_extract_bug_record_none_if_marked_duplicate():
    """Bug 2141209 case: all Ubuntu tasks are still open (Confirmed), but the
    bug was marked as a duplicate of another bug. It must be treated as closed."""
    mock_bug = MagicMock()
    mock_bug.id = 2141209
    mock_bug.title = "no sound after update"
    mock_bug.duplicate_of_link = "https://api.launchpad.net/1.0/bugs/2141223"
    mock_bug.bug_tasks = [_make_open_ubuntu_task()]

    record = extract_bug_record(mock_bug, matched_packages={"linux-firmware"})
    assert record is None


def test_extract_bug_record_keeps_bug_without_duplicate_link():
    mock_bug = MagicMock()
    mock_bug.id = 2141223
    mock_bug.title = "Master bug"
    mock_bug.duplicate_of_link = None
    mock_bug.bug_tasks = [_make_open_ubuntu_task()]
    mock_bug.activity = []
    mock_bug.date_created = None
    mock_bug.date_last_updated = None
    mock_bug.date_last_message = None
    mock_bug.owner = None
    mock_bug.tags = []

    record = extract_bug_record(mock_bug, matched_packages={"linux-firmware"})
    assert record is not None
    assert record.id == 2141223
