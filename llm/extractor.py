import json
import os
from groq import Groq
from groq import GroqError

from schemas.lease import LeaseRecord
from schemas.na_order import NAOrder

from llm.prompt import build_prompt

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is missing. Set it in your environment or .env file before running extraction."
        )

    try:
        _client = Groq(api_key=api_key)
        return _client
    except GroqError as exc:
        raise RuntimeError(f"Failed to initialize Groq client: {exc}") from exc


def _approx_tokens(text):
    # Practical approximation for mixed OCR text.
    return max(1, len(text) // 4)


def _doc_char_budget(doc_type):
    # Keep per-document budgets tight by default and configurable via env.
    default_map = {
        "na_order": 1000,
        "lease": 1200,
    }
    env_name = f"MAX_INPUT_CHARS_{str(doc_type).upper()}"
    configured = os.getenv(env_name)
    if configured and configured.isdigit():
        return max(400, int(configured))
    return default_map.get(doc_type, 1200)


def _keyword_set(doc_type):
    if doc_type == "lease":
        return {
            "village",
            "moje",
            "mouje",
            "ગામ",
            "doc",
            "document",
            "દસ્તાવેજ",
            "registration",
            "lease",
            "survey",
            "block",
            "area",
            "સરવે",
            "બ્લોક",
            "ક્ષેત્રફળ",
            "date",
            "commencing",
            "effective",
        }
    if doc_type == "na_order":
        return {
            "village",
            "moje",
            "mouje",
            "ગામ",
            "case",
            "order no",
            "વશી",
            "જમીન",
            "હુકમ",
            "પરિશિષ્ટ",
            "સરવે",
            "બ્લોક",
            "ક્ષેત્રફળ",
            "ચો.મી",
            "તા.",
            "survey",
            "block",
            "area",
            "order",
            "date",
        }
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
    indexed_scored = [
        (idx, line, _line_score(line, keywords)) for idx, line in enumerate(lines)
    ]
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


def _has_min_signal(text, doc_type):
    compact = (text or "").strip()
    if len(compact) < 40:
        return False

    keywords = _keyword_set(doc_type)
    lower = compact.lower()
    keyword_hits = sum(1 for kw in keywords if kw in lower)
    has_digits = any(ch.isdigit() for ch in compact)
    return keyword_hits >= 1 or has_digits


def get_schema(doc_type):
    if doc_type == "lease":
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
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except Exception:
            return None
    return None


def _postprocess_lease_data(data):
    if not isinstance(data, dict):
        return data

    # Backward-compatible key mapping if model returns older field names.
    if not data.get("lease_area") and data.get("land_area"):
        data["lease_area"] = data.get("land_area")
    if not data.get("lease_start") and data.get("lease_start_date"):
        data["lease_start"] = data.get("lease_start_date")

    return data


def _postprocess_na_order_data(data):
    if not isinstance(data, dict):
        return data

    # Map na_area (the field name used in the prompt) to area_in_na_order.
    if not data.get("area_in_na_order") and data.get("na_area"):
        data["area_in_na_order"] = data.get("na_area")
    # Backward-compatible key mapping if model returns older field names.
    if not data.get("area_in_na_order") and data.get("land_area"):
        data["area_in_na_order"] = data.get("land_area")
    if not data.get("dated") and data.get("order_date"):
        data["dated"] = data.get("order_date")

    return data


def extract_structured_data(text, doc_type):
    client = _get_client()

    requested_budget = int(os.getenv("MAX_REQUEST_TOKENS", "1800"))
    max_request_tokens = min(requested_budget, 4000)
    reserve_output_tokens = int(os.getenv("RESERVE_OUTPUT_TOKENS", "350"))
    max_completion_tokens = int(os.getenv("MAX_COMPLETION_TOKENS", "350"))

    if not _has_min_signal(text, doc_type):
        return None, "", ""

    # Estimate static prompt overhead with empty document and budget input accordingly.
    static_prompt = build_prompt("", doc_type)
    static_tokens = _approx_tokens(static_prompt)
    max_input_tokens = max(
        300, max_request_tokens - reserve_output_tokens - static_tokens
    )
    max_input_chars_hard = int(
        os.getenv("MAX_INPUT_CHARS", str(_doc_char_budget(doc_type)))
    )
    max_input_chars = min(max_input_tokens * 4, max_input_chars_hard)

    compacted_text = _compact_text_to_budget(text, doc_type, max_input_chars)
    prompt = build_prompt(compacted_text, doc_type)

    print(
        f"[INFO] Token budget -> approx_prompt_tokens={_approx_tokens(prompt)} "
        f"(limit={max_request_tokens})"
    )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=max_completion_tokens,
        )
        raw_output = response.choices[0].message.content
        raw_output = clean_json(raw_output)
    except Exception as e:
        print(f"[WARN] LLM API Call failed (Rate Limit or Error): {e}")
        return None, prompt, ""

    schema = get_schema(doc_type)

    if not schema:
        return None, prompt, raw_output

    try:
        data = _try_parse_json(raw_output)
        if data is None:
            raise ValueError("Unable to parse JSON from model output")

        if doc_type == "lease":
            data = _postprocess_lease_data(data)
        elif doc_type == "na_order":
            data = _postprocess_na_order_data(data)

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
            temperature=0,
            max_tokens=max_completion_tokens,
        )

        fixed_output = fix_response.choices[0].message.content
        fixed_output = clean_json(fixed_output)

        try:
            data = _try_parse_json(fixed_output)
            if data is None:
                raise ValueError("Unable to parse fixed JSON")

            if doc_type == "lease":
                data = _postprocess_lease_data(data)
            elif doc_type == "na_order":
                data = _postprocess_na_order_data(data)

            for k, v in data.items():
                if v is not None:
                    data[k] = str(v)
            validated = schema(**data)
            return validated.dict(), prompt, fixed_output
        except:
            return None, prompt, raw_output
