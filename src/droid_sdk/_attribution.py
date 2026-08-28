"""Canonical producer-owned attribution for the Python SDK."""

from __future__ import annotations

import importlib.metadata
from typing import TYPE_CHECKING

from droid_sdk.schemas.enums import ClientType
from droid_sdk.schemas.session import SessionTag
from droid_sdk.schemas.shared import ClientRequestAttribution, SdkClientMetadata

if TYPE_CHECKING:
    from collections.abc import Sequence

SDK_CLIENT_METADATA = SdkClientMetadata(
    language="python",
    version=importlib.metadata.version("droid-sdk"),
)
SDK_IDENTITY = f"{SDK_CLIENT_METADATA.language}/{SDK_CLIENT_METADATA.version}"
SDK_REQUEST_ATTRIBUTION = ClientRequestAttribution(
    client=ClientType.SDK,
    sdk=SDK_CLIENT_METADATA,
)
SDK_REQUEST_ATTRIBUTION_PAYLOAD = SDK_REQUEST_ATTRIBUTION.model_dump(mode="json")
SDK_TAG = SessionTag(
    name="sdk",
    metadata=SDK_CLIENT_METADATA.model_dump(mode="json"),
)


def canonicalize_sdk_tags(tags: Sequence[SessionTag]) -> list[SessionTag]:
    """Replace caller-supplied SDK tags with one canonical tag."""
    return [tag for tag in tags if tag.name != SDK_TAG.name] + [SDK_TAG]


def sdk_process_environment() -> dict[str, str]:
    """Return producer-owned attribution for a spawned Droid process."""
    return {
        "FACTORY_UPSTREAM_CLIENT_TYPE": ClientType.SDK.value,
        "FACTORY_UPSTREAM_SDK": SDK_IDENTITY,
    }


__all__ = [
    "SDK_CLIENT_METADATA",
    "SDK_IDENTITY",
    "SDK_REQUEST_ATTRIBUTION",
    "SDK_REQUEST_ATTRIBUTION_PAYLOAD",
    "SDK_TAG",
    "canonicalize_sdk_tags",
    "sdk_process_environment",
]
