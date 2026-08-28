"""Installed Python SDK version."""

from __future__ import annotations

import importlib.metadata

PACKAGE_VERSION = importlib.metadata.version("droid-sdk")

__all__ = ["PACKAGE_VERSION"]
