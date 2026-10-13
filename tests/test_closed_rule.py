"""Tests verifying the rule: 'A closed bug can not have any non-closed bug tasks'."""

from __future__ import annotations

from lp_bug_monitor.scanner import BugRecord, TaskRecord, is_bug_closed


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
