import json
import os
import re
from glob import glob

from dotenv import load_dotenv

from parser.pdf_parser import hybrid_extract
from parser.document_detector import (
    detect_document_type,
    detect_document_type_from_filename,
)
from parser.page_filter import filter_pages
from parser.lease_pipeline import (
    extract_lease_record_from_pages,
    extract_doc_no_from_filename,
    extract_survey_from_filename,
    extract_survey_from_na_filename,
)
from parser.na_pipeline import extract_na_record_from_text
from llm.extractor import extract_structured_data
from storage.logger import log_llm

load_dotenv()


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _write_xlsx(path, rows, columns):
    from openpyxl import Workbook
    os.makedirs(os.path.dirname(path), exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.append(columns)
    for row in rows:
        ws.append([row.get(col) for col in columns])
    wb.save(path)


def _normalize_survey_key(value):
    if not value:
        return None
    # Remove whitespace, uppercase
    token = re.sub(r"\s+", "", str(value)).upper()
    # Split by / or - and normalize each part
    parts = re.split(r"[/\-]", token)
    normalized_parts = []
    for part in parts:
        # Remove non-alphanumeric
        cleaned = re.sub(r"[^A-Z0-9]", "", part)
        # Remove leading zeros from numeric-only parts
        if cleaned.isdigit():
            cleaned = cleaned.lstrip("0") or "0"
        normalized_parts.append(cleaned)
    result = "/".join(normalized_parts)
    return result or None


def _normalize_area(value):
    """Normalize area value to plain integer string (e.g., '16,534.00 ચો.મી.' → '16534')."""
    if not value:
        return None
    # Remove everything except digits and dots
    cleaned = re.sub(r"[^\d.]", "", str(value))
    if not cleaned:
        return value
    try:
        num = float(cleaned)
        return str(int(num)) if num == int(num) else str(num)
    except (ValueError, OverflowError):
        return value


def _first_non_empty(*values):
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() != "none":
            return text
    return None


def _target_pages_for_doc_type(doc_type):
    if doc_type == "na_order":
        return [1]
    if doc_type == "lease":
        return [3, 4, 33, 35, 51] 
    return None


def process_single_pdf(pdf_path):
    print(f"\n[INFO] Processing PDF: {pdf_path}")

    file_type = detect_document_type_from_filename(pdf_path)
    if file_type:
        doc_type = file_type
        print(f"[INFO] Detected Document Type from filename: {doc_type}")
    else:
        print(
            "[INFO] Filename did not match known types; scanning first 5 pages for detection"
        )
        preview_pages = hybrid_extract(pdf_path, max_pages=5)
        doc_type = detect_document_type(preview_pages)

    target_pages = _target_pages_for_doc_type(doc_type)
    if target_pages:
        pages = hybrid_extract(pdf_path, page_numbers=target_pages)
    else:
        pages = hybrid_extract(pdf_path)

    print(f"[INFO] Detected Document Type: {doc_type}")

    relevant_pages = filter_pages(pages, doc_type)
    print("[INFO] Relevant Pages:")
    for page in relevant_pages:
        print(f"  - Page {page['page']}")

    # Deterministic NA order extraction: all fields are on page 1 in a rigid template.
    deterministic_records = []
    if doc_type == "na_order":
        merged_text = "\n".join(p["text"] for p in relevant_pages if p["text"].strip())
        na_record = extract_na_record_from_text(merged_text)

        # Overlay filename-based survey number (more reliable than OCR).
        base_name = os.path.basename(pdf_path)
        fname_survey = extract_survey_from_na_filename(base_name)
        if fname_survey:
            na_record["survey_number"] = fname_survey

        has_core = _first_non_empty(
            na_record.get("na_area"),
            na_record.get("na_order_no"),
            na_record.get("survey_number"),
        ) is not None

        if has_core:
            print(f"[SUCCESS] Deterministic NA extraction: {na_record}")
            deterministic_records = [na_record]
        else:
            print("[WARN] Deterministic NA extraction failed, relying purely on LLM")

    # Deterministic lease extraction: classify pages and extract key fields directly.
    if doc_type == "lease":
        lease_record = extract_lease_record_from_pages(relevant_pages, all_pages=pages)

        # Fallback: extract doc_no and survey from filename when OCR fails.
        base_name = os.path.basename(pdf_path)
        if not lease_record.get("lease_deed_doc_no"):
            fname_doc_no = extract_doc_no_from_filename(base_name)
            if fname_doc_no:
                lease_record["lease_deed_doc_no"] = fname_doc_no
        fname_survey = extract_survey_from_filename(base_name)
        if fname_survey:
            lease_record["survey_number"] = fname_survey

        has_core_values = (
            _first_non_empty(
                lease_record.get("lease_deed_doc_no"),
                lease_record.get("lease_area"),
                lease_record.get("lease_start"),
                lease_record.get("survey_number"),
            )
            is not None
        )

        if has_core_values:
            print(f"[SUCCESS] Deterministic Lease extraction: {lease_record}")
            deterministic_records = [lease_record]
        else:
            print("[WARN] Deterministic Lease extraction failed, relying purely on LLM")

    # For docs where deterministic extraction failed, prepare LLM text payloads.
    llm_inputs = []
    if doc_type in {"lease", "na_order"}:
        merged_text_parts = []
        for page in relevant_pages:
            if page["text"].strip():
                merged_text_parts.append(f"[PAGE {page['page']}]\n{page['text']}")

        merged_text = "\n\n".join(merged_text_parts)
        llm_inputs.append({"page": "merged", "text": merged_text})
    else:
        # Fallback for unknown types if any.
        for page in relevant_pages:
            llm_inputs.append({"page": page["page"], "text": page["text"]})

    return {
        "file": pdf_path,
        "doc_type": doc_type,
        "records": [],
        "deterministic_records": deterministic_records,
        "llm_inputs": llm_inputs,
        "relevant_pages": [p["page"] for p in relevant_pages],
    }


def run_llm_final_step(processed_docs):
    print("\n[INFO] Running final LLM extraction step...")

    for doc in processed_docs:
        doc_type = doc.get("doc_type")
        inputs = doc.get("llm_inputs") or []
        file_name = os.path.basename(doc.get("file", ""))

        if not inputs:
            continue

        print(f"[INFO] LLM extraction: {file_name} ({doc_type})")
        results = []

        for item in inputs:
            page_marker = item.get("page")
            text = item.get("text") or ""
            data, prompt, response = extract_structured_data(text, doc_type)

            if prompt == "" and response == "":
                print(f"[SKIPPED] Low-signal payload: {page_marker}")
                continue

            if data:
                # Merge LLM output base with Deterministic highly-accurate overrides
                merged_data = data
                d_records = doc.get("deterministic_records") or []
                if d_records:
                    d_rec = d_records[0]
                    for key, val in d_rec.items():
                        # Override LLM values ONLY if the deterministic parser found a non-null, valid value
                        if val is not None and not str(key).startswith("_"):
                            merged_data[key] = val
                            
                results.append(merged_data)
                print(f"[SUCCESS] Extracted payload: {page_marker}")
            else:
                print(f"[FAILED] Extracted payload: {page_marker}")

            log_llm(prompt, response, doc_type, page_marker)

        # If LLM failed completely/rate-limited, fallback directly to deterministic core data
        if not results and doc.get("deterministic_records"):
            print(f"[WARN] LLM extraction returned no results. Falling back to deterministic.")
            results = doc.get("deterministic_records")

        doc["records"] = results


def merge_na_and_lease(processed_docs):
    merged = {}

    for doc in processed_docs:
        doc_type = doc.get("doc_type")
        records = doc.get("records") or []
        file_path = doc.get("file", "")
        base_name = os.path.basename(file_path)

        # Use filename-derived survey number for NA docs as a more reliable source.
        fname_survey = None
        if doc_type == "na_order":
            fname_survey = extract_survey_from_na_filename(base_name)

        for record in records:
            survey_number = _first_non_empty(fname_survey, record.get("survey_number"))
            key = _normalize_survey_key(survey_number)
            if not key:
                continue

            if key not in merged:
                merged[key] = {
                    "Sr.no.": None,
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
                row["Village"] = _first_non_empty(
                    row.get("Village"), record.get("village")
                )
                row["Area in NA Order"] = _normalize_area(
                    _first_non_empty(
                        row.get("Area in NA Order"),
                        record.get("area_in_na_order"),
                        record.get("na_area"),
                        record.get("land_area"),
                    )
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
                row["Lease Area"] = _normalize_area(
                    _first_non_empty(
                        row.get("Lease Area"),
                        record.get("lease_area"),
                        record.get("land_area"),
                    )
                )
                row["Lease Start"] = _first_non_empty(
                    row.get("Lease Start"),
                    record.get("lease_start"),
                    record.get("lease_start_date"),
                )

    table = []
    for idx, key in enumerate(sorted(merged.keys()), start=1):
        row = merged[key]
        row["Sr.no."] = idx
        table.append(row)

    return table


def run_directory_pipeline(input_dir="data"):
    pdf_files = sorted(glob(os.path.join(input_dir, "*.pdf")))
    if not pdf_files:
        print(f"[WARN] No PDF files found in: {input_dir}")
        _write_json("output/results.json", [])
        return []

    processed_docs = []

    for pdf_path in pdf_files:
        processed = process_single_pdf(pdf_path)
        processed_docs.append(processed)

    # LLM is intentionally called only after all files have been extracted and optimized.
    run_llm_final_step(processed_docs)

    unified_rows = merge_na_and_lease(processed_docs)

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
    _write_xlsx("output/results.xlsx", unified_rows, csv_columns)

    print("\n[INFO] Batch processing complete!")
    print(f"[INFO] Total PDFs processed: {len(processed_docs)}")
    print(f"[INFO] Unified NA+Lease rows: {len(unified_rows)}")

    return unified_rows


if __name__ == "__main__":
    try:
        run_directory_pipeline("data")
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
