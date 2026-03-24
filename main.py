import json
import os
import re
import csv
from glob import glob

from dotenv import load_dotenv

from parser.pdf_parser import hybrid_extract
from parser.document_detector import detect_document_type
from parser.page_filter import filter_pages
from llm.extractor import extract_structured_data
from storage.logger import log_llm

load_dotenv()


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _write_csv(path, rows, columns):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col) for col in columns})


def _normalize_survey_key(value):
    if not value:
        return None
    token = re.sub(r"[^A-Za-z0-9]", "", str(value)).upper()
    return token or None


def _first_non_empty(*values):
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() != "none":
            return text
    return None


def process_single_pdf(pdf_path, save_debug=False):
    print(f"\n[INFO] Processing PDF: {pdf_path}")

    pages = hybrid_extract(pdf_path)
    doc_type = detect_document_type(pages)
    print(f"[INFO] Detected Document Type: {doc_type}")

    relevant_pages = filter_pages(pages, doc_type)
    print("[INFO] Relevant Pages:")
    for page in relevant_pages:
        print(f"  - Page {page['page']}")

    if save_debug:
        base = os.path.splitext(os.path.basename(pdf_path))[0]
        _write_json(f"output/{base}_parsed_pages_raw.json", pages)
        _write_json(f"output/{base}_parsed_pages.json", relevant_pages)

    results = []
    print("[INFO] Extracting structured data...")

    if doc_type in {"lease", "na_order"}:
        merged_text_parts = []
        for page in relevant_pages:
            if page["text"].strip():
                merged_text_parts.append(f"[PAGE {page['page']}]\n{page['text']}")

        merged_text = "\n\n".join(merged_text_parts)
        data, prompt, response = extract_structured_data(merged_text, doc_type)

        if data:
            results.append(data)
            print("[SUCCESS] Merged document extracted")
        else:
            print("[FAILED] Merged document extraction failed")

        log_llm(prompt, response, doc_type, "merged")
    else:
        # Keep e-challan and any other document flows page-wise.
        for page in relevant_pages:
            data, prompt, response = extract_structured_data(page["text"], doc_type)

            if data:
                results.append(data)
                print(f"[SUCCESS] Page {page['page']} extracted")
            else:
                print(f"[FAILED] Page {page['page']} extraction failed")

            log_llm(prompt, response, doc_type, page["page"])

    return {
        "file": pdf_path,
        "doc_type": doc_type,
        "records": results,
        "relevant_pages": [p["page"] for p in relevant_pages],
    }


def normalize_document_records(processed_docs):
    normalized = []

    for doc in processed_docs:
        doc_type = doc.get("doc_type")
        file_name = os.path.basename(doc.get("file", ""))
        records = doc.get("records") or []

        for record in records:
            survey = _first_non_empty(record.get("survey_number"))
            base = {
                "source_file": file_name,
                "doc_type": doc_type,
                "survey_number": survey,
            }

            if doc_type == "na_order":
                base.update(
                    {
                        "NA_village": _first_non_empty(record.get("village")),
                        "NA_area_in_na_order": _first_non_empty(
                            record.get("area_in_na_order"),
                            record.get("land_area"),
                        ),
                        "NA_dated": _first_non_empty(
                            record.get("dated"),
                            record.get("order_date"),
                        ),
                        "NA_order_no": _first_non_empty(record.get("na_order_no")),
                    }
                )
            elif doc_type == "lease":
                base.update(
                    {
                        "LEASE_doc_no": _first_non_empty(record.get("lease_deed_doc_no")),
                        "LEASE_area": _first_non_empty(
                            record.get("lease_area"),
                            record.get("land_area"),
                        ),
                        "LEASE_start": _first_non_empty(
                            record.get("lease_start"),
                            record.get("lease_start_date"),
                        ),
                    }
                )

            normalized.append(base)

    return normalized


