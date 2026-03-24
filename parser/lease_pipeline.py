import re


def extract_doc_no_from_filename(filename):
    """Extract lease deed doc number from the PDF filename."""
    m = re.search(r"(?:Lease\s*Deed\s*No\.?\s*[-:]?\s*)(\d+)", filename, re.IGNORECASE)
    return m.group(1) if m else None


def extract_survey_from_filename(filename):
    """Extract survey number from a lease filename like 'S.No.- 251p2'."""
    m = re.search(r"S\.?No\.?\s*[-:]?\s*(\S+?)(?:\s+Lease|\s*$)", filename, re.IGNORECASE)
    if m:
        raw = m.group(1).strip().rstrip("-")
        # Normalize: insert / before alpha suffix (251p2 → 251/p2)
        raw = re.sub(r"(\d)([a-zA-Z])", r"\1/\2", raw)
        return raw
    return None


def extract_survey_from_na_filename(filename):
    """Extract survey number from an NA filename like '251-p2 FINAL ORDER.pdf'."""
    m = re.search(r"^([\d]+(?:[-/][a-zA-Z0-9]+)?)\s+FINAL\s+ORDER", filename, re.IGNORECASE)
    if m:
        raw = m.group(1)
        return raw.replace("-", "/")
    return None


_DATE_PATTERN = re.compile(r"\b(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{2,4})\b")


def _normalize_whitespace(text):
	return re.sub(r"\s+", " ", text).strip()


def _normalize_for_matching(text):
	if not text:
		return ""

	# Keep Gujarati/Unicode letters but drop noisy control-like symbols.
	text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
	text = text.replace("\u200c", " ").replace("\u200d", " ")

	lowered = text.lower()
	lowered = re.sub(r"sq\.?\s*m\b", "sqm", lowered)
	lowered = re.sub(r"square\s*meters?", "sqm", lowered)

	# OCR normalization in numeric contexts only.
	lowered = re.sub(r"(?<=\d)[oO](?=\d)", "0", lowered)
	lowered = re.sub(r"(?<=\d)[iIl](?=\d)", "1", lowered)
	lowered = re.sub(r"(?<=\d)[sS](?=\d)", "5", lowered)
	lowered = re.sub(r"(?<=[a-z])[0](?=[a-z])", "o", lowered)

	return _normalize_whitespace(lowered)


def _normalize_date(raw_date):
	if not raw_date:
		return None

	m = _DATE_PATTERN.search(raw_date)
	if not m:
		return None

	day = m.group(1).zfill(2)
	month = m.group(2).zfill(2)
	year = m.group(3)
	if len(year) == 2:
		year = "20" + year

	return f"{day}/{month}/{year}"


def _all_dates(text):
	dates = []
	for m in _DATE_PATTERN.finditer(text or ""):
		normalized = _normalize_date(m.group(0))
		if normalized:
			dates.append(normalized)
	return dates


def classify_page(text):
	normalized = _normalize_for_matching(text)

	if (
		"book no" in normalized
		or "registered no" in normalized
		or "registration no" in normalized
		or "document no" in normalized
		or "doc no" in normalized
	):
		return "registration"

	if "lease deed" in normalized or ("lessor" in normalized and "lessee" in normalized):
		return "first_page"

	if (
		"lease term" in normalized
		or "commencing from" in normalized
		or "effective date" in normalized
		or "term of this lease" in normalized
	):
		return "term"

	if (
		"annexure" in normalized
		or "village" in normalized
		and "survey" in normalized
		and ("area" in normalized or "sqm" in normalized)
	):
		return "annexure"

	if (
		"survey no" in normalized
		or "survey number" in normalized
		or "measuring" in normalized
		or "sqm" in normalized
		or "sq.m" in normalized
	):
		return "property"

	return "other"


def _extract_doc_no(text):
	normalized = _normalize_for_matching(text)

	patterns = [
		r"book\s*no\.?\s*[:\-]?\s*([a-z0-9\-/]+)",
		r"registered\s*no\.?\s*[:\-]?\s*([a-z0-9\-/]+)",
		r"registration\s*no\.?\s*[:\-]?\s*([a-z0-9\-/]+)",
		r"doc(?:ument)?\s*no\.?\s*[:\-]?\s*([a-z0-9\-/]+)",
		r"deed\s*no\.?\s*[:\-]?\s*([a-z0-9\-/]+)",
	]

	for pattern in patterns:
		m = re.search(pattern, normalized, flags=re.IGNORECASE)
		if m:
			token = re.sub(r"[^a-zA-Z0-9\-/]", "", m.group(1))
			return token or None

	return None


