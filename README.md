# Pyzotero Utilities

Utility scripts and tools for working with Zotero libraries via the pyzotero API.

## Setup
1. Create `config.py` with your Zotero credentials (never commit this file):
    ```python
    LIBRARY_ID = "your_id"  # Find at https://www.zotero.org/settings/keys (your userID number)
    LIBRARY_TYPE = "user"
    API_KEY = "your_api_key"  # Generate at https://www.zotero.org/settings/keys/new
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
  - `combine_pdfs.py`: Combines PDFs from collections with size management (splits at 95MB)
- `config.py`: Credentials and settings (create from template above)

## Security
- `config.py` is gitignored to protect credentials
- Never commit files containing API keys or personal information
- If you accidentally commit sensitive information:
  1. Immediately revoke your API key at https://www.zotero.org/settings/keys
  2. Generate a new key at https://www.zotero.org/settings/keys/new
  3. Update your local config.py
  4. Contact repository admin to purge sensitive data from history

## Usage
See individual script READMEs in the `scripts/` directory for specific usage instructions.