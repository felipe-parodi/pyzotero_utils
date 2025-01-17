#!/usr/bin/env python
"""Summarize PDFs from Zotero collections using OpenAI.

Use pyzot conda env.

This script connects to Zotero API to process PDFs from specified collections,
generating structured summaries via OpenAI and saving to CSV files.

Usage:
    Single collection:
        python llm_summarize_pdfs.py
    
    Recursive (process all subcollections):
        python llm_summarize_pdfs.py --recursive

Args:
    --recursive (-r): Optional flag to process all subcollections

Returns:
    Creates CSV files named as:
        {collection_name}_summaries.csv

Requirements:
    - Zotero API credentials in config.py
    - OpenAI API key in config.py
    - PyPDF2
    - pyzotero
    - requests
    - openai
"""

import sys
import os
from pathlib import Path

# Add the parent directory to the Python path
parent_dir = str(Path(__file__).resolve().parent.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import argparse
import csv
import tempfile
import openai
from PyPDF2 import PdfReader
from pyzotero import zotero
import requests

import requests  # Add missing import
from config import (  # Change to relative import
    ZOTERO_API_KEY,
    CONFIG,
    LIBRARY_ID,
    LIBRARY_TYPE,
    OPENAI_API_KEY,
    PARENT_COLLECTION,
    PARENT_TARGET_COLLECTION,
    TARGET_SUBCOLLECTION,
)

def download_pdf_from_zotero(zot, pdf_item_key):
    """
    Download PDF file content from Zotero via the item key.
    Returns the content in bytes if successful, else None.
    """
    download_url = f"https://api.zotero.org/users/{LIBRARY_ID}/items/{pdf_item_key}/file"
    headers = {"Authorization": f"Bearer {ZOTERO_API_KEY}", "Zotero-API-Version": "3"}

    # First request to get the signed URL (Zotero often returns a 302 Redirect).
    response = requests.get(download_url, headers=headers, allow_redirects=False)
    if response.status_code == 302:
        # Get the actual signed URL from the 'Location' header
        signed_url = response.headers.get("Location")
        if not signed_url:
            return None
        # Fetch the PDF from the signed URL
        file_response = requests.get(signed_url)
        if file_response.status_code == 200:
            return file_response.content
    elif response.status_code == 200:
        # Direct file content (rare)
        return response.content

    print(f"Download failed with status {response.status_code}")
    return None


def extract_text_from_pdf(pdf_bytes):
    """
    Given PDF content in bytes, extract textual content using PyPDF2.
    """
    text_content = []
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp.flush()
        tmp_path = tmp.name

    reader = PdfReader(tmp_path)
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text_content.append(page_text)

    # Clean up temporary file
    os.remove(tmp_path)
    return "\n".join(text_content)


def summarize_text_with_openai(text):
    """
    Sends text to the OpenAI API for summarization.
    Returns a summary string that includes the requested structure:
        - Key findings
        - Core argument/thesis
        - Technical advances
        - Cognitive implications
        - How it provides evidence for the subsection
        - Potential controversies and alternative views
        - Connection to previous & next sections
    """
    client = openai.OpenAI(api_key=OPENAI_API_KEY)

    prompt = (
        "You are a helpful AI assistant. Read the following text and summarize it with "
        "the following structure:\n\n"
        "1) Key findings\n"
        "2) Core argument/thesis\n"
        "3) Technical advances\n"
        "4) Cognitive implications\n"
        "5) How it provides evidence for the subsection\n"
        "6) Potential controversies & alternative views\n"
        "7) Connection to previous & next sections\n\n"
        "Text:\n"
        f"{text}\n\n"
        "Now craft your structured summary."
    )

    try:
        response = client.chat.completions.create(
            # model="o1-2024-12-17",  # your preferred model
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are a scholarly summarizer that produces comprehensive structured summaries.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=1024,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"OpenAI API error: {str(e)}")
        return ""


def find_collection_key(zot, collection_path):
    """Find the collection key for a given collection path (e.g., 'TICS>s3:sci-insights>s3.3:social')"""
    path_parts = collection_path.split('>')
    current_key = None
    
    for i, name in enumerate(path_parts):
        name = name.strip()
        if i == 0:
            # Find top-level collection
            collections = zot.collections()
        else:
            # Find subcollection
            collections = zot.collections_sub(current_key)
            
        found = False
        for collection in collections:
            if collection['data']['name'].lower() == name.lower():
                current_key = collection['key']
                found = True
                break
                
        if not found:
            raise ValueError(f"Collection '{name}' not found in path {collection_path}")
            
    return current_key


def main():
    # Initialize the Zotero client
    zot = zotero.Zotero(LIBRARY_ID, LIBRARY_TYPE, ZOTERO_API_KEY)
    
    # Create data directory if it doesn't exist
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    
    # Construct full collection path
    collection_path = f"{PARENT_COLLECTION}>{PARENT_TARGET_COLLECTION}>{TARGET_SUBCOLLECTION}"
    
    # Find the actual collection key
    try:
        subcollection_key = find_collection_key(zot, collection_path)
        subcollection_info = zot.collection(subcollection_key)
        subcollection_name = subcollection_info['data']['name']
    except Exception as e:
        print(f"Error finding collection: {str(e)}")
        return

    # Prepare a CSV file to write all the results in data directory
    csv_filename = data_dir / f"zotero_summaries_{subcollection_name}.csv".replace(" ", "_")
    print(f"Will save summaries to CSV: {csv_filename}")

    # Retrieve *parent* items in that subcollection 
    items = zot.collection_items(subcollection_key)
    if not items:
        print("No parent items found in the specified subcollection.")
        return

    with open(csv_filename, mode="w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        # Write CSV header
        writer.writerow(["Citation", "Subcollection", "LLM Summary"])

        # Loop over each parent item in the subcollection
        for item in items:
            # If item is itself an attachment or note, skip
            if item["data"].get("itemType") in ("attachment", "note"):
                continue

            title_for_display = item["data"].get("title", "Untitled")
            item_key = item["key"]
            print(f"Processing: {title_for_display}...")

            # Get children to find a PDF
            children = zot.children(item_key)
            pdf_bytes = None

            for child in children:
                if child["data"].get("contentType") == "application/pdf":
                    pdf_bytes = download_pdf_from_zotero(zot, child["key"])
                    # Just one PDF per item for demonstration
                    break

            if not pdf_bytes:
                print(f"No PDF found for item: {title_for_display}")
                continue

            # Extract text from the PDF
            extracted_text = extract_text_from_pdf(pdf_bytes)
            if not extracted_text: 
                print(f"Could not extract text for item: {title_for_display}")
                continue

            # Summarize via OpenAI
            summary_text = summarize_text_with_openai(extracted_text)

            # Write row to CSV
            writer.writerow([title_for_display, subcollection_name, summary_text])

    print(f"\nDone! CSV with summaries saved to: {csv_filename}")


if __name__ == "__main__":
    main()