def _extract_area_candidates(text):
	normalized = _normalize_for_matching(text)
	candidates = []

	area_patterns = [
		r"(\d{1,6}(?:,\d{3})*(?:\.\d+)?)\s*(sqm|sq\.m|sq m|square\s*meters?)",
		r"(\d{1,6}(?:,\d{3})*(?:\.\d+)?)\s*(acre|acres)",
		r"(\d{1,6}(?:,\d{3})*(?:\.\d+)?)\s*(hectare|hectares|ha)\b",
	]

	for pattern in area_patterns:
		for m in re.finditer(pattern, normalized, flags=re.IGNORECASE):
			value = m.group(1).replace(",", "")
			unit = m.group(2).replace(" ", "")
			unit = "sqm" if unit in {"sq.m", "sqm", "sqmeters", "squaremeters"} else unit
			candidates.append(f"{value} {unit}")

	return candidates


def _extract_survey_number(text):
	normalized = _normalize_for_matching(text)
	patterns = [
		r"survey\s*(?:no|number)\.?\s*[:\-]?\s*([a-z0-9\-/]+)",
		r"block\s*(?:no|number)\.?\s*[:\-]?\s*([a-z0-9\-/]+)",
		r"સરવે\s*નં\.?\s*[:\-]?\s*([a-z0-9\-/]+)",
		r"બ્લોક\s*નં\.?\s*[:\-]?\s*([a-z0-9\-/]+)",
	]

	for pattern in patterns:
		m = re.search(pattern, normalized, flags=re.IGNORECASE)
		if m:
			token = re.sub(r"[^a-zA-Z0-9\-/]", "", m.group(1))
			return token or None

	return None


def _extract_lease_start(execution_date, term_text):
	normalized = _normalize_for_matching(term_text)

	if (
		"commencing from the effective date" in normalized
		or "commencing from effective date" in normalized
	):
		return execution_date

	m = re.search(
		r"commencing\s*from\s*(\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{2,4})",
		normalized,
		flags=re.IGNORECASE,
	)
	if m:
		return _normalize_date(m.group(1))

	m = re.search(
		r"effective\s*date\s*[:\-]?\s*(\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{2,4})",
		normalized,
		flags=re.IGNORECASE,
	)
	if m:
		return _normalize_date(m.group(1))

	return execution_date


def extract_lease_record_from_pages(pages, all_pages=None):
	classified = []
	for p in pages:
		text = p.get("text") or ""
		classified.append(
			{
				"page": p.get("page"),
				"text": text,
				"page_type": classify_page(text),
			}
		)

	page_groups = {
		"registration": [],
		"first_page": [],
		"property": [],
		"term": [],
		"annexure": [],
		"other": [],
	}
	for item in classified:
		page_groups[item["page_type"]].append(item)

	doc_no = None
	for page in page_groups["registration"] + page_groups["first_page"]:
		doc_no = _extract_doc_no(page["text"])
		if doc_no:
			break

	annexure_areas = []
	for page in page_groups["annexure"]:
		annexure_areas.extend(_extract_area_candidates(page["text"]))

	property_areas = []
	for page in page_groups["property"]:
		property_areas.extend(_extract_area_candidates(page["text"]))

	any_areas = []
	for page in classified:
		any_areas.extend(_extract_area_candidates(page["text"]))

	lease_area = (annexure_areas or property_areas or any_areas or [None])[0]

	execution_date = None
	# The lease execution date appears as "Date: DD-MM-YYYY" in the footer
	# of every page.  Search ALL raw pages (not just filtered) because the
	# filtered subset may have garbled OCR on the footer.
	search_pages = (all_pages or []) + [p for p in classified]
	for page in search_pages:
		text = page.get("text") or ""
		m = re.search(
			r"date\s*[:\-]\s*(\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{2,4})",
			text,
			flags=re.IGNORECASE,
		)
		if m:
			execution_date = _normalize_date(m.group(1))
			if execution_date:
				break

	term_blob = "\n".join(page["text"] for page in page_groups["term"])
	lease_start = _extract_lease_start(execution_date, term_blob)

	survey_number = None
	for page in page_groups["annexure"] + page_groups["property"] + page_groups["first_page"]:
		survey_number = _extract_survey_number(page["text"])
		if survey_number:
			break

	return {
		"survey_number": survey_number,
		"lease_deed_doc_no": doc_no,
		"lease_area": lease_area,
		"lease_start": lease_start,
		# Legacy compatibility aliases for existing normalization layer.
		"land_area": lease_area,
		"lease_start_date": lease_start,
		"_lease_page_types": [{"page": p["page"], "type": p["page_type"]} for p in classified],
	}
