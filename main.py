import json

from parser.pdf_parser import hybrid_extract

pdf_path = "data/255 FINAL ORDER.pdf"

pages = hybrid_extract(pdf_path)

# Save output (VERY IMPORTANT)
with open("output/parsed_pages.json", "w", encoding="utf-8") as f:
    json.dump(pages, f, indent=2, ensure_ascii=False)

# Print preview
for p in pages[:3]:
    print(f"\n--- Page {p['page']} ---\n")
    print(p["text"][:500])