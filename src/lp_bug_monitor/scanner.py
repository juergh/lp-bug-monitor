"""Bug task scanning, extraction, filtering, and state merging."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

ALL_LAUNCHPAD_STATUSES = [
    "New",
    "Incomplete",
    "Opinion",
    "Invalid",
    "Won't Fix",
    "Expired",
    "Confirmed",
    "Triaged",
    "In Progress",
    "Fix Committed",
    "Fix Released",
]

CLOSED_STATUSES = {
    "Fix Released",
    "Invalid",
    "Won't Fix",
    "Expired",
    "Opinion",
}


@dataclass
class TaskRecord:
    """Record representing a single Launchpad bug task."""

    target: str
    target_display: str
    status: str
    is_complete: bool
    importance: str = "Undecided"
    assignee: str | None = None
    web_link: str = ""
    date_created: str | None = None
    date_closed: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskRecord:
        return cls(
            target=data.get("target", ""),
            target_display=data.get("target_display", data.get("target", "")),
            status=data.get("status", "Unknown"),
            is_complete=data.get("is_complete", False),
            importance=data.get("importance", "Undecided"),
            assignee=data.get("assignee"),
            web_link=data.get("web_link", ""),
            date_created=data.get("date_created"),
            date_closed=data.get("date_closed"),
        )


@dataclass
class BugRecord:
    """Record representing an aggregated Launchpad bug."""

    id: int
    title: str
    web_link: str
    package: str
    packages: list[str] = field(default_factory=list)
    date_created: str = ""
    date_last_updated: str = ""
    last_activity_time: str = ""
    last_activity_summary: str | None = None
    owner: str = ""
    tags: list[str] = field(default_factory=list)
    tasks: list[TaskRecord] = field(default_factory=list)
    has_activity_after_incomplete: bool = False

    @property
    def open_tasks(self) -> list[TaskRecord]:
        return [t for t in self.tasks if not t.is_complete]

    @property
    def closed_tasks(self) -> list[TaskRecord]:
        return [t for t in self.tasks if t.is_complete]

    @property
    def is_closed(self) -> bool:
        """A closed bug can not have any non-closed bug tasks."""
        return is_bug_closed(self.tasks)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["tasks"] = [t.to_dict() for t in self.tasks]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BugRecord:
        tasks = [TaskRecord.from_dict(t) for t in data.get("tasks", [])]
        return cls(
            id=int(data["id"]),
            title=data.get("title", ""),
            web_link=data.get("web_link", f"https://bugs.launchpad.net/bugs/{data['id']}"),
            package=data.get("package", "unknown"),
            packages=data.get("packages", [data.get("package", "unknown")]),
            date_created=data.get("date_created", ""),
            date_last_updated=data.get("date_last_updated", ""),
            last_activity_time=data.get("last_activity_time", data.get("date_last_updated", "")),
            last_activity_summary=data.get("last_activity_summary"),
            owner=data.get("owner", "Unknown"),
            tags=data.get("tags", []),
            tasks=tasks,
            has_activity_after_incomplete=bool(data.get("has_activity_after_incomplete", False)),
        )


def is_ubuntu_task(task: Any) -> bool:
    """Determine whether a bug task is targeted at Ubuntu or an Ubuntu series.

    Non-Ubuntu tasks (upstream projects, other distributions) are ignored.
    """
    if isinstance(task, TaskRecord):
        target = task.target
        target_display = task.target_display
        web_link = task.web_link
    elif isinstance(task, dict):
        target = str(task.get("target", ""))
        target_display = str(task.get("target_display", ""))
        web_link = str(task.get("web_link", ""))
    else:
        target = str(getattr(task, "bug_target_name", "") or "")
        target_display = str(getattr(task, "bug_target_display_name", "") or "")
        web_link = str(getattr(task, "web_link", "") or "")

    target_combined = f"{target} {target_display}".lower()
    if "(ubuntu" in target_combined:
        return True
    if target.strip().lower() == "ubuntu" or target_display.strip().lower() == "ubuntu":
        return True
    if "/ubuntu" in web_link.lower():
        return True

    distro_link = getattr(task, "distribution_link", None)
    if isinstance(distro_link, str) and "/ubuntu" in distro_link.lower():
        return True

    return False


def is_bug_closed(tasks: list[TaskRecord | dict[str, Any] | Any]) -> bool:
    """Determine if a bug is closed.

    Rule: Ignore non-Ubuntu tasks. A closed bug cannot have any non-closed Ubuntu bug tasks.
    Therefore, if ANY Ubuntu task is not complete, the bug is NOT closed.
    If all Ubuntu tasks are complete (or no Ubuntu tasks exist), the bug is considered closed.
    """
    ubuntu_tasks = [t for t in tasks if is_ubuntu_task(t)]
    if not ubuntu_tasks:
        return True

    for t in ubuntu_tasks:
        if isinstance(t, TaskRecord):
            complete = t.is_complete
        elif isinstance(t, dict):
            complete = t.get("is_complete", False)
        elif hasattr(t, "is_complete"):
            complete = bool(t.is_complete)
        else:
            status = getattr(t, "status", None) or (t.get("status") if isinstance(t, dict) else None)
            complete = status in CLOSED_STATUSES

        if not complete:
            return False

    return True


def extract_task_record(lp_task: Any) -> TaskRecord:
    """Extract a clean TaskRecord from a Launchpad bug_task object."""
    assignee_name: str | None = None
    try:
        if getattr(lp_task, "assignee", None):
            assignee_name = lp_task.assignee.display_name or lp_task.assignee.name
    except Exception:
        assignee_name = None

    date_created = None
    if getattr(lp_task, "date_created", None):
        date_created = lp_task.date_created.isoformat()

    date_closed = None
    if getattr(lp_task, "date_closed", None):
        date_closed = lp_task.date_closed.isoformat()

    importance = str(getattr(lp_task, "importance", "Undecided") or "Undecided")

    return TaskRecord(
        target=getattr(lp_task, "bug_target_name", ""),
        target_display=getattr(lp_task, "bug_target_display_name", getattr(lp_task, "bug_target_name", "")),
        status=getattr(lp_task, "status", "Unknown"),
        is_complete=bool(getattr(lp_task, "is_complete", False)),
        importance=importance,
        assignee=assignee_name,
        web_link=getattr(lp_task, "web_link", ""),
        date_created=date_created,
        date_closed=date_closed,
    )


def extract_last_activity(lp_bug: Any) -> tuple[str, str | None]:
    """Determine the timestamp and human-readable summary of the latest activity on a bug."""
    candidates: list[datetime] = []

    date_created = getattr(lp_bug, "date_created", None)
    if isinstance(date_created, datetime):
        candidates.append(date_created)

    date_updated = getattr(lp_bug, "date_last_updated", None)
    if isinstance(date_updated, datetime):
        candidates.append(date_updated)

    date_msg = getattr(lp_bug, "date_last_message", None)
    if isinstance(date_msg, datetime):
        candidates.append(date_msg)

    activity_summary: str | None = None
    try:
        activity_entries = list(getattr(lp_bug, "activity", []))
        if activity_entries:
            last = activity_entries[-1]
            if isinstance(last.datechanged, datetime):
                candidates.append(last.datechanged)
            who = ""
            if getattr(last, "person_link", None):
                who = last.person_link.split("~")[-1]
            change = getattr(last, "whatchanged", "")
            new_val = getattr(last, "newvalue", "") or ""
            if change:
                activity_summary = f"{change}: {new_val}" if new_val else f"{change} updated"
                if who:
                    activity_summary = f"{activity_summary} by {who}"
    except Exception as e:
        logger.debug("Could not fetch bug activity for #%s: %s", getattr(lp_bug, "id", "?"), e)

    latest_dt = max(candidates) if candidates else datetime.now(UTC)
    if not activity_summary:
        if date_msg and date_updated and date_msg >= date_updated:
            activity_summary = "New comment posted"
        else:
            activity_summary = "Bug details updated"

    return latest_dt.isoformat(), activity_summary


def detect_activity_after_incomplete(lp_bug: Any, task_records: list[TaskRecord]) -> bool:
    """Detect if activity occurred after an open task was marked Incomplete.

    This indicates someone may have provided requested information, requiring review.
    """
    has_open_incomplete = any(t.status.lower().startswith("incomplete") and not t.is_complete for t in task_records)
    if not has_open_incomplete:
        return False

    incomplete_dt: datetime | None = None
    try:
        activity_entries = list(getattr(lp_bug, "activity", []))
        for act in activity_entries:
            change = str(getattr(act, "whatchanged", "")).lower()
            new_val = str(getattr(act, "newvalue", "")).lower()
            if "status" in change and new_val.startswith("incomplete"):
                dt = getattr(act, "datechanged", None)
                if isinstance(dt, datetime):
                    if incomplete_dt is None or dt > incomplete_dt:
                        incomplete_dt = dt
    except Exception as e:
        logger.debug("Could not inspect activity for incomplete tasks on #%s: %s", getattr(lp_bug, "id", "?"), e)

    threshold = timedelta(seconds=60)

    if incomplete_dt is None:
        date_created = getattr(lp_bug, "date_created", None)
        date_msg = getattr(lp_bug, "date_last_message", None)
        if isinstance(date_msg, datetime) and isinstance(date_created, datetime):
            return (date_msg - date_created).total_seconds() > 300
        return False

    date_msg = getattr(lp_bug, "date_last_message", None)
    if isinstance(date_msg, datetime) and (date_msg - incomplete_dt) > threshold:
        return True

    try:
        for act in getattr(lp_bug, "activity", []):
            act_dt = getattr(act, "datechanged", None)
            if isinstance(act_dt, datetime) and (act_dt - incomplete_dt) > threshold:
                return True
    except Exception:
        pass

    date_updated = getattr(lp_bug, "date_last_updated", None)
    if isinstance(date_updated, datetime) and (date_updated - incomplete_dt) > threshold:
        return True

    return False


def extract_bug_record(lp_bug: Any, matched_packages: set[str] | None = None) -> BugRecord | None:
    """Extract a BugRecord from a Launchpad bug object.

    Returns None if the bug is closed (i.e. has zero non-closed tasks).
    """
    raw_tasks = [t for t in getattr(lp_bug, "bug_tasks", []) if is_ubuntu_task(t)]
    task_records = [extract_task_record(t) for t in raw_tasks]

    # Enforce rule: Ignore closed bugs. A closed bug cannot have any non-closed Ubuntu bug tasks.
    if is_bug_closed(task_records):
        logger.debug("Bug #%s is closed (all Ubuntu tasks complete); ignoring", lp_bug.id)
        return None

    last_activity_time, last_activity_summary = extract_last_activity(lp_bug)
    has_activity_after_incomplete = detect_activity_after_incomplete(lp_bug, task_records)

    owner_name = "Unknown"
    try:
        if getattr(lp_bug, "owner", None):
            owner_name = lp_bug.owner.display_name or lp_bug.owner.name
    except Exception:
        pass

    tags = list(getattr(lp_bug, "tags", []))
    matched_pkgs = sorted(matched_packages) if matched_packages else ["unknown"]
    primary_pkg = matched_pkgs[0] if matched_pkgs else "unknown"

    date_created = getattr(lp_bug, "date_created", None)
    date_last_updated = getattr(lp_bug, "date_last_updated", None)

    return BugRecord(
        id=int(lp_bug.id),
        title=str(getattr(lp_bug, "title", "")),
        web_link=str(getattr(lp_bug, "web_link", f"https://bugs.launchpad.net/bugs/{lp_bug.id}")),
        package=primary_pkg,
        packages=matched_pkgs,
        date_created=date_created.isoformat() if isinstance(date_created, datetime) else "",
        date_last_updated=date_last_updated.isoformat() if isinstance(date_last_updated, datetime) else "",
        last_activity_time=last_activity_time,
        last_activity_summary=last_activity_summary,
        owner=owner_name,
        tags=tags,
        tasks=task_records,
        has_activity_after_incomplete=has_activity_after_incomplete,
    )


def scan_full(
    ubuntu: Any,
    packages: list[str],
    series_list: list[str],
) -> dict[str, dict[str, Any]]:
    """Perform a full scan for all non-closed bugs across specified packages and active series."""
    logger.info("Starting full scan across %d packages and %d series...", len(packages), len(series_list))
    bug_objects: dict[int, Any] = {}
    bug_matched_packages: dict[int, set[str]] = {}

    series_objects: list[Any] = []
    for s_name in series_list:
        try:
            s_obj = ubuntu.getSeries(name_or_version=s_name)
            if s_obj:
                series_objects.append(s_obj)
        except Exception as e:
            logger.debug("Series %s could not be loaded: %s", s_name, e)

    for idx, pkg_name in enumerate(packages, 1):
        logger.info("[%d/%d] Scanning open tasks for %s...", idx, len(packages), pkg_name)

        # 1. Distro-level package tasks
        try:
            sp = ubuntu.getSourcePackage(name=pkg_name)
            if sp:
                for task in sp.searchTasks():
                    bug = task.bug
                    b_id = int(bug.id)
                    bug_objects[b_id] = bug
                    bug_matched_packages.setdefault(b_id, set()).add(pkg_name)
        except Exception as e:
            logger.warning("Failed scanning distro tasks for %s: %s", pkg_name, e)

        # 2. Active series-level package tasks
        for s_obj in series_objects:
            try:
                s_sp = s_obj.getSourcePackage(name=pkg_name)
                if s_sp:
                    for task in s_sp.searchTasks():
                        bug = task.bug
                        b_id = int(bug.id)
                        bug_objects[b_id] = bug
                        bug_matched_packages.setdefault(b_id, set()).add(pkg_name)
            except Exception as e:
                logger.debug("Failed scanning %s on series %s: %s", pkg_name, getattr(s_obj, "name", "?"), e)

    logger.info("Found %d candidate bugs with open tasks. Extracting full bug records...", len(bug_objects))

    results: dict[str, dict[str, Any]] = {}
    for idx, (b_id, bug_obj) in enumerate(bug_objects.items(), 1):
        if idx % 10 == 0 or idx == len(bug_objects):
            logger.info("Processing bug records: %d/%d...", idx, len(bug_objects))

        matched_pkgs = bug_matched_packages.get(b_id, set())
        record = extract_bug_record(bug_obj, matched_pkgs)
        if record is not None:
            results[str(b_id)] = record.to_dict()

    logger.info("Full scan complete. %d non-closed bugs retained.", len(results))
    return results


def scan_incremental(
    ubuntu: Any,
    packages: list[str],
    series_list: list[str],
    existing_bugs: dict[str, dict[str, Any]],
    since_utc: datetime,
) -> dict[str, dict[str, Any]]:
    """Perform an incremental scan for bugs modified since `since_utc`.

    Updates modified bugs, adds new bugs, and removes bugs that have closed since the last scan.
    """
    logger.info("Starting incremental scan for changes since %s...", since_utc.isoformat())
    updated_bugs: dict[str, dict[str, Any]] = dict(existing_bugs)

    # Collect series objects
    series_objects: list[Any] = []
    for s_name in series_list:
        try:
            s_obj = ubuntu.getSeries(name_or_version=s_name)
            if s_obj:
                series_objects.append(s_obj)
        except Exception as e:
            logger.debug("Series %s could not be loaded: %s", s_name, e)

    modified_bug_objects: dict[int, Any] = {}
    bug_matched_packages: dict[int, set[str]] = {}

    for idx, pkg_name in enumerate(packages, 1):
        # 1. Distro-level tasks modified since last run (query all statuses to detect transitions to closed)
        try:
            sp = ubuntu.getSourcePackage(name=pkg_name)
            if sp:
                tasks = sp.searchTasks(modified_since=since_utc, status=ALL_LAUNCHPAD_STATUSES)
                for task in tasks:
                    bug = task.bug
                    b_id = int(bug.id)
                    modified_bug_objects[b_id] = bug
                    bug_matched_packages.setdefault(b_id, set()).add(pkg_name)
        except Exception as e:
            logger.warning("Incremental distro query failed for %s: %s", pkg_name, e)

        # 2. Active series-level tasks modified since last run
        for s_obj in series_objects:
            try:
                s_sp = s_obj.getSourcePackage(name=pkg_name)
                if s_sp:
                    tasks = s_sp.searchTasks(modified_since=since_utc, status=ALL_LAUNCHPAD_STATUSES)
                    for task in tasks:
                        bug = task.bug
                        b_id = int(bug.id)
                        modified_bug_objects[b_id] = bug
                        bug_matched_packages.setdefault(b_id, set()).add(pkg_name)
            except Exception as e:
                logger.debug(
                    "Incremental series query failed for %s on %s: %s",
                    pkg_name,
                    getattr(s_obj, "name", "?"),
                    e,
                )

    logger.info("Identified %d modified bugs since %s", len(modified_bug_objects), since_utc.isoformat())

    added_count = 0
    updated_count = 0
    closed_count = 0

    for b_id, bug_obj in modified_bug_objects.items():
        matched_pkgs = bug_matched_packages.get(b_id, set())
        # Preserve previous package matches if existing
        if str(b_id) in updated_bugs:
            prev_pkgs = updated_bugs[str(b_id)].get("packages", [])
            matched_pkgs.update(prev_pkgs)

        record = extract_bug_record(bug_obj, matched_pkgs)
        b_key = str(b_id)

        if record is None:
            # Bug is closed (all tasks complete)
            if b_key in updated_bugs:
                logger.info("Bug #%d has closed all tasks; removing from active bugs", b_id)
                del updated_bugs[b_key]
                closed_count += 1
        else:
            # Bug is non-closed; update or add
            if b_key in updated_bugs:
                updated_count += 1
            else:
                added_count += 1
            updated_bugs[b_key] = record.to_dict()

    logger.info(
        "Incremental update finished: %d added, %d updated, %d closed. Total active: %d",
        added_count,
        updated_count,
        closed_count,
        len(updated_bugs),
    )
    return updated_bugs
