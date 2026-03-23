import json
from dotenv import load_dotenv
load_dotenv()

from parser.pdf_parser import hybrid_extract
from parser.document_detector import detect_document_type
from parser.page_filter import filter_pages

from llm.extractor import extract_structured_data
from storage.logger import log_llm



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

    # 🔥 STEP 3 STARTS HERE
    results = []

    print("\n[INFO] Extracting structured data...\n")

    for page in relevant_pages:
        data, prompt, response = extract_structured_data(
            page["text"],
            doc_type   # ⭐ VERY IMPORTANT
        )

        if data:
            results.append(data)
            print(f"[SUCCESS] Page {page['page']} extracted")
        else:
            print(f"[FAILED] Page {page['page']} extraction failed")

        # Audit logging (required)
        log_llm(prompt, response, doc_type, page["page"])

    # Save final structured output (debugging)
    with open("output/results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("\n[INFO] Extraction complete!")
    print(f"[INFO] Total records extracted: {len(results)}")

    return results


if __name__ == "__main__":
    run_pipeline("data/e3.pdf")