def merge_na_and_lease(processed_docs):
    merged = {}

    for doc in processed_docs:
        doc_type = doc.get("doc_type")
        records = doc.get("records") or []

        for record in records:
            survey_number = _first_non_empty(record.get("survey_number"))
            key = _normalize_survey_key(survey_number)
            if not key:
                continue

            if key not in merged:
                merged[key] = {
                    "Village": None,
                    "Survey No.": survey_number,
                    "Area in NA Order": None,
                    "Dated": None,
                    "NA Order No.": None,
                    "Lease Deed Doc. No.": None,
                    "Lease Area": None,
                    "Lease Start": None,
                }

            row = merged[key]
            row["Survey No."] = _first_non_empty(row.get("Survey No."), survey_number)

            if doc_type == "na_order":
                row["Village"] = _first_non_empty(row.get("Village"), record.get("village"))
                row["Area in NA Order"] = _first_non_empty(
                    row.get("Area in NA Order"),
                    record.get("area_in_na_order"),
                    record.get("land_area"),
                )
                row["Dated"] = _first_non_empty(
                    row.get("Dated"),
                    record.get("dated"),
                    record.get("order_date"),
                )
                row["NA Order No."] = _first_non_empty(
                    row.get("NA Order No."),
                    record.get("na_order_no"),
                )

            if doc_type == "lease":
                row["Lease Deed Doc. No."] = _first_non_empty(
                    row.get("Lease Deed Doc. No."),
                    record.get("lease_deed_doc_no"),
                )
                row["Lease Area"] = _first_non_empty(
                    row.get("Lease Area"),
                    record.get("lease_area"),
                    record.get("land_area"),
                )
                row["Lease Start"] = _first_non_empty(
                    row.get("Lease Start"),
                    record.get("lease_start"),
                    record.get("lease_start_date"),
                )

    table = []
    for idx, key in enumerate(sorted(merged.keys()), start=1):
        row = {"Sr.no.": idx}
        row.update(merged[key])
        table.append(row)

    return table


def run_pipeline(pdf_path):
    # Backward-compatible single-file entrypoint.
    processed = process_single_pdf(pdf_path, save_debug=True)
    results = processed["records"]
    _write_json("output/results.json", results)

    print("\n[INFO] Extraction complete!")
    print(f"[INFO] Total records extracted: {len(results)}")
    return results


def run_directory_pipeline(input_dir="data"):
    pdf_files = sorted(glob(os.path.join(input_dir, "*.pdf")))
    if not pdf_files:
        print(f"[WARN] No PDF files found in: {input_dir}")
        _write_json("output/results.json", [])
        return []

    processed_docs = []
    echallan_records = []

    for pdf_path in pdf_files:
        processed = process_single_pdf(pdf_path, save_debug=True)
        processed_docs.append(processed)

        if processed["doc_type"] == "echallan":
            echallan_records.extend(processed["records"])

    normalized_records = normalize_document_records(processed_docs)
    unified_rows = merge_na_and_lease(processed_docs)

    _write_json("output/document_records.json", processed_docs)
    _write_json("output/normalized_records.json", normalized_records)
    _write_json("output/results.json", unified_rows)

    csv_columns = [
        "Sr.no.",
        "Village",
        "Survey No.",
        "Area in NA Order",
        "Dated",
        "NA Order No.",
        "Lease Deed Doc. No.",
        "Lease Area",
        "Lease Start",
    ]
    _write_csv("output/results.csv", unified_rows, csv_columns)

    # Keep e-challan extraction output available separately.
    if echallan_records:
        _write_json("output/echallan_results.json", echallan_records)

    print("\n[INFO] Batch processing complete!")
    print(f"[INFO] Total PDFs processed: {len(processed_docs)}")
    print(f"[INFO] Normalized records: {len(normalized_records)}")
    print(f"[INFO] Unified NA+Lease rows: {len(unified_rows)}")
    if echallan_records:
        print(f"[INFO] eChallan rows (separate): {len(echallan_records)}")

    return unified_rows


if __name__ == "__main__":
    try:
        run_directory_pipeline("data")
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
