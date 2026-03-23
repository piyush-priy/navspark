import json
from groq import Groq

from schemas.echallan import EChallan
from schemas.lease import LeaseRecord
from schemas.na_order import NAOrder

from llm.prompt import build_prompt

client = Groq()


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


def extract_structured_data(text, doc_type):
    prompt = build_prompt(text, doc_type)

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
        data = json.loads(raw_output)
        validated = schema(**data)
        return validated.dict(), prompt, raw_output

    except Exception:
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
            data = json.loads(fixed_output)
            validated = schema(**data)
            return validated.dict(), prompt, fixed_output
        except:
            return None, prompt, raw_output