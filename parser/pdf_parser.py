import pdfplumber
import pytesseract
from pdf2image import convert_from_path


def clean_text(text):
    if not text:
        return ""
    return text.replace("\n", " ").strip()


def is_garbage(text):
    return "(cid:" in text or len(text.strip()) < 20


def extract_text_pdfplumber(pdf_path):
    pages_text = []

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            pages_text.append({
                "page": i + 1,
                "text": clean_text(text)
            })

    return pages_text


def extract_text_ocr_images(images, page_index):
    img = images[page_index]

    text = pytesseract.image_to_string(
        img,
        lang="eng+hin+guj"
    )

    return clean_text(text)


def hybrid_extract(pdf_path):
    pages = extract_text_pdfplumber(pdf_path)
    images = convert_from_path(pdf_path)

    final_pages = []

    for i, page in enumerate(pages):
        text = page["text"]

        if text and not is_garbage(text):
            final_pages.append(page)
        else:
            print(f"[INFO] Using OCR for page {page['page']}")
            ocr_text = extract_text_ocr_images(images, i)

            final_pages.append({
                "page": page["page"],
                "text": ocr_text
            })

    return final_pages