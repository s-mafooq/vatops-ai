import pdfplumber
import os
import struct


def extract_text_from_pdf(file_path: str) -> tuple[str, str]:
    try:
        pages_text = []
        with pdfplumber.open(file_path) as pdf:
            total_pages = len(pdf.pages)
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text and text.strip():
                    pages_text.append(f"[Page {i+1} of {total_pages}]\n{text.strip()}")

        full_text = "\n\n".join(pages_text)

        if len(full_text.strip()) < 50:
            return "", "scanned"

        return full_text.strip(), "ok"

    except Exception as e:
        return "", f"error: {str(e)}"


def extract_text_from_txt(file_path: str) -> tuple[str, str]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read().strip(), "ok"
    except UnicodeDecodeError:
        try:
            with open(file_path, "r", encoding="latin-1") as f:
                return f.read().strip(), "ok"
        except Exception as e:
            return "", f"error: {str(e)}"
    except Exception as e:
        return "", f"error: {str(e)}"


def extract_text_from_image(file_path: str) -> tuple[str, str]:
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(file_path)
        # Convert to RGB if needed
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        text = pytesseract.image_to_string(img)
        if text and len(text.strip()) > 20:
            return text.strip(), "ok"
        return "", "scanned"
    except ImportError:
        return "", "image"
    except Exception as e:
        return "", f"error: {str(e)}"


def process_file(file_path: str) -> tuple[str, str]:
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext == ".txt":
        return extract_text_from_txt(file_path)
    elif ext in [".png", ".jpg", ".jpeg"]:
        return extract_text_from_image(file_path)
    else:
        return "", f"error: unsupported file type {ext}"