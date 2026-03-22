def filter_pages(pages, doc_type):
    relevant = []

    for p in pages:
        text = p["text"]

        if doc_type == "echallan":
            if "challan" in text.lower():
                relevant.append(p)

        elif doc_type == "lease":
            if (
                "survey" in text.lower()
                or "₹" in text
                or "amount" in text.lower()
                or "lessee" in text.lower()
            ):
                relevant.append(p)

        elif doc_type == "na_order":
            if "હુકમ" in text or "સર્વે" in text:
                relevant.append(p)

        else:
            # fallback: keep first few pages
            if p["page"] <= 3:
                relevant.append(p)

    return relevant