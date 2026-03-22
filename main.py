import json
from parser.pdf_parser import hybrid_extract
from parser.document_detector import detect_document_type
from parser.page_filter import filter_pages


def run_pipeline(pdf_path):
    # Step 1: Extract text
    pages = hybrid_extract(pdf_path)

    # Save raw output (debugging)
    with open("output/parsed_pages.json", "w", encoding="utf-8") as f:
        json.dump(pages, f, indent=2, ensure_ascii=False)

    # Step 2: Detect document type
    doc_type = detect_document_type(pages)
    print(f"\n[INFO] Detected Document Type: {doc_type}")

    # Step 2: Filter relevant pages
    relevant_pages = filter_pages(pages, doc_type)

    print("\n[INFO] Relevant Pages:")
    for p in relevant_pages:
        print(f"Page {p['page']}")

    return relevant_pages

if __name__ == "__main__":
    run_pipeline("data/e2.pdf")