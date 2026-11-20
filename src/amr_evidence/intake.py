"""Bounded PDF/text intake; originals are not written to disk."""

import io
from pathlib import Path

import pdfplumber

MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 100
MAX_CHARS = 2_000_000


def read_upload(name: str, content: bytes) -> tuple[list[str], str]:
    if not content or len(content) > MAX_BYTES:
        raise ValueError("Upload must be non-empty and no larger than 20 MB.")
    extension = Path(name).suffix.lower()
    if extension == ".txt":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Text must use UTF-8 encoding.") from exc
        if "\x00" in text or not text.strip() or len(text) > MAX_CHARS:
            raise ValueError("Text is empty, binary, or exceeds 2 million characters.")
        return [text], "text"
    if extension != ".pdf" or not content.startswith(b"%PDF-"):
        raise ValueError("Only UTF-8 .txt or genuine text-based .pdf files are supported.")
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            if pdf.doc.encryption:
                raise ValueError(
                    "Encrypted PDFs are unsupported. Upload an authorized unlocked copy."
                )
            if not 1 <= len(pdf.pages) <= MAX_PAGES:
                raise ValueError("PDF must contain 1–100 pages.")
            pages = []
            for page in pdf.pages:
                pages.append(page.extract_text() or "")
                if sum(len(p) for p in pages) > MAX_CHARS:
                    raise ValueError("PDF text exceeds 2 million characters.")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("PDF could not be read; it may be damaged or encrypted.") from exc
    if sum(len(p.strip()) for p in pages) < 40:
        raise ValueError("No useful PDF text found. Scanned documents need OCR outside this app.")
    return pages, "pdf"
