def build_prompt(text, doc_type):
    doc_guidance = ""

    if doc_type == "lease":
        fields = """
- survey_number
- village
- lease_area
- lease_start_date
- lease_deed_doc_no
"""
        doc_guidance = """
Lease-specific hints:
- `survey_number` may appear as: survey no, block number, સરવે નંબર, બ્લોક નંબર.
- `village` may appear as ગામ, Village, Moje, or Mouje.
- `lease_area` may appear as: area, extent, sq.m, hectare, acre, ચો.મી, ક્ષેત્રફળ.
- `lease_start_date` may be execution/registration/effective date.
- `lease_deed_doc_no` may appear as Document No, Doc No, દસ્તાવેજ નં, or Registration Number.
"""

    elif doc_type == "na_order":
        fields = """
- survey_number
- village
- na_area
- order_date
- na_order_no
"""
        doc_guidance = """
NA-order-specific hints:
- `survey_number` may appear as સરવે/બ્લોક નંબર or survey/block number.
- `village` may appear as ગામ, Village, Moje, or Mouje.
- `na_area` is the TOTAL survey area (વિસ્તાર), NOT the leased subset (ક્ષેત્રફળ). Look for the number after વિસ્તાર. For example in "વિસ્તાર 5,997.00 ચો.મી. પૈકી ક્ષેત્રફળ 4,047.00 ચો.મી.", na_area = 5997.
- `order_date` is usually near હુકમ નં./પ્રાંત કચેરી/તા.
- `na_order_no` may appear as Order No, હુકમ નં, જમીન/વશી/..., or Case Number.
"""
    else:
        fields = ""

    return f"""Extract structured data from OCR text.

Rules:
- Text may be English/Gujarati/Hindi.
- Correct only obvious OCR confusions (O/0, I/1, S/5) when context is clear.
- Return ONLY one JSON object.
- Include exactly these fields:
{fields}
- Missing values must be null.
- Do not invent values.
- For `village`, always transliterate to English (e.g., રામપુરા મોટા → Rampura Mota).
- For area fields (`na_area`, `lease_area`), return ONLY the numeric value in sq.m without units or commas (e.g., 16534 not "16,534.00 ચો.મી.").

{doc_guidance}

OCR text:
<<<TEXT>>>
{text}
<<<END_TEXT>>>
"""
