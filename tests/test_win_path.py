"""Tests for Windows-to-WSL2 path translation in the Podman backend."""

import pytest

from cutip.backends.podman.backend import _win_to_wsl


@pytest.mark.parametrize(
    "inp, expected",
    [
        # Canonical Windows forward-slash paths
        ("C:/Users/foo/bar", "/mnt/c/Users/foo/bar"),
        ("D:/some/path", "/mnt/d/some/path"),
        # Missing slash after colon (as seen in the wild)
        ("C:Users/foo/.ssh/key", "/mnt/c/Users/foo/.ssh/key"),
        # Backslash paths
        ("C:\\Users\\foo\\bar", "/mnt/c/Users/foo/bar"),
        # Drive letter casing is normalised to lowercase
        ("c:/Users/foo", "/mnt/c/Users/foo"),
        ("Z:/data", "/mnt/z/data"),
        # Non-Windows paths are returned unchanged
        ("/home/user/.ssh/key", "/home/user/.ssh/key"),
        ("/mnt/c/already/wsl", "/mnt/c/already/wsl"),
        ("relative/path", "relative/path"),
    ],
)
def test_win_to_wsl(inp, expected):
    assert _win_to_wsl(inp) == expected
