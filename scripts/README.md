# Zotero Scripts

Collection of Python scripts for Zotero library management.

These require a config.py file in the parent directory with Zotero, OpenAI, and/or Gemini credentials.

## Scripts
- `combine_pdfs.py`: Combines PDFs from Zotero collections with automatic size management (splits at 95MB)
  - Usage: `python combine_pdfs.py [--recursive]`
- `llm_summarize_pdfs.py`: Summarizes PDFs using OpenAI API or Gemini API with structured output
  - Usage: `python llm_summarize_pdfs.py`

