import re


def _contains_alnum(line):
    return any(c.isalnum() for c in line)


def _is_footer_or_signature(line):
    lower = line.lower()
    footer_markers = [
        "ocr output",
        "signature not",
        "signed by",
        "open the document in adobe",
        "courtesy: nic",
        "application no.",
        "order no.",
        "page ",
        "unadkat",
    ]
    return any(marker in lower for marker in footer_markers)


def _keep_keywords(doc_type):
    if doc_type == "lease":
        return [
            "lease",
            "lease deed",
            "lessor",
            "lessee",
            "owner",
            "company",
            "survey",
            "block",
            "area",
            "hectare",
            "sq",
            "acre",
            "duration",
            "year",
            "month",
            "agreement",
            "rent",
            "amount",
            "execute",
            "સરવે",
            "બ્લોક",
            "લીઝ",
            "ભાડા",
            "માલિક",
            "ક્ષેત્રફળ",
            "વર્ષ",
            "માસ",
            "કંપની",
            "અરજદાર",
        ]

    if doc_type == "na_order":
        return [
            "હુકમ",
            "પરિશિષ્ટ",
            "સરવે",
            "બ્લોક",
            "ક્ષેત્રફળ",
            "ચો.મી",
            "જમીન",
            "અરજદાર",
            "અધિકૃત",
            "કંપની",
            "તા.",
            "તારીખ",
            "વર્ષ",
            "માસ",
            "દિવસ",
            "survey",
            "block",
            "area",
            "company",
            "order",
            "date",
            "year",
            "month",
            "day",
        ]

    if doc_type == "echallan":
        return [
            "challan",
            "vehicle",
            "violation",
            "amount",
            "offence",
            "payment",
        ]

    return []


def _extract_ocr_variants(text):
    # Split text by OCR markers like "--- OCR OUTPUT 1 ---" and return non-empty chunks.
    if "--- OCR OUTPUT" not in text:
        return [text]

    parts = re.split(r"---\s*OCR\s*OUTPUT\s*\d*\s*---", text, flags=re.IGNORECASE)
    variants = [p.strip() for p in parts if p.strip()]
    return variants if variants else [text]


def _score_variant(variant, doc_type):
    lines = [ln.strip() for ln in variant.split("\n") if ln.strip()]
    keywords = _keep_keywords(doc_type)

    score = 0
    for line in lines:
        lower = line.lower()
        if any(kw in lower for kw in keywords):
            score += 5
        if any(ch.isdigit() for ch in line):
            score += 2
        if 8 <= len(line) <= 220:
            score += 1

    # Penalize obvious footer/signature noise.
    score -= sum(2 for line in lines if _is_footer_or_signature(line))
    return score


def _select_best_ocr_variant(text, doc_type):
    variants = _extract_ocr_variants(text)
    if len(variants) == 1:
        return variants[0]

    ranked = sorted(
        variants,
        key=lambda v: _score_variant(v, doc_type),
        reverse=True,
    )
    return ranked[0]


def _basic_clean_lines(text):
    lines = text.split("\n")
    cleaned = []
    seen_lines = set()

    for line in lines:
        line_stripped = line.strip()
        line_stripped = re.sub(r"\s+", " ", line_stripped)
        if len(line_stripped) <= 2:
            continue
        if not _contains_alnum(line_stripped):
            continue
        if _is_footer_or_signature(line_stripped):
            continue
        if line_stripped in seen_lines:
            continue

        seen_lines.add(line_stripped)
        cleaned.append(line_stripped)

    return cleaned


