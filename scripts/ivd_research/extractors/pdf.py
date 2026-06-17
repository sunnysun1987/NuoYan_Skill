from pathlib import Path


def extract_pdf_text(path: Path) -> tuple[str, str]:
    try:
        from pypdf import PdfReader
    except Exception:
        return "", "needs_pdf_dependency"

    try:
        reader = PdfReader(str(path))
        pages = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(f"[page {index}]\n{text}")
        return "\n\n".join(pages), "parsed" if pages else "needs_ocr"
    except Exception as exc:
        return "", f"parse_failed: {exc}"
