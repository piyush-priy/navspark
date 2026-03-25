# Navspark Document Extraction Pipeline

The **Navspark Hybrid Document Extraction Pipeline** is designed to process, extract, and unify highly complex, legally dense, mixed-language (English and Gujarati) documents such as **Non-Agricultural (NA) Orders** and **Lease Deeds**. 

The system utilizes a hybrid approach:
1. **Deterministic Parser:** A fast, highly reliable text-layout and regex engine for extracting primary, high-accuracy data components (Survey Numbers, Dates, Areas).
2. **Heuristic OCR:** Integrates Tesseract OCR enhanced using OpenCV to preprocess and clarify highly obfuscated text.
3. **LLM Engine:** Serves as a secondary layer resolving complex tabular context and mixed-vernacular extraction when deterministic checks are exhausted, using the Groq API (`llama-3.3-70b-versatile`).

## 📁 System Architecture & Naming Scheme

The project follows a strictly modular layout designed for separating data sourcing, routing, heuristic parsing, and LLM resolution:

- **`main.py`**            : The primary entry point. Orchestrates the pipeline, delegates processing to modules, handles merging, and produces the final `.xlsx` and `.json` outputs.
- **`parser/`**            : Houses deterministic processing logic.
  - `pdf_parser.py`      : The backbone for PDF-to-Text conversion. Employs `pdfplumber` for text and `pdf2image` + `opencv-python` + `pytesseract` for image-to-text.
  - `page_filter.py`     : A noise-canceling sieve. Strips page numbers, footers, boilerplate markers, identifying only signal-heavy lines to meet dense LLM context limits.
  - `document_detector.py` : Automates type-classification (`na_order` vs. `lease`) via filename heuristics or 5-page previews.
  - `lease_pipeline.py`  : Domain-specific deterministic rules for Lease Deeds.
  - `na_pipeline.py`     : Domain-specific deterministic rules for Non-Agricultural Orders.
- **`llm/`**               : AI-assistance capabilities.
  - `extractor.py`       : Connects to Groq's Large Language Models mapping the `schemas` output. Integrates a smart text-compaction logic (`_compact_text_to_budget`) based upon available input tokens.
  - `prompt.py`          : Stores few-shot tailored parsing prompts heavily tuned for local state and legal logic.
- **`schemas/`**           : Output definitions matching Pydantic standards (e.g. `lease.py`, `na_order.py`).
- **`storage/`**           : Logging logic capturing debug information or LLM prompts.
- **`data/`**              : Input directory where standard `.pdf` target files must be placed.
- **`output/`**            : Generated data (Unified `.xlsx` spreadsheets and JSON payload history).

## 🚀 Execution Process

### Prerequisites
In order to run OCR parsing, you must have external system dependencies installed:
- **Tesseract-OCR:** Ensure it is installed on your OS. For Windows, download the binary. Also ensure that you install Gujarati (`guj`), Hindi (`hin`), and English language data. 
- **Poppler:** Required by `pdf2image` to convert PDF pipelines into pixel matrices. On Windows, ensure you update your PATH with Poppler binaries.

### Setup
1. **Prepare Virtual Environment:**
   Run the following commands in the root of the project to bootstrap your virtual shell:
   ```bash
   python -m venv .venv
   # Windows Activation
   .venv\Scripts\activate
   # macOS/Linux Activation
   source .venv/bin/activate
   ```

2. **Install Package Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Provide API Configuration:**
   Copy the existing `.env` or create an empty `.env` in the project root, supplying your private Groq credentials for the fallback processor:
   ```env
   GROQ_API_KEY=your_actual_groq_api_key_here
   ```

### Running the Pipeline
Simply drop your target `.pdf` documents in the `data/` subdirectory. Then execute the main runner:

```bash
python main.py
```

The system will synchronously chunk through each document. Detailed logging for the deterministic successes/failures and LLM queries is recorded in Standard Output. 

Ultimately, all records are unified under `Survey No.` keys and exported beautifully to `output/results.xlsx` alongside the raw extraction `output/results.json`.

## 📜 Intelligent File Naming Constraints
During operation, the parser aggressively searches filename markers to supplement poor OCR. Ensure input variables reflect proper identification parameters when possible:
- If processing **Lease Deeds**: Attempt incorporating doc numbers (`Doc _ 1234`) or Survey paths directly in the file string (e.g., `Survey 38-B_Lease.pdf`).
- If processing **NA Orders**: The filename's internal survey numbers frequently overlay poor structural reads during extraction routing. Ensure naming closely represents its physical content identifier.
