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
        "unabkat",
        "e-sign",
        "adobe acrobat",
        "date :",
        " ist",
        "7022026",
        "authsnsed signacor",
        "authorised signatory",
    ]
    return any(marker in lower for marker in footer_markers)


def _is_ocr_garbage(line):
    """Detect lines that are mostly OCR noise (low alphanumeric density)."""
    if len(line) < 4:
        return True
    alnum_count = sum(1 for c in line if c.isalnum())
    ratio = alnum_count / len(line)
    # Lines with very few real characters relative to length are garbage.
    return ratio < 0.35 and len(line) > 5


def _keep_keywords(doc_type):
    if doc_type == "lease":
        return [
            "lease",
            "lease deed",
            "survey",
            "block",
            "area",
            "hectare",
            "sq",
            "acre",
            "સરવે",
            "બ્લોક",
            "ક્ષેત્રફળ",
            "village",
            "moje",
            "mouje",
            "ગામ",
            "doc",
            "document",
            "registration",
            "દસ્તાવેજ",
            "commencing",
            "effective",
            "execution",
            "date",
            "તા.",
            "તારીખ",
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
            "તા.",
            "તારીખ",
            "survey",
            "block",
            "area",
            "order",
            "date",
            "village",
            "moje",
            "mouje",
            "ગામ",
            "case",
            "વશી",
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


def _truncate_at_conditions(text):
    """For NA orders: strip everything from the conditions section onwards.

    All extractable fields (order no, date, village, survey, area) appear
    *before* the 'શરતો :-' marker.  Everything after is boilerplate.
    """
    marker = "શરતો"
    idx = text.find(marker)
    if idx != -1:
        return text[:idx]
    return text


_LEASE_BOILERPLATE_MARKERS = [
    "bonafide needs and requirements",
    "rights, privileges, benefits",
    "rights, privileges",
    "appurtenances, easements",
    "hereinafter contained",
    "hereinafter appearing",
    "terms and conditions",
    "grant of lease",
    "record the said",
    "solar power projects",
    "સૌર પાવર પ્રોજેક્ટ",
    "સૌર ઉર્જાના ઉત્પાદન",
    "પટે લેનાર હાલમાં",
    "absolutely clear and marketable",
    "unencumbered and physical possession",
    "right, interest, claim or concern",
    "approaching the lessors",
    "approached the lessors",
]


def _is_lease_boilerplate(line):
    """Detect pure legal boilerplate in lease deeds that holds no field data."""
    lower = line.lower()
    return any(m in lower for m in _LEASE_BOILERPLATE_MARKERS)


def _basic_clean_lines(text, doc_type=None):
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
        if _is_ocr_garbage(line_stripped):
            continue
        if doc_type == "lease" and _is_lease_boilerplate(line_stripped):
            continue
        if line_stripped in seen_lines:
            continue

        seen_lines.add(line_stripped)
        cleaned.append(line_stripped)

    return cleaned


def _extract_na_core_lines(lines):
    """For NA orders: keep ONLY lines containing the 5 extractable fields.

    Target fields & their line markers:
      - na_order_no  → 'હુકમ નં' (order number line)
      - order_date   → 'તા.' immediately after district line (જિ.)
      - village      → 'ગામ' in the body paragraph
      - survey_number → 'સરવે/બ્લોક નંબર'
      - na_area      → 'વિસ્તાર' (total area)
    """
    core_markers = [
        "હુકમ નં",           # order number
        "સરવે/બ્લોક",        # survey/block number
        "સરવે",              # survey fallback
        "વિસ્તાર",           # total area
        "ક્ષેત્રફળ",          # leased area (useful context)
        "ગામ",               # village
    ]
    # Also keep the order date line: 'તા.DD/MM/YYYY' that appears right after 'જિ.'
    keep = []
    prev_was_district = False
    for line in lines:
        lower = line.lower()
        # Keep the date line immediately after district header
        if prev_was_district and "તા." in line:
            keep.append(line)
            prev_was_district = False
            continue
        prev_was_district = "જિ." in line or "જિ " in line

        if any(m in line for m in core_markers):
            keep.append(line)
    return keep


def clean_irrelevant_lines(text, doc_type):
    # Reparse OCR payload: keep the strongest OCR variant before line-level filtering.
    reparsed_text = _select_best_ocr_variant(text, doc_type)

    # Section-level truncation: for NA orders, cut everything after conditions.
    if doc_type == "na_order":
        reparsed_text = _truncate_at_conditions(reparsed_text)

    lines = _basic_clean_lines(reparsed_text, doc_type)
    if not lines:
        return ""

    # NA orders: precision extraction — keep only lines with target field data.
    if doc_type == "na_order":
        core = _extract_na_core_lines(lines)
        if core:
            return "\n".join(core)
        # Fallback: return all cleaned lines if precision extraction found nothing.
        return "\n".join(lines)

    # Lease docs: the lease_pipeline has its own page classification + regex
    # extraction that needs the full text context.  Only basic cleaning
    # (footers, OCR garbage, boilerplate) is applied — no keyword filtering.
    if doc_type == "lease":
        return "\n".join(lines)

    # Unknown doc types: keyword-only filtering.
    keep_keywords = _keep_keywords(doc_type)
    if not keep_keywords:
        return "\n".join(lines)

    keep_indices = set()
    for i, line in enumerate(lines):
        lower = line.lower()
        if any(keyword in lower for keyword in keep_keywords):
            keep_indices.add(i)

    # Fall back to basic cleaned lines if keyword matching is too sparse.
    if len(keep_indices) < 3:
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
            "હુકમ નં",
            "સરવે",
            "સર્વે",
            "બ્લોક",
            "ક્ષેત્રફળ",
            "ચો.મી",
            "survey",
            "block",
            "area",
            "order no",
        ]
        weak = ["તા.", "date", "પ્રાંત કચેરી", "village", "ગામ", "moje", "mouje"]
        strong_hits = _keyword_count(cleaned_text, strong)
        weak_hits = _keyword_count(cleaned_text, weak)
        return strong_hits >= 2 or (strong_hits >= 1 and weak_hits >= 2)

    if doc_type == "lease":
        strong = [
            "survey",
            "block",
            "area",
            "hectare",
            "acre",
            "સરવે",
            "બ્લોક",
            "ક્ષેત્રફળ",
            "village",
            "ગામ",
            "moje",
            "mouje",
            "book no",
            "registered no",
            "registration no",
            "document no",
        ]
        weak = [
            "doc no",
            "document",
            "દસ્તાવેજ",
            "registration",
            "date",
            "commencing",
            "effective",
        ]
        strong_hits = _keyword_count(cleaned_text, strong)
        weak_hits = _keyword_count(cleaned_text, weak)
        return strong_hits >= 2 or (strong_hits >= 1 and weak_hits >= 2)

    return True


def filter_pages(pages, doc_type):
    relevant = []

    # Business rule: for target pipeline we only process fixed pages for these docs.
    if doc_type == "na_order":
        target_pages = {1}
    elif doc_type == "lease":
        target_pages = {3, 4, 33, 35, 51}
    else:
        target_pages = None

    for p in pages:
        if target_pages is not None and p["page"] not in target_pages:
            continue

        text = p["text"]

        # Clean the text based on document type to remove irrelevant boilerplate
        cleaned_text = clean_irrelevant_lines(text, doc_type)

        if not _is_relevant_page(cleaned_text, doc_type):
            continue

        if doc_type == "lease":
            # The lease flow already uses fixed target pages. Keep pages that pass
            # cleaned-text relevance checks to reduce noisy payload.
            if cleaned_text.strip():
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
        if doc_type == "lease":
            # Prefer fixed lease pages fallback as requested.
            lease_fallback = [p for p in pages if p["page"] in {3, 4, 33, 35, 51}]
            if lease_fallback:
                first = lease_fallback[0]
            else:
                first = pages[0]
        else:
            first = pages[0]

        relevant.append(
            {
                "page": first["page"],
                "text": clean_irrelevant_lines(first["text"], doc_type),
            }
        )

    return relevant
