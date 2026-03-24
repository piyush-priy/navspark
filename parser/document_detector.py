import os
import re


def detect_document_type_from_filename(file_path):
    file_name = os.path.basename(file_path).lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", file_name)

    # Accept small spelling noise while still requiring lease+deed intent.
    has_lease = bool(re.search(r"\ble+a+s+e\b", normalized)) or "lease" in normalized
    has_deed = "deed" in normalized

    if has_lease and has_deed:
        return "lease"

    if "final order" in normalized:
        return "na_order"

    return None


def detect_document_type(pages):
    # Process the entire document text to ensure we don't miss classification keywords
    combined_text = " ".join([p["text"] for p in pages]).lower()

    scores = {"lease": 0, "na_order": 0}

    # Lease keywords (STRONG SIGNAL)
    if "lease deed" in combined_text:
        scores["lease"] += 3
    if "lessor" in combined_text or "lessee" in combined_text:
        scores["lease"] += 2
    if "agreement" in combined_text:
        scores["lease"] += 1

    # NA Order keywords
    if "હુકમ" in combined_text:
        scores["na_order"] += 2
    if "પરિશિષ્ટ" in combined_text:
        scores["na_order"] += 1

    # Debug print (VERY USEFUL)
    print(f"[DEBUG] Scores: {scores}")

    # Return highest score
    return max(scores, key=scores.get)
