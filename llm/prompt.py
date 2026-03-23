def build_prompt(text, doc_type):

    if doc_type == "echallan":
        fields = """
- challan_number
- vehicle_number
- violation_date
- amount
- offence_description
- payment_status
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

    elif doc_type == "na_order":
        fields = """
- survey_number
- land_area
- owner_name
- order_date
- company_name
"""

    else:
        fields = ""

    return f"""
You are an expert document parser.

The document may contain multiple languages (English, Gujarati, Hindi).

Extract the following fields:

{fields}

Return ONLY valid JSON.
If a field is missing → return null.

Document:
\"\"\"
{text}
\"\"\"
"""