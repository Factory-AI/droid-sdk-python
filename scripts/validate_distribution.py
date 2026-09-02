"""Validate and install the built wheel and source distribution."""

from __future__ import annotations

import importlib.metadata
import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from email.parser import Parser
from pathlib import Path

ROOT = Path(__file__).parents[1]
DIST = ROOT / "dist"
PACKAGE_NAME = "droid-sdk"


def single_artifact(pattern: str) -> Path:
    """Return the only distribution artifact matching *pattern*."""
    artifacts = list(DIST.glob(pattern))
    if len(artifacts) != 1:
        raise RuntimeError(
            f"expected exactly one {pattern} artifact in {DIST}, found {artifacts}"
        )
    return artifacts[0]


def validate_wheel(wheel: Path, expected_version: str) -> None:
    """Check the wheel metadata and required typed-package marker."""
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata_files = [
            name for name in names if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_files) != 1:
            raise RuntimeError(
                f"expected one wheel METADATA file, found {metadata_files}"
            )
        metadata = Parser().parsestr(archive.read(metadata_files[0]).decode("utf-8"))
        if metadata["Name"] != PACKAGE_NAME:
            raise RuntimeError(
                f"wheel name is {metadata['Name']!r}, expected {PACKAGE_NAME!r}"
            )
        if metadata["Version"] != expected_version:
            raise RuntimeError(
                f"wheel version is {metadata['Version']!r}, "
                f"expected {expected_version!r}"
            )
        if "droid_sdk/py.typed" not in names:
            raise RuntimeError("wheel does not contain droid_sdk/py.typed")


def validate_sdist(sdist: Path) -> None:
    """Check the source distribution's required and excluded files."""
    with tarfile.open(sdist, "r:gz") as archive:
        names = archive.getnames()
    relative_names = {name.split("/", 1)[1] for name in names if "/" in name}
    required = {
        "LICENSE",
        "README.md",
        "pyproject.toml",
        "src/droid_sdk/py.typed",
    }
    missing = required - relative_names
    if missing:
        raise RuntimeError(f"sdist is missing required files: {sorted(missing)}")
    excluded_roots = {".github", "scripts", "tests"}
    included_excluded_roots = {
        name.split("/", 1)[0] for name in relative_names
    } & excluded_roots
    if included_excluded_roots:
        raise RuntimeError(
            "sdist unexpectedly contains development-only roots: "
            f"{sorted(included_excluded_roots)}"
        )


def install_and_import_artifact(artifact: Path, expected_version: str) -> None:
    """Install an artifact into a clean environment and import its public root."""
    with tempfile.TemporaryDirectory(prefix="droid-sdk-package-smoke-") as temp:
        environment = Path(temp)
        subprocess.run(
            ["uv", "venv", str(environment), "--python", sys.executable],
            check=True,
            cwd=ROOT,
        )
        python = environment / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        subprocess.run(
            ["uv", "pip", "install", "--python", str(python), str(artifact)],
            check=True,
            cwd=ROOT,
        )
        subprocess.run(
            [
                str(python),
                "-c",
                (
                    "import importlib.metadata, droid_sdk; "
                    f"expected = {expected_version!r}; "
                    "assert importlib.metadata.version('droid-sdk') == expected; "
                    "assert droid_sdk.__version__ == expected"
                ),
            ],
            check=True,
            cwd=environment,
        )


def main() -> None:
    """Validate both artifacts and smoke-test the installed wheel."""
    expected_version = importlib.metadata.version(PACKAGE_NAME)
    wheel = single_artifact("*.whl")
    sdist = single_artifact("*.tar.gz")
    validate_wheel(wheel, expected_version)
    validate_sdist(sdist)
    install_and_import_artifact(wheel, expected_version)
    install_and_import_artifact(sdist, expected_version)
    print(f"Validated {wheel.name} and {sdist.name}")


if __name__ == "__main__":
    main()
