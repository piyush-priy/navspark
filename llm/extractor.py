import json
import os
import re
from groq import Groq

from schemas.echallan import EChallan
from schemas.lease import LeaseRecord
from schemas.na_order import NAOrder

from llm.prompt import build_prompt

client = Groq()


def _approx_tokens(text):
    # Practical approximation for mixed OCR text.
    return max(1, len(text) // 4)


def _keyword_set(doc_type):
    if doc_type == "lease":
        return {
            "lease", "lessor", "lessee", "survey", "block", "area", "duration", "year",
            "month", "company", "owner", "amount", "સરવે", "બ્લોક", "લીઝ", "ક્ષેત્રફળ",
            "વર્ષ", "માસ", "અરજદાર", "કંપની"
        }
    if doc_type == "na_order":
        return {
            "હુકમ", "પરિશિષ્ટ", "સરવે", "બ્લોક", "ક્ષેત્રફળ", "ચો.મી", "અરજદાર",
            "કંપની", "તા.", "survey", "block", "area", "order", "date", "year", "month"
        }
    if doc_type == "echallan":
        return {"challan", "vehicle", "violation", "amount", "offence", "payment"}
    return set()


def _line_score(line, keywords):
    lower = line.lower()
    score = 0
    if any(ch.isdigit() for ch in line):
        score += 2
    if any(kw in lower for kw in keywords):
        score += 4
    if 6 <= len(line) <= 220:
        score += 1
    return score


def _compact_text_to_budget(text, doc_type, max_chars):
    if len(text) <= max_chars:
        return text

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return text[:max_chars]

    keywords = _keyword_set(doc_type)
    indexed_scored = [(idx, line, _line_score(line, keywords)) for idx, line in enumerate(lines)]
    indexed_scored.sort(key=lambda x: x[2], reverse=True)

    selected_idx = set()
    used_chars = 0

    # Keep top-scoring lines first.
    for idx, line, score in indexed_scored:
        if score <= 0:
            continue
        line_cost = len(line) + 1
        if used_chars + line_cost > max_chars:
            continue
        selected_idx.add(idx)
        used_chars += line_cost
        if used_chars >= max_chars:
            break

    # If still sparse, fill in original order until budget.
    if used_chars < int(max_chars * 0.7):
        for idx, line in enumerate(lines):
            if idx in selected_idx:
                continue
            line_cost = len(line) + 1
            if used_chars + line_cost > max_chars:
                break
            selected_idx.add(idx)
            used_chars += line_cost

    compacted = "\n".join(lines[idx] for idx in sorted(selected_idx))
    if not compacted:
        compacted = text[:max_chars]
    return compacted


def get_schema(doc_type):
    if doc_type == "echallan":
        return EChallan
    elif doc_type == "lease":
        return LeaseRecord
    elif doc_type == "na_order":
        return NAOrder
    return None


def clean_json(text):
    text = text.strip()

    if text.startswith("```"):
        text = text.strip("`")
        text = text.replace("json", "", 1)

    return text


def _try_parse_json(text):
    try:
        return json.loads(text)
    except Exception:
        pass

    # Try to recover JSON object from surrounding text.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except Exception:
            return None
    return None


def _normalize_date_text(value):
    if not value:
        return None

    value = str(value).strip()
    m = re.search(r"(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{2,4})", value)
    if not m:
        return None

    day = m.group(1).zfill(2)
    month = m.group(2).zfill(2)
    year = m.group(3)
    if len(year) == 2:
        year = "20" + year

    return f"{day}/{month}/{year}"


def _extract_best_date_from_text(text):
    matches = re.findall(r"\b\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{2,4}\b", text)
    for candidate in matches:
        normalized = _normalize_date_text(candidate)
        if normalized:
            return normalized
    return None


def _normalize_plate_like(value):
    if value is None:
        return None
    # Keep only alphanumeric characters and uppercase for stable identifiers.
    return re.sub(r"[^A-Za-z0-9]", "", str(value)).upper() or None


def _postprocess_echallan_data(data, source_text):
    if not isinstance(data, dict):
        return data

    # Normalize compact identifiers.
    data["vehicle_number"] = _normalize_plate_like(data.get("vehicle_number"))
    data["challan_number"] = _normalize_plate_like(data.get("challan_number"))

    # Normalize/repair violation date.
    normalized = _normalize_date_text(data.get("violation_date"))
    if normalized:
        data["violation_date"] = normalized
    elif not data.get("violation_date"):
        fallback_date = _extract_best_date_from_text(source_text)
        if fallback_date:
            data["violation_date"] = fallback_date

    return data


def extract_structured_data(text, doc_type):
    requested_budget = int(os.getenv("MAX_REQUEST_TOKENS", "3500"))
    max_request_tokens = min(requested_budget, 12000)
    reserve_output_tokens = int(os.getenv("RESERVE_OUTPUT_TOKENS", "1000"))

    # Estimate static prompt overhead with empty document and budget input accordingly.
    static_prompt = build_prompt("", doc_type)
    static_tokens = _approx_tokens(static_prompt)
    max_input_tokens = max(1000, max_request_tokens - reserve_output_tokens - static_tokens)
    max_input_chars_hard = int(os.getenv("MAX_INPUT_CHARS", "3000"))
    max_input_chars = min(max_input_tokens * 4, max_input_chars_hard)

    compacted_text = _compact_text_to_budget(text, doc_type, max_input_chars)
    prompt = build_prompt(compacted_text, doc_type)

    print(
        f"[INFO] Token budget -> approx_prompt_tokens={_approx_tokens(prompt)} "
        f"(limit={max_request_tokens})"
    )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    raw_output = response.choices[0].message.content
    raw_output = clean_json(raw_output)

    schema = get_schema(doc_type)

    if not schema:
        return None, prompt, raw_output

    try:
        data = _try_parse_json(raw_output)
        if data is None:
            raise ValueError("Unable to parse JSON from model output")

        if doc_type == "echallan":
            data = _postprocess_echallan_data(data, compacted_text)

        # Convert all non-None values to string to satisfy Pydantic strict string fields
        for k, v in data.items():
            if v is not None:
                data[k] = str(v)
        
        validated = schema(**data)
        return validated.dict(), prompt, raw_output

    except Exception:
        use_llm_json_fix = os.getenv("ENABLE_LLM_JSON_FIX", "0") == "1"
        if not use_llm_json_fix:
            return None, prompt, raw_output

        fix_prompt = f"""
The following output is not valid JSON.

Fix it and return ONLY valid JSON.
Do not add any explanation.

Output:
{raw_output}
"""

        fix_response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": fix_prompt}],
            temperature=0
        )

        fixed_output = fix_response.choices[0].message.content
        fixed_output = clean_json(fixed_output)

        try:
            data = _try_parse_json(fixed_output)
            if data is None:
                raise ValueError("Unable to parse fixed JSON")

            if doc_type == "echallan":
                data = _postprocess_echallan_data(data, compacted_text)

            for k, v in data.items():
                if v is not None:
                    data[k] = str(v)
            validated = schema(**data)
            return validated.dict(), prompt, fixed_output
        except:
            return None, prompt, raw_output