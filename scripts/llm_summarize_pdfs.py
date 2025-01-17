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
    """Summarize scientific text using OpenAI API with structured output."""
    client = openai.OpenAI(api_key=OPENAI_API_KEY)

    prompt = (
        "You are a scientific paper summarizer specializing in neuroscience, particularly "
        "primate neuroethology and naturalistic behavior studies. Your goal is to extract key "
        "information about advances in methods, technology, and understanding that enable the "
        "study of natural primate behavior. Summarize the following text using these sections:\n\n"
        "1) Key findings: Main empirical results and discoveries, focusing on what was learned "
        "about natural behavior or methodological breakthroughs\n"
        "2) Core argument/thesis: Central theoretical contribution and how it advances our ability "
        "to study natural behavior\n"
        "3) Technical advances: Novel methods, tools, or approaches that enable more naturalistic "
        "studies (e.g., wireless recording, computer vision, machine learning)\n"
        "4) Cognitive implications: What this tells us about brain function and behavior in natural "
        "contexts, beyond traditional controlled experiments\n"
        "5) Evidence contribution: How this specifically advances our ability to study and understand "
        "naturalistic primate behavior\n"
        "6) Limitations and alternatives: Key caveats, technical challenges, and alternative "
        "interpretations of the findings\n"
        "7) Scientific context: How this connects to the broader field of naturalistic neuroscience "
        "and primate behavior\n\n"
        "Text to summarize:\n"
        f"{text}\n\n"
        "Guidelines:\n"
        "- Write in clear, concise language\n"
        "- Avoid any markdown formatting, special characters, or bullet points\n"
        "- Focus specifically on advances that enable more naturalistic studies\n"
        "- Be precise about methodological innovations and their impact\n"
        "- Highlight implications for studying behavior in natural contexts\n"
        "- Emphasize connections to ethology and field studies when relevant\n"
        "- Note any bridges between controlled lab studies and natural behavior\n"
        "- Identify scalable approaches that could be applied to other studies\n"
        "- Write each section as a coherent paragraph, not a list\n"
        "- Keep focus on how this enables better study of natural behavior"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a scientific summarizer specializing in advances that enable the "
                        "study of primate behavior in natural contexts. Focus on methodological "
                        "and theoretical developments that bridge laboratory neuroscience with "
                        "naturalistic behavior."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=1024,  # Increased to allow for more detailed responses
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
