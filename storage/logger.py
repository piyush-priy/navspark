import json
import os
from datetime import datetime

LOG_DIR = "logs"
LOG_FILE = "llm_logs.jsonl"


def log_llm(prompt, response, doc_type=None, page=None):
    # Ensure logs directory exists
    os.makedirs(LOG_DIR, exist_ok=True)

    log_entry = {
        "timestamp": str(datetime.now()),
        "doc_type": doc_type,
        "page": page,
        "prompt": prompt,
        "response": response
    }

    log_path = os.path.join(LOG_DIR, LOG_FILE)

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")