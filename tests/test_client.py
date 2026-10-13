"""Tests for client discovery and connection parameters."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from lp_bug_monitor.client import (
    get_active_series,
    get_launchpad,
    get_ubuntu_distribution,
)


def test_get_active_series():
    ubuntu_mock = MagicMock()

    s1 = MagicMock()
    s1.name = "noble"
    s1.active = True

    s2 = MagicMock()
    s2.name = "jammy"
    s2.active = True

    s3 = MagicMock()
    s3.name = "trusty"
    s3.active = False

    ubuntu_mock.series = [s1, s2, s3]

    series = get_active_series(ubuntu_mock)
    assert series == ["noble", "jammy"]


@patch("lp_bug_monitor.client.Launchpad")
def test_get_launchpad_calls_login_anonymously(mock_lp):
    get_launchpad(cache_dir="/tmp/test_lp_cache")
    mock_lp.login_anonymously.assert_called_once_with(
        consumer_name="lp-bug-monitor",
        service_root="production",
        launchpadlib_dir="/tmp/test_lp_cache",
        version="devel",
    )


def test_get_ubuntu_distribution():
    lp_mock = MagicMock()
    ubuntu_mock = MagicMock()
    lp_mock.distributions = {"ubuntu": ubuntu_mock}

    assert get_ubuntu_distribution(lp_mock) is ubuntu_mock
