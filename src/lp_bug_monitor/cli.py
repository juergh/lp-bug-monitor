"""Command-line interface for Launchpad bug monitor."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from lp_bug_monitor.client import (
    DEFAULT_CACHE_DIR,
    get_active_series,
    get_launchpad,
    get_ubuntu_distribution,
)
from lp_bug_monitor.report import generate_html_report
from lp_bug_monitor.scanner import scan_full, scan_incremental
from lp_bug_monitor.state import load_state, save_state

logger = logging.getLogger("lp_bug_monitor")


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

    if not packages:
        parser.error("No source packages specified. Provide package names as arguments or via -f/--packages-file.")

    return sorted(packages)


def main(argv: list[str] | None = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    packages = resolve_packages(args, parser)
    logger.info("Monitoring %d source packages: %s", len(packages), packages)

    try:
        lp = get_launchpad(cache_dir=args.cache_dir)
        ubuntu = get_ubuntu_distribution(lp)
    except Exception as e:
        logger.error("Failed to connect to Launchpad: %s", e)
        return 1

    # Resolve active series
    if args.series:
        series_list = sorted(set(args.series))
        logger.info("Using user-specified series: %s", series_list)
    else:
        series_list = get_active_series(ubuntu)

    # Load existing state
    state = load_state(args.state_file)
    existing_bugs = state.get("bugs", {})
    last_scan_utc = state.get("last_scan_utc")

    scan_start_utc = datetime.now(UTC)
    is_incremental = bool(last_scan_utc) and not args.full

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


if __name__ == "__main__":
    sys.exit(main())
