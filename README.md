# Pyzotero Utilities

Utility scripts and tools for working with Zotero libraries via the pyzotero API.

## Setup
1. Create `config.py` with your Zotero credentials:
    ```python
    LIBRARY_ID = "your_id"
    LIBRARY_TYPE = "user"
    API_KEY = "your_api_key"
    CONFIG = {
        'INSTITUTIONAL_PROXY': 'your.proxy.edu',
        'EMAIL_FOR_UNPAYWALL': 'your.email@institution.edu'
    }
    ```

2. Install requirements:
    ```bash
    pip install pyzotero PyPDF2 requests
    ```

## Directory Structure
- `scripts/`: Collection of utility scripts
  - `combine_pdfs.py`: Combines PDFs from collections with size management
- `config.py`: Credentials and settings (create from template above)

## Security
- `config.py` is gitignored to protect credentials
- Never commit files containing API keys or personal information

## Usage
See individual script READMEs in the `scripts/` directory for specific usage instructions.
