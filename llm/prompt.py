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
- land_area
- owner_name
- lease_start_date
- lease_duration
- company_name
"""
        doc_guidance = """
Lease-specific hints:
- `survey_number` may appear as: survey no, survey number, block number, સરવે નંબર, બ્લોક નંબર.
- `land_area` may appear as: area, extent, sq.m, hectare, acre, ચો.મી, ક્ષેત્રફળ.
- `owner_name` can be lessor/land owner/grantor/ખાતેદાર name.
- `company_name` can be lessee/company/applicant/અરજદાર name.
- `lease_start_date` may be execution/registration/effective date.
- `lease_duration` may appear like "28 years 11 months 0 days" or "28 વર્ષ 11 માસ 0 દિવસ".
"""

    elif doc_type == "na_order":
        fields = """
- survey_number
- land_area
- owner_name
- order_date
- company_name
"""
        doc_guidance = """
NA-order-specific hints:
- `survey_number` may appear as સરવે/બ્લોક નંબર or survey/block number.
- `land_area` may appear as ક્ષેત્રફળ, ચો.મી, sq.m, area.
- `order_date` is usually near હુકમ નં./પ્રાંત કચેરી/તા.
- `company_name` can be applicant/authorized-person company (અરજદાર, અધિકૃત વ્યક્તિ, Limited).
- `owner_name` means the land holder/lessor/ખાતેદાર only when explicit; do not invent.
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