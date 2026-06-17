from pathlib import Path

from bs4 import BeautifulSoup


def extract_text_file(path: Path) -> str:
    for encoding in ("utf-8", "gb18030"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = path.read_bytes().decode("utf-8", errors="ignore")

    if path.suffix.lower() in {".html", ".htm"}:
        return BeautifulSoup(text, "html.parser").get_text("\n", strip=True)
    return text


def extract_docx_text(path: Path) -> tuple[str, str]:
    try:
        import zipfile
        from xml.etree import ElementTree

        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(xml)
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs = []
        for paragraph in root.findall(".//w:p", namespace):
            parts = [
                node.text or ""
                for node in paragraph.findall(".//w:t", namespace)
                if node.text
            ]
            if parts:
                paragraphs.append("".join(parts))
        text = "\n".join(paragraphs)
        return text, "parsed" if text.strip() else "parse_failed"
    except Exception as exc:
        return "", f"parse_failed: {exc}"
