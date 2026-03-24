import pdfplumber
import pytesseract
from pdf2image import convert_from_path
import cv2
import numpy as np


def clean_text(text):
    if not text:
        return ""
    return text.strip()


def is_garbage(text):
    return "(cid:" in text or len(text.strip()) < 20


def _resolve_target_pages(total_pages, page_numbers=None, max_pages=None):
    if page_numbers is None:
        targets = list(range(1, total_pages + 1))
    else:
        targets = sorted({p for p in page_numbers if 1 <= p <= total_pages})

    if max_pages is not None:
        targets = targets[:max_pages]

    return targets


def extract_text_pdfplumber(pdf_path, page_numbers=None, max_pages=None):
    pages_text = []

    with pdfplumber.open(pdf_path) as pdf:
        targets = _resolve_target_pages(
            total_pages=len(pdf.pages),
            page_numbers=page_numbers,
            max_pages=max_pages,
        )

        for page_number in targets:
            page = pdf.pages[page_number - 1]
            text = page.extract_text()
            pages_text.append({
                "page": page_number,
                "text": clean_text(text)
            })

    return pages_text


def preprocess_image_for_ocr(img):
    """Enhance image for OCR using OpenCV (resizing, grayscale, thresholding)."""
    # Convert PIL Image to OpenCV format (numpy array)
    cv_img = np.array(img)
    # Convert RGB to BGR if necessary
    if len(cv_img.shape) == 3 and cv_img.shape[2] == 3:
        cv_img = cv_img[:, :, ::-1].copy()
    
    # 1. Resize image to 2.0x to improve small text recognition (like footers)
    # INTER_LANCZOS4 is sharper than CUBIC, preventing loops in '5' from blurring into '8'
    width = int(cv_img.shape[1] * 2.0)
    height = int(cv_img.shape[0] * 2.0)
    cv_img = cv2.resize(cv_img, (width, height), interpolation=cv2.INTER_LANCZOS4)
    
    # 2. Convert to grayscale
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    
    # We remove explicit Otsu thresholding because Tesseract's internal adaptive
    # thresholding (Leptonica) is much better at keeping small features like the gap in '5'
    # open across different page lighting conditions.
    
    return gray


def extract_text_ocr_images(images, page_index):
    img = images[page_index]
    
    # Preprocess the image to improve text clarity, especially for small dates
    preprocessed_img = preprocess_image_for_ocr(img)

    # Multi-language segmentation modes
    text_psm3 = pytesseract.image_to_string(
        preprocessed_img,
        lang="eng+hin+guj",
        config="--psm 3"
    )

    text_psm6 = pytesseract.image_to_string(
        img,
        lang="eng+hin+guj",
        config="--psm 6"
    )
    
    # Clean the spacing of both
    t3 = clean_text(text_psm3)
    t6 = clean_text(text_psm6)

    # Token Optimization: If the engine produced the exact same text for both PSM modes, 
    # only return one copy to avoid doubling the token cost.
    if t3 == t6:
        return t3

    # Return pure raw text (only for the distinct outputs).
    combined = f"--- OCR OUTPUT 1 ---\n{t3}\n\n--- OCR OUTPUT 2 ---\n{t6}"
    return clean_text(combined)


def _extract_text_ocr_single_page(pdf_path, page_number):
    images = convert_from_path(
        pdf_path,
        dpi=300,
        first_page=page_number,
        last_page=page_number,
    )
    if not images:
        return ""
    return extract_text_ocr_images(images, 0)


def hybrid_extract(pdf_path, page_numbers=None, max_pages=None):
    pages = extract_text_pdfplumber(
        pdf_path,
        page_numbers=page_numbers,
        max_pages=max_pages,
    )

    final_pages = []

    for page in pages:
        text = page["text"]

        if text and not is_garbage(text):
            final_pages.append(page)
        else:
            print(f"[INFO] Using OCR for page {page['page']}")
            ocr_text = _extract_text_ocr_single_page(pdf_path, page["page"])

            final_pages.append({
                "page": page["page"],
                "text": ocr_text
            })

    return final_pages