def clean_irrelevant_lines(text, doc_type):
    # Reparse OCR payload: keep the strongest OCR variant before line-level filtering.
    reparsed_text = _select_best_ocr_variant(text, doc_type)

    lines = _basic_clean_lines(reparsed_text)
    if not lines:
        return ""

    keep_keywords = _keep_keywords(doc_type)
    if not keep_keywords:
        return "\n".join(lines)

    # Keep lines that contain strong document-specific keywords and keep local context.
    keep_indices = set()
    for i, line in enumerate(lines):
        lower = line.lower()
        if any(keyword in lower for keyword in keep_keywords):
            keep_indices.add(i)
            if i - 1 >= 0:
                keep_indices.add(i - 1)
            if i + 1 < len(lines):
                keep_indices.add(i + 1)

    # Fall back to basic cleaned lines if keyword matching is too sparse on noisy OCR.
    if len(keep_indices) < 5:
        return "\n".join(lines)

    selected = [lines[i] for i in sorted(keep_indices)]
    return "\n".join(selected)


def _keyword_count(text, keywords):
    lower = text.lower()
    return sum(1 for kw in keywords if kw in lower)


def _is_relevant_page(cleaned_text, doc_type):
    # Keep only pages that contain core field signals, not just generic legal text.
    if not cleaned_text.strip():
        return False

    if doc_type == "na_order":
        strong = [
            "હુકમ નં", "સરવે", "સર્વે", "બ્લોક", "ક્ષેત્રફળ", "ચો.મી",
            "survey", "block", "area", "order no"
        ]
        weak = [
            "અરજદાર", "અધિકૃત", "company", "limited", "તા.", "date", "પ્રાંત કચેરી"
        ]
        strong_hits = _keyword_count(cleaned_text, strong)
        weak_hits = _keyword_count(cleaned_text, weak)
        return strong_hits >= 2 or (strong_hits >= 1 and weak_hits >= 2)

    if doc_type == "lease":
        strong = [
            "survey", "block", "area", "hectare", "acre", "lessor", "lessee",
            "owner", "duration", "rent", "સરવે", "બ્લોક", "ક્ષેત્રફળ", "લીઝ", "માલિક"
        ]
        weak = ["company", "limited", "agreement", "year", "month", "વર્ષ", "માસ"]
        strong_hits = _keyword_count(cleaned_text, strong)
        weak_hits = _keyword_count(cleaned_text, weak)
        return strong_hits >= 2 or (strong_hits >= 1 and weak_hits >= 2)

    if doc_type == "echallan":
        strong = [
            "challan", "challan no", "vehicle", "vehicle no", "violation",
            "offence", "amount", "payment", "date", "time"
        ]
        strong_hits = _keyword_count(cleaned_text, strong)
        has_date_pattern = bool(
            re.search(r"\b\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{2,4}\b", cleaned_text)
        )
        # Accept if core challan signals exist, or one signal plus an actual date pattern.
        return strong_hits >= 2 or (strong_hits >= 1 and has_date_pattern)

    return True


def filter_pages(pages, doc_type):
    relevant = []

    for p in pages:
        text = p["text"]
        
        # Clean the text based on document type to remove irrelevant boilerplate
        cleaned_text = clean_irrelevant_lines(text, doc_type)

        if not _is_relevant_page(cleaned_text, doc_type):
            continue

        if doc_type == "echallan":
            if "challan" in text.lower():
                relevant.append({"page": p["page"], "text": cleaned_text})

        elif doc_type == "lease":
            if (
                "survey" in text.lower()
                or "₹" in text
                or "amount" in text.lower()
                or "lessee" in text.lower()
                or "lease" in text.lower()
                or "લીઝ" in text
                or "સરવે" in text
            ):
                relevant.append({"page": p["page"], "text": cleaned_text})

        elif doc_type == "na_order":
            if "હુકમ" in text or "સર્વે" in text or "સરવે" in text or "પરિશિષ્ટ" in text:
                relevant.append({"page": p["page"], "text": cleaned_text})

        else:
            # fallback: keep first few pages
            if p["page"] <= 3:
                relevant.append({"page": p["page"], "text": cleaned_text})

    # Safety fallback: if everything gets filtered out, keep the first cleaned page.
    if not relevant and pages:
        first = pages[0]
        relevant.append({"page": first["page"], "text": clean_irrelevant_lines(first["text"], doc_type)})

    return relevant