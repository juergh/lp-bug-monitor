"""Launchpad client interaction, connection handling, and release series retrieval."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from launchpadlib.launchpad import Launchpad

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "launchpadlib"


def get_launchpad(cache_dir: Path | str | None = None) -> Launchpad:
    """Connect anonymously to Launchpad with a persistent local cache."""
    resolved_cache = Path(cache_dir or DEFAULT_CACHE_DIR).expanduser().resolve()
    resolved_cache.mkdir(parents=True, exist_ok=True)

    logger.debug("Connecting anonymously to Launchpad (cache: %s)...", resolved_cache)
    return Launchpad.login_anonymously(
        consumer_name="lp-bug-monitor",
        service_root="production",
        launchpadlib_dir=str(resolved_cache),
        version="devel",
    )


def get_ubuntu_distribution(lp: Launchpad) -> Any:
    """Retrieve the Ubuntu distribution resource from Launchpad."""
    return lp.distributions["ubuntu"]


def get_active_series(ubuntu: Any) -> list[str]:
    """Retrieve list of currently active Ubuntu release series names."""
    logger.debug("Retrieving active Ubuntu series...")
    active_series: list[str] = []
    try:
        for s in ubuntu.series:
            if getattr(s, "active", False):
                active_series.append(s.name)
    except Exception as e:
        logger.warning("Failed to retrieve series from distribution: %s", e)
        # Standard active series fallback in case of API issue
        active_series = ["noble", "jammy", "focal"]

    logger.debug("Active Ubuntu series: %s", active_series)
    return active_series
