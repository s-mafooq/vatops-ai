import pdfplumber
import os


def extract_text_from_pdf(file_path: str) -> tuple[str, str]:
    """
    Extract and aggregate text from all pages of a PDF.
    Returns (extracted_text, status)
    """
    try:
        pages_text = []

        with pdfplumber.open(file_path) as pdf:
            total_pages = len(pdf.pages)

            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text and text.strip():
                    pages_text.append(f"[Page {i+1} of {total_pages}]\n{text.strip()}")

        full_text = "\n\n".join(pages_text)

        # If we got very little text across ALL pages, it's likely scanned
        if len(full_text.strip()) < 50:
            return "", "scanned"

        return full_text.strip(), "ok"

    except Exception as e:
        return "", f"error: {str(e)}"


def extract_text_from_txt(file_path: str) -> tuple[str, str]:
    """Read plain text files directly."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read().strip(), "ok"
    except Exception as e:
        return "", f"error: {str(e)}"


def process_file(file_path: str) -> tuple[str, str]:
    """
    Route file to the right extractor based on extension.
    Returns (text, status)
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext == ".txt":
        return extract_text_from_txt(file_path)
    elif ext in [".png", ".jpg", ".jpeg"]:
        return "", "image"
    else:
        return "", f"error: unsupported file type {ext}"