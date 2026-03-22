def detect_document_type(pages):
    combined_text = " ".join(
        [p["text"][:1000] for p in pages[:5]]
    ).lower()

    scores = {
        "echallan": 0,
        "lease": 0,
        "na_order": 0
    }

    # eChallan keywords
    if "challan" in combined_text:
        scores["echallan"] += 2
    if "vehicle" in combined_text:
        scores["echallan"] += 1

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