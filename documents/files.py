"""Locate local Job Library application documents."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATED_DOCUMENTS = PROJECT_ROOT / "local" / "generated_documents"
DOCUMENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def document_file(capture_id, kind):
    for suffix in DOCUMENT_TYPES:
        path = GENERATED_DOCUMENTS / str(capture_id) / f"{kind}{suffix}"
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError):
            continue
        if resolved == path and resolved.is_file():
            return resolved
    return None
