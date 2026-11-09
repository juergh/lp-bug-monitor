"""Command-line interface for Launchpad bug monitor."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from lp_bug_monitor.client import (
    DEFAULT_CACHE_DIR,
    get_active_series,
    get_launchpad,
    get_ubuntu_distribution,
)
from lp_bug_monitor.report import generate_html_report, generate_index_page
from lp_bug_monitor.scanner import scan_full, scan_incremental
from lp_bug_monitor.state import load_state, save_state

logger = logging.getLogger("lp_bug_monitor")

DEFAULT_WORKFLOW_URL = "https://github.com/juergh/lp-bug-monitor/actions/workflows/sync.yaml"


def load_packages_from_file(path: Path | str) -> list[str]:
    """Load source package names from a text file.

    Rules:
    - One package per line.
    - Ignore lines starting with '#'.
    - Strip inline comments (e.g. 'pkg # note' -> 'pkg').
    - Strip leading/trailing whitespace.
    - Ignore empty lines.
    """
    pkg_file = Path(path).expanduser().resolve()
    if not pkg_file.is_file():
        raise FileNotFoundError(f"Packages file not found: {pkg_file}")

    packages: set[str] = set()
    with pkg_file.open("r", encoding="utf-8") as f:
        for line in f:
            clean_line = line.split("#", 1)[0].strip()
            if clean_line:
                packages.add(clean_line)

    return sorted(packages)


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="lp-bug-monitor",
        description="Scan Launchpad bugs for specified Ubuntu source packages and generate an HTML status page.",
    )
    parser.add_argument(
        "pos_packages",
        nargs="*",
        metavar="PACKAGE",
        help="Ubuntu source packages to monitor (e.g. linux-firmware, systemd)",
    )
    parser.add_argument(
        "-p",
        "--packages",
        nargs="+",
        metavar="PACKAGE",
        help="Ubuntu source packages to monitor (alternative to positional arguments)",
    )
    parser.add_argument(
        "-f",
        "--packages-file",
        type=Path,
        metavar="FILE",
        help="Path to file containing source packages to monitor (one per line, # for comments)",
    )
    parser.add_argument(
        "-t",
        "--title",
        type=str,
        default=None,
        help="Custom title for the HTML status report dashboard",
    )
    parser.add_argument(
        "--workflow-url",
        type=str,
        default=DEFAULT_WORKFLOW_URL,
        help=f"URL to GitHub Action for manual regeneration and run history (default: {DEFAULT_WORKFLOW_URL})",
    )
    parser.add_argument(
        "--no-workflow-url",
        action="store_const",
        const=None,
        dest="workflow_url",
        help="Disable the GitHub Action link and Regenerate button in the HTML report",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("bugs.html"),
        help="Path for generated HTML status report (default: bugs.html)",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path("bugs-state.json"),
        help="Path to JSON state file for incremental scans (default: bugs-state.json)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Force a full scan from scratch instead of an incremental scan",
    )
    parser.add_argument(
        "--full-scan-interval",
        type=float,
        default=48.0,
        metavar="HOURS",
        help=(
            "Force a full scan if the last scan is older than this many hours "
            "(default: 48, 0 disables the periodic full scan)"
        ),
    )
    parser.add_argument(
        "--no-scan",
        "--report-only",
        action="store_true",
        dest="no_scan",
        help="Skip Launchpad scan and regenerate HTML status report directly from state file",
    )
    parser.add_argument(
        "-s",
        "--series",
        nargs="+",
        metavar="SERIES",
        help="Specific Ubuntu series to scan (default: all active series, e.g. noble, jammy, etc.)",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help=f"Launchpadlib HTTP cache directory (default: {DEFAULT_CACHE_DIR})",
    )
    parser.add_argument(
        "--json",
        type=Path,
        metavar="PATH",
        help="Optional path to dump extracted bug data as JSON",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run scan and generate HTML without modifying the state file",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable detailed diagnostic logging",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = create_parser()
    return parser.parse_args(argv)


def resolve_packages(args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[str]:
    """Resolve and validate the combined list of packages from file and CLI arguments."""
    packages: set[str] = set()

    if args.packages_file:
        try:
            file_pkgs = load_packages_from_file(args.packages_file)
            packages.update(file_pkgs)
            logger.debug("Loaded %d packages from %s", len(file_pkgs), args.packages_file)
        except Exception as e:
            parser.error(f"Failed to read packages file '{args.packages_file}': {e}")

    if args.packages:
        packages.update(args.packages)

    if args.pos_packages:
        packages.update(args.pos_packages)

    if not packages and not getattr(args, "no_scan", False):
        parser.error("No source packages specified. Provide package names as arguments or via -f/--packages-file.")

    return sorted(packages)


def setup_logging(verbose: bool) -> None:
    """Configure logging for the CLI."""
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def run_scan(
    args: argparse.Namespace,
    packages: list[str],
    lp: Any | None = None,
    ubuntu: Any | None = None,
    series_list: list[str] | None = None,
) -> int:
    """Scan one package set and generate its HTML status report.

    `lp`, `ubuntu`, and `series_list` may be supplied to reuse an existing
    Launchpad connection and series resolution (as done by scan-all);
    otherwise they are created here.
    """
    if args.no_scan:
        logger.info("Running in report-only mode (skipping Launchpad scan)...")
        state_file = Path(args.state_file)
        if not state_file.is_file():
            logger.error("State file '%s' does not exist; cannot regenerate report", state_file)
            return 1

        state = load_state(state_file)
        bugs = state.get("bugs", {})
        state_packages = state.get("packages", [])

        final_packages = packages if packages else state_packages
        if not final_packages and bugs:
            final_packages = sorted({b.get("package") for b in bugs.values() if b.get("package")})

        scan_time = None
        if state.get("last_scan_utc"):
            try:
                scan_time = datetime.fromisoformat(str(state["last_scan_utc"]))
            except Exception:
                scan_time = None

        logger.info(
            "Regenerating HTML report from state (%d bugs, %d packages)...",
            len(bugs),
            len(final_packages),
        )
        try:
            generate_html_report(
                bugs=bugs,
                output_path=args.output,
                scan_time_utc=scan_time,
                packages_scanned=final_packages,
                title=args.title,
                workflow_url=args.workflow_url,
            )
            logger.info("Generated HTML status report at %s", args.output.resolve())
        except Exception as e:
            logger.error("Failed to generate HTML report: %s", e)
            return 1

        if args.json:
            try:
                args.json.parent.mkdir(parents=True, exist_ok=True)
                with args.json.open("w", encoding="utf-8") as f:
                    json.dump({"scan_time_utc": state.get("last_scan_utc"), "bugs": bugs}, f, indent=2)
                logger.info("Exported JSON bug data to %s", args.json)
            except Exception as e:
                logger.error("Failed to export JSON: %s", e)

        return 0

    logger.info("Monitoring %d source packages: %s", len(packages), packages)

    try:
        if lp is None:
            lp = get_launchpad(cache_dir=args.cache_dir)
        if ubuntu is None:
            ubuntu = get_ubuntu_distribution(lp)
    except Exception as e:
        logger.error("Failed to connect to Launchpad: %s", e)
        return 1

    # Resolve active series
    if args.series:
        series_list = sorted(set(args.series))
        logger.info("Using user-specified series: %s", series_list)
    elif series_list is None:
        series_list = get_active_series(ubuntu)

    # Load existing state
    state = load_state(args.state_file)
    existing_bugs = state.get("bugs", {})
    last_scan_utc = state.get("last_scan_utc")
    state_packages = state.get("packages", [])

    scan_start_utc = datetime.now(UTC)

    # Automatically trigger a full scan if monitored packages have changed
    packages_changed = bool(state_packages) and set(state_packages) != set(packages)
    if packages_changed:
        added = sorted(set(packages) - set(state_packages))
        removed = sorted(set(state_packages) - set(packages))
        changes = []
        if added:
            changes.append(f"added: {added}")
        if removed:
            changes.append(f"removed: {removed}")
        logger.info("Monitored packages changed (%s); triggering full scan", "; ".join(changes))

    is_incremental = bool(last_scan_utc) and not args.full and not packages_changed

    # Periodic full scan: guard against changes that incremental scans cannot
    # see (e.g. bugs retargeted away from the monitored packages).
    if is_incremental and args.full_scan_interval > 0:
        try:
            last_dt = datetime.fromisoformat(str(last_scan_utc))
            age_hours = (scan_start_utc - last_dt).total_seconds() / 3600.0
            if age_hours >= args.full_scan_interval:
                logger.info(
                    "Last scan is %.1f hours old (full-scan interval: %g h); forcing full scan",
                    age_hours,
                    args.full_scan_interval,
                )
                is_incremental = False
        except Exception as e:
            logger.warning("Could not determine last scan age (%s); forcing full scan", e)
            is_incremental = False

    if is_incremental:
        try:
            last_dt = datetime.fromisoformat(str(last_scan_utc))
            # 5-minute safety buffer against network latency and clock skew
            since_utc = last_dt - timedelta(minutes=5)
            logger.info("Running incremental scan since %s (last run: %s)", since_utc.isoformat(), last_scan_utc)
            bugs = scan_incremental(
                ubuntu=ubuntu,
                packages=packages,
                series_list=series_list,
                existing_bugs=existing_bugs,
                since_utc=since_utc,
                lp=lp,
            )
        except Exception as e:
            logger.warning("Incremental scan failed (%s); falling back to full scan", e)
            bugs = scan_full(ubuntu=ubuntu, packages=packages, series_list=series_list)
    else:
        logger.info("Running full scan across %d packages...", len(packages))
        bugs = scan_full(ubuntu=ubuntu, packages=packages, series_list=series_list)

    logger.info("Active open bugs found: %d", len(bugs))

    # Persist state
    if not args.dry_run:
        new_state = {
            "last_scan_utc": scan_start_utc.isoformat(),
            "packages": packages,
            "bugs": bugs,
        }
        try:
            save_state(args.state_file, new_state)
            logger.info("Saved state to %s", args.state_file)
        except Exception as e:
            logger.error("Failed to save state to %s: %s", args.state_file, e)

    # Generate HTML report
    try:
        generate_html_report(
            bugs=bugs,
            output_path=args.output,
            scan_time_utc=scan_start_utc,
            packages_scanned=packages,
            title=args.title,
            workflow_url=args.workflow_url,
        )
        logger.info("Generated HTML status report at %s", args.output.resolve())
    except Exception as e:
        logger.error("Failed to generate HTML report: %s", e)
        return 1

    # Optional JSON export
    if args.json:
        try:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            with args.json.open("w", encoding="utf-8") as f:
                json.dump({"scan_time_utc": scan_start_utc.isoformat(), "bugs": bugs}, f, indent=2)
            logger.info("Exported JSON bug data to %s", args.json)
        except Exception as e:
            logger.error("Failed to export JSON: %s", e)

    return 0


def set_title(name: str) -> str:
    """Return the dashboard title for a package set."""
    return f"Ubuntu Bug Status — {name}"


def discover_sets(data_dir: Path | str) -> list[Path]:
    """Discover package sets: subdirectories of data_dir containing a packages.txt file.

    Hidden directories are ignored. Returns a sorted list of set directories.
    """
    root = Path(data_dir).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Data directory not found: {root}")

    return sorted(
        d for d in root.iterdir() if d.is_dir() and not d.name.startswith(".") and (d / "packages.txt").is_file()
    )


def build_set_summary(name: str, set_dir: Path) -> dict[str, Any]:
    """Build the index-page summary record for one package set from its state file."""
    state = load_state(set_dir / "bugs-state.json")
    return {
        "name": name,
        "path": f"{name}/index.html",
        "title": set_title(name),
        "bug_count": len(state.get("bugs", {})),
        "package_count": len(state.get("packages", [])),
        "last_scan_utc": state.get("last_scan_utc"),
    }


def create_scan_all_parser() -> argparse.ArgumentParser:
    """Create the argument parser for multi-set scanning."""
    parser = argparse.ArgumentParser(
        prog="lp-bug-monitor scan-all",
        description=(
            "Scan every package set under DATA_DIR. A set is a subdirectory containing a "
            "packages.txt file; each set gets its own bugs-state.json and index.html dashboard, "
            "and a shared index.html landing page links all dashboards."
        ),
    )
    parser.add_argument(
        "data_dir",
        nargs="?",
        default="data",
        metavar="DATA_DIR",
        help="Directory containing one subdirectory per package set (default: data)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable detailed diagnostic logging",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help=f"Launchpadlib HTTP cache directory (default: {DEFAULT_CACHE_DIR})",
    )
    parser.add_argument(
        "-s",
        "--series",
        nargs="+",
        metavar="SERIES",
        help="Specific Ubuntu series to scan (default: all active series, e.g. noble, jammy, etc.)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Force full scans from scratch instead of incremental scans",
    )
    parser.add_argument(
        "--full-scan-interval",
        type=float,
        default=48.0,
        metavar="HOURS",
        help=(
            "Force a full scan if the last scan is older than this many hours "
            "(default: 48, 0 disables the periodic full scan)"
        ),
    )
    parser.add_argument(
        "--no-scan",
        "--report-only",
        action="store_true",
        dest="no_scan",
        help="Skip Launchpad scans and regenerate dashboards from existing state files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run scans and generate HTML without modifying the state files",
    )
    parser.add_argument(
        "--workflow-url",
        type=str,
        default=DEFAULT_WORKFLOW_URL,
        help=f"URL to GitHub Action for manual regeneration and run history (default: {DEFAULT_WORKFLOW_URL})",
    )
    parser.add_argument(
        "--no-workflow-url",
        action="store_const",
        const=None,
        dest="workflow_url",
        help="Disable the GitHub Action link and Regenerate button in the HTML reports",
    )
    return parser


def run_scan_all(argv: list[str] | None = None) -> int:
    """Scan (or regenerate reports for) every package set under a data directory."""
    parser = create_scan_all_parser()
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    data_dir = Path(args.data_dir).expanduser().resolve()
    try:
        set_dirs = discover_sets(data_dir)
    except FileNotFoundError as e:
        logger.error("%s", e)
        return 1

    if not set_dirs:
        logger.error(
            "No package sets found in %s (expected subdirectories each containing a packages.txt file)",
            data_dir,
        )
        return 1

    logger.info("Found %d package set(s): %s", len(set_dirs), [d.name for d in set_dirs])

    # Share a single Launchpad connection and series list across all sets
    lp: Any | None = None
    ubuntu: Any | None = None
    series_list: list[str] | None = None
    if not args.no_scan:
        try:
            lp = get_launchpad(cache_dir=args.cache_dir)
            ubuntu = get_ubuntu_distribution(lp)
        except Exception as e:
            logger.error("Failed to connect to Launchpad: %s", e)
            return 1
        series_list = sorted(set(args.series)) if args.series else get_active_series(ubuntu)

    failed: list[str] = []
    summaries: list[dict[str, Any]] = []
    for set_dir in set_dirs:
        name = set_dir.name
        logger.info("=== Package set '%s' ===", name)

        try:
            packages = load_packages_from_file(set_dir / "packages.txt")
        except Exception as e:
            logger.error("Failed to load packages for set '%s': %s", name, e)
            failed.append(name)
            continue

        set_args = argparse.Namespace(
            no_scan=args.no_scan,
            full=args.full,
            full_scan_interval=args.full_scan_interval,
            series=args.series,
            cache_dir=args.cache_dir,
            state_file=set_dir / "bugs-state.json",
            output=set_dir / "index.html",
            title=set_title(name),
            workflow_url=args.workflow_url,
            json=None,
            dry_run=args.dry_run,
        )
        try:
            rc = run_scan(set_args, packages, lp=lp, ubuntu=ubuntu, series_list=series_list)
        except Exception as e:
            logger.error("Package set '%s' failed: %s", name, e)
            rc = 1
        if rc != 0:
            failed.append(name)
            continue

        summaries.append(build_set_summary(name, set_dir))

    if failed:
        logger.error("Failed package set(s): %s", ", ".join(failed))

    if not summaries:
        return 1

    # Landing page linking all dashboards
    try:
        generate_index_page(summaries, data_dir / "index.html", workflow_url=args.workflow_url)
        logger.info("Generated index page at %s", (data_dir / "index.html").resolve())
    except Exception as e:
        logger.error("Failed to generate index page: %s", e)
        return 1

    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    argv_list = list(sys.argv[1:] if argv is None else argv)
    if argv_list and argv_list[0] == "scan-all":
        return run_scan_all(argv_list[1:])

    parser = create_parser()
    args = parser.parse_args(argv_list)
    setup_logging(args.verbose)

    packages = resolve_packages(args, parser)
    return run_scan(args, packages)


if __name__ == "__main__":
    sys.exit(main())
