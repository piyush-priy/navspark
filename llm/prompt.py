def build_prompt(text, doc_type):
    doc_guidance = ""

    if doc_type == "echallan":
        fields = """
- challan_number
- vehicle_number
- violation_date
- amount
- offence_description
- payment_status
"""
        doc_guidance = """
eChallan hints:
- `vehicle_number` should be normalized to a compact plate-like token in format XX00XX0000 (e.g., DL01AB1234).
- `challan_number` may contain OCR confusions between O/0, I/1, S/5, also there may be accidental blank spaces in between which should not be there. Remove any accidental spaces, line breaks, or separators present due to OCR/parsing errors.
"""

    elif doc_type == "lease":
        fields = """
- survey_number
    - lease_deed_doc_no
    - lease_area
    - lease_start
"""
        doc_guidance = """
Lease-specific hints:
- `survey_number` may appear as: survey no, survey number, block number, સરવે નંબર, બ્લોક નંબર.
    - `lease_deed_doc_no` may appear as document no, registration no, deed no, દાખલા ક્રમાંક.
    - `lease_area` may appear as: area, extent, sq.m, hectare, acre, ચો.મી, ક્ષેત્રફળ.
    - `lease_start` may be execution/registration/effective/commencement date.
"""

    elif doc_type == "na_order":
        fields = """
- survey_number
    - village
    - area_in_na_order
    - dated
    - na_order_no
"""
        doc_guidance = """
NA-order-specific hints:
- `survey_number` may appear as સરવે/બ્લોક નંબર or survey/block number.
    - `village` may appear as ગામ, mouje, village.
    - `area_in_na_order` may appear as ક્ષેત્રફળ, ચો.મી, sq.m, area.
    - `dated` is usually near હુકમ નં./પ્રાંત કચેરી/તા.
    - `na_order_no` may appear as હુકમ નં., order no, file no.
"""

    else:
        fields = ""

    return f"""
You are an expert document parser.

The document may contain multiple languages (English, Gujarati, Hindi).
You WILL see OCR errors. Fix obvious OCR confusions (O/0, I/1, S/5) only when context is clear.
Never truncate long string values.

Extract the following fields:

{fields}

Return ONLY valid JSON.
If a field is missing, return null.
Do not invent values.

{doc_guidance}

Document:
\"\"\"
{text}
\"\"\"
"""