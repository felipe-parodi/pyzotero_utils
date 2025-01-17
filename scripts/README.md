# Zotero Scripts

Collection of Python scripts for Zotero library management.

## Scripts
- `combine_pdfs.py`: Combines PDFs from Zotero collections with automatic size management (splits at 95MB)
  - Usage: `python combine_pdfs.py [--recursive]`
  - Requires config.py in parent directory with Zotero credentials
- `llm_summarize_pdfs.py`: Summarizes PDFs using OpenAI API with structured output
  - Usage: `python llm_summarize_pdfs.py`
  - Requires config.py in parent directory with Zotero credentials

