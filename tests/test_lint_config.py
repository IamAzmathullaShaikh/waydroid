# SPDX-License-Identifier: GPL-3.0-or-later
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _find_ruff():
    """Locate ruff on PATH, or next to the running interpreter (venvs)."""
    found = shutil.which("ruff")
    if found:
        return found
    # Note: do not resolve sys.executable here - venv pythons are symlinks
    # to the base interpreter, so resolving would escape the venv's bin dir.
    candidate = Path(sys.executable).parent / "ruff"
    if candidate.is_file():
        return str(candidate)
    return None


def _lint_ignore():
    with open(ROOT / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    return data["tool"]["ruff"]["lint"]["ignore"]


def test_f401_f811_not_disabled_in_pyproject():
    """
    F401 (unused imports) and F811 (redefinitions) must stay enabled.

    They were previously hidden behind a TODO in the pyproject.toml ignore
    list; that cleanup is done, so this test fails if they are disabled
    again, either directly or through a prefix (e.g. "F" or "F4") that
    covers them.
    """
    for entry in _lint_ignore():
        assert not ("F401".startswith(entry) or "F811".startswith(entry)), (
            f"F401/F811 must not be disabled via ignore entry {entry!r} in pyproject.toml"
        )


def test_ruff_f401_f811_clean():
    """
    Run ruff restricted to F401/F811 and fail on any violation.

    The CI lint job already runs the full `ruff check .`; this test makes
    the two rules explicit and works locally too. It is skipped when ruff
    is not installed (e.g. in the CI test job, which only installs pytest).
    """
    ruff = _find_ruff()
    if ruff is None:
        pytest.skip("ruff not installed")

    result = subprocess.run(
        [ruff, "check", "--select", "F401,F811", "."],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "ruff reported F401/F811 violations:\n" + result.stdout + result.stderr
    )
