"""Safe, immutable local attachment values."""

from __future__ import annotations

import base64
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from droid_sdk.errors import InvalidAttachmentError

ImageMediaType = Literal["image/jpeg", "image/png", "image/gif", "image/webp"]
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
MAX_PDF_ATTACHMENT_BYTES = 3 * 1024 * 1024


def _oversize_error() -> InvalidAttachmentError:
    return InvalidAttachmentError(
        f"Attachment exceeds the {MAX_ATTACHMENT_BYTES}-byte limit"
    )


def _pdf_oversize_error() -> InvalidAttachmentError:
    return InvalidAttachmentError(
        f"PDF attachment exceeds the {MAX_PDF_ATTACHMENT_BYTES}-byte limit"
    )


def _read_regular_file(
    path: str | Path,
    *,
    max_bytes: int | None = None,
) -> tuple[Path, bytes]:
    resolved = Path(path)
    limit = MAX_ATTACHMENT_BYTES if max_bytes is None else max_bytes
    try:
        path_stat = resolved.stat()
        if not stat.S_ISREG(path_stat.st_mode):
            raise InvalidAttachmentError(
                f"Attachment is not a regular file: {resolved}"
            )
        if path_stat.st_size > limit:
            raise _oversize_error()

        with resolved.open("rb") as file:
            before = os.fstat(file.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise InvalidAttachmentError(
                    f"Attachment is not a regular file: {resolved}"
                )
            if (
                before.st_dev != path_stat.st_dev
                or before.st_ino != path_stat.st_ino
                or before.st_size != path_stat.st_size
                or before.st_mtime_ns != path_stat.st_mtime_ns
            ):
                raise InvalidAttachmentError("Attachment changed before it was read")
            if before.st_size > limit:
                raise _oversize_error()

            data = file.read(limit + 1)
            after = os.fstat(file.fileno())

        if len(data) > limit or after.st_size > limit:
            raise _oversize_error()
        if (
            after.st_size != before.st_size
            or after.st_mtime_ns != before.st_mtime_ns
            or len(data) != after.st_size
        ):
            raise InvalidAttachmentError("Attachment changed while it was read")
        return resolved, data
    except InvalidAttachmentError:
        raise
    except FileNotFoundError:
        raise InvalidAttachmentError(f"Attachment does not exist: {resolved}") from None
    except PermissionError:
        raise InvalidAttachmentError(
            f"Attachment is not readable: {resolved}"
        ) from None
    except (OSError, ValueError) as exc:
        raise InvalidAttachmentError(
            f"Could not read attachment {resolved}: {type(exc).__name__}"
        ) from None


def _detect_image_type(data: bytes) -> ImageMediaType | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _utf8_exceeds_limit(value: str, limit: int) -> bool:
    size = 0
    for start in range(0, len(value), 64 * 1024):
        size += len(value[start : start + 64 * 1024].encode("utf-8"))
        if size > limit:
            return True
    return False


@dataclass(frozen=True, slots=True)
class Base64ImageSource:
    data: str
    media_type: ImageMediaType

    def __post_init__(self) -> None:
        if len(self.data) > 4 * ((MAX_ATTACHMENT_BYTES + 2) // 3):
            raise _oversize_error()
        if self.media_type not in {
            "image/jpeg",
            "image/png",
            "image/gif",
            "image/webp",
        }:
            raise InvalidAttachmentError(
                f"Unsupported image media type: {self.media_type}"
            )
        try:
            decoded = base64.b64decode(self.data, validate=True)
        except (ValueError, TypeError):
            raise InvalidAttachmentError("Image data is not valid base64") from None
        if len(decoded) > MAX_ATTACHMENT_BYTES:
            raise _oversize_error()
        detected = _detect_image_type(decoded)
        if detected is None:
            raise InvalidAttachmentError("Image data has an unsupported signature")
        if detected != self.media_type:
            raise InvalidAttachmentError(
                f"Image data is {detected}, not {self.media_type}"
            )


def _image_source_from_validated_bytes(
    data: bytes,
    media_type: ImageMediaType,
) -> Base64ImageSource:
    source = object.__new__(Base64ImageSource)
    object.__setattr__(source, "data", base64.b64encode(data).decode("ascii"))
    object.__setattr__(source, "media_type", media_type)
    return source


@dataclass(frozen=True, slots=True)
class Image:
    source: Base64ImageSource

    @classmethod
    def from_path(cls, path: str | Path) -> Image:
        _, data = _read_regular_file(path)
        media_type = _detect_image_type(data)
        if media_type is None:
            raise InvalidAttachmentError("Unsupported or invalid image file")
        return cls.from_bytes(data, media_type=media_type)

    @classmethod
    def from_bytes(cls, data: bytes, *, media_type: ImageMediaType) -> Image:
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise _oversize_error()
        detected = _detect_image_type(data)
        if detected is None:
            raise InvalidAttachmentError("Unsupported or invalid image data")
        if detected != media_type:
            raise InvalidAttachmentError(f"Image data is {detected}, not {media_type}")
        return cls(_image_source_from_validated_bytes(data, media_type))


@dataclass(frozen=True, slots=True)
class TextDocumentSource:
    data: str
    name: str | None = None
    mime: str | None = None

    def __post_init__(self) -> None:
        if _utf8_exceeds_limit(self.data, MAX_ATTACHMENT_BYTES):
            raise _oversize_error()


@dataclass(frozen=True, slots=True)
class PdfDocumentSource:
    data: str
    parsed_data: str | None = None
    name: str | None = None
    path: str | None = None

    def __post_init__(self) -> None:
        if len(self.data) > 4 * ((MAX_PDF_ATTACHMENT_BYTES + 2) // 3):
            raise _pdf_oversize_error()
        try:
            decoded = base64.b64decode(self.data, validate=True)
        except (ValueError, TypeError):
            raise InvalidAttachmentError("PDF data is not valid base64") from None
        if len(decoded) > MAX_PDF_ATTACHMENT_BYTES:
            raise _pdf_oversize_error()
        if not decoded.startswith(b"%PDF-"):
            raise InvalidAttachmentError("Document data is not a valid PDF")


def _pdf_source_from_validated_bytes(
    data: bytes,
    *,
    name: str | None,
    path: str | None,
) -> PdfDocumentSource:
    source = object.__new__(PdfDocumentSource)
    object.__setattr__(source, "data", base64.b64encode(data).decode("ascii"))
    object.__setattr__(source, "parsed_data", None)
    object.__setattr__(source, "name", name)
    object.__setattr__(source, "path", path)
    return source


DocumentSource = TextDocumentSource | PdfDocumentSource


@dataclass(frozen=True, slots=True)
class Document:
    source: DocumentSource

    @classmethod
    def from_path(cls, path: str | Path) -> Document:
        file_path, data = _read_regular_file(path)
        if data.startswith(b"%PDF-"):
            if len(data) > MAX_PDF_ATTACHMENT_BYTES:
                raise _pdf_oversize_error()
            return cls(
                _pdf_source_from_validated_bytes(
                    data,
                    name=file_path.name,
                    path=str(file_path),
                )
            )
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise InvalidAttachmentError(
                "Document is neither a PDF nor valid UTF-8 text"
            ) from None
        return cls.from_text(text, name=file_path.name, mime="text/plain")

    @classmethod
    def from_text(
        cls,
        text: str,
        *,
        name: str | None = None,
        mime: str | None = None,
    ) -> Document:
        return cls(TextDocumentSource(data=text, name=name, mime=mime))

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        *,
        name: str | None = None,
    ) -> Document:
        if len(data) > MAX_PDF_ATTACHMENT_BYTES:
            raise _pdf_oversize_error()
        if not data.startswith(b"%PDF-"):
            raise InvalidAttachmentError("Document bytes are not a valid PDF")
        return cls(
            _pdf_source_from_validated_bytes(
                data,
                name=name,
                path=None,
            )
        )
