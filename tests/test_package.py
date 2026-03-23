"""Basic package tests."""

from droid_sdk import __all__


def test_package_importable() -> None:
    """Verify the package can be imported."""
    assert isinstance(__all__, list)
