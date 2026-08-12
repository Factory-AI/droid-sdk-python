from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
NEGATIVE_FIXTURE = ROOT / "tests" / "typing" / "negative.py"
NEGATIVE_PYRIGHT_CONFIG = ROOT / "tests" / "typing" / "pyright-negative.json"


def test_negative_mypy_fixture_is_rejected() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            str(NEGATIVE_FIXTURE),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 1
    assert "Missing positional arguments" in completed.stdout
    assert 'cannot be "str"' in completed.stdout
    assert "Incompatible types in assignment" in completed.stdout
    assert completed.stdout.count("Unsupported target for indexed assignment") == 2


def test_negative_pyright_fixture_is_rejected() -> None:
    pyright = shutil.which("pyright")
    if pyright is None:
        pytest.fail("pyright executable is required for typing fixture tests")
    completed = subprocess.run(
        [pyright, "--project", str(NEGATIVE_PYRIGHT_CONFIG)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 1
    assert '"model", "reasoning_effort"' in completed.stdout
    assert "No overloads for" in completed.stdout
    assert 'Type "BadLogger" is not assignable to declared type "Logger"' in (
        completed.stdout
    )
    assert '"__setitem__" method not defined on type "FrozenJsonObject"' in (
        completed.stdout
    )
    assert '"__setitem__" method not defined on type "tuple' in completed.stdout
