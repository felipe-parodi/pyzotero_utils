"""Configuration settings for Zotero PDF utilities."""

# Zotero credentials
LIBRARY_ID = "6759929"  # Your user ID
LIBRARY_TYPE = "user"   # Type is "user" for personal library
API_KEY = "pFRsxm9kwiNaU770FNlqDCDV"

# Configuration options
CONFIG = {
    'INSTITUTIONAL_PROXY': 'proxy.library.upenn.edu',
    'USE_UNPAYWALL': True,
    'EMAIL_FOR_UNPAYWALL': 'fparodi@pennmedicine.upenn.edu',
    'RETRY_ATTEMPTS': 3,
    'TIMEOUT': 30,
} 