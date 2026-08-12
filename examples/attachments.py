"""Load local attachments without starting Droid."""

from __future__ import annotations

import argparse
import asyncio
import base64
import tempfile
from pathlib import Path

from droid_sdk import (
    Document,
    Image,
    PdfDocumentSource,
    TextDocumentSource,
    run,
)


def minimal_pdf() -> bytes:
    content = b"BT /F1 12 Tf 72 720 Td (Offline PDF example.) Tj ET"
    objects = (
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        b"<< /Length "
        + str(len(content)).encode()
        + b" >>\nstream\n"
        + content
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    )
    data = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, value in enumerate(objects, start=1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode())
        data.extend(value)
        data.extend(b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    data.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010} 00000 n \n".encode())
    data.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode()
    )
    return bytes(data)


async def main(run_turn: bool = False) -> None:
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAAQ0lEQVR4AcXB"
        "AQEAAAiDMKR/5xuD7QYjJDGJSUxiEpOYxCQmMYlJTGISk5jEJCYxiUlMYhKT"
        "mMQkJjGJSUxiEpOYxB4w4wI+9B/igQAAAABJRU5ErkJggg=="
    )
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        text_path = root / "notes.txt"
        pdf_path = root / "report.pdf"
        image_path = root / "pixel.png"
        text_path.write_text("Offline attachment example.\n", encoding="utf-8")
        pdf_path.write_bytes(minimal_pdf())
        image_path.write_bytes(png)

        image = Image.from_path(image_path)
        text = Document.from_path(text_path)
        pdf = Document.from_path(pdf_path)

        assert isinstance(text.source, TextDocumentSource)
        assert isinstance(pdf.source, PdfDocumentSource)
        if run_turn:
            result = await run(
                "Describe the attached red square and summarize both files.",
                images=[image],
                files=[text, pdf],
                timeout=60,
            )
            assert result.success, result.error
            assert result.text
            print(result.text)
        print(f"image: {image.source.media_type}")
        print(f"text: {text.source.name} ({text.source.mime})")
        print(f"pdf: {pdf.source.name} ({len(pdf.source.data)} base64 chars)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    asyncio.run(main(parser.parse_args().run))
