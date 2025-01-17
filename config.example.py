"""
Configuration settings for Zotero and API access.
Copy this file to config.py and fill in your credentials.
"""

# Zotero API credentials
ZOTERO_API_KEY = "your_zotero_api_key"
LIBRARY_ID = "your_library_id"  # e.g., "9999999"
LIBRARY_TYPE = "user"  # or "group"

# Collection structure
PARENT_COLLECTION = "TICS"  # Top-level collection
PARENT_TARGET_COLLECTION = "s3:sci-insights"  # Mid-level collection
TARGET_SUBCOLLECTION = "s3.3:social"  # Target subcollection

# LLM API keys
OPENAI_API_KEY = "your_openai_api_key"
GEMINI_API_KEY = "your_gemini_api_key"

# Additional configuration
CONFIG = {
    "max_tokens": 1024,
    "temperature": 0.2,
} 

summarization_prompt = """
"""