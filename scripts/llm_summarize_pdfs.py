#!/usr/bin/env python
"""Summarize PDFs from Zotero collections using OpenAI.

Use pyzotero_utls conda env.

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
import google.generativeai as genai

import requests  # Add missing import
from config import (  # Change to relative import
    ZOTERO_API_KEY,
    CONFIG,
    LIBRARY_ID,
    LIBRARY_TYPE,
    OPENAI_API_KEY,
    GEMINI_API_KEY,
    PARENT_COLLECTION,
    TARGET_COLLECTION,
    summarization_prompt,
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


def chunk_text(text, max_chars=12000):
    """Split text into chunks, trying to break at paragraph boundaries."""
    if len(text) <= max_chars:
        return [text]
    
    chunks = []
    paragraphs = text.split('\n\n')
    current_chunk = []
    current_length = 0
    
    for para in paragraphs:
        if current_length + len(para) > max_chars and current_chunk:
            chunks.append('\n\n'.join(current_chunk))
            current_chunk = [para]
            current_length = len(para)
        else:
            current_chunk.append(para)
            current_length += len(para)
    
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))
    
    return chunks


def extract_subsection_key(collection_path):
    """Extract parent subsection key from collection path.
    e.g., 'TICS>s2.3.3:emerging' -> 's2.3'
         'TICS>s2>s2.3.2:neuropred' -> 's2.3'
    """
    parts = collection_path.split('>')
    for part in parts:
        if ':' in part:  # Handle parts with descriptions
            section = part.split(':')[0].lower()
        else:
            section = part.lower()
            
        if section.startswith('s'):
            section = section[1:]  # Remove 's' prefix if present
            
        # Look for patterns like '2.3.3', '2.3', etc.
        if '.' in section:
            # Take first two numbers (e.g., '2.3' from '2.3.3')
            numbers = section.split('.')[:2]
            return f"s{'.'.join(numbers)}"
            
    return None


def summarize_text_with_openai(text, collection_path):
    """Summarize scientific text using OpenAI API with structured output."""
    from config import subsection_outline_dictionary
    
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    
    # Get subsection context if available
    subsection_key = extract_subsection_key(collection_path)
    prompt = summarization_prompt
    
    if subsection_key and subsection_key in subsection_outline_dictionary:
        # Format section context with clear visual separation
        context = (
            "\n" + "="*40 + "\n" +
            "SECTION CONTEXT\n" +
            "-"*20 + "\n" +
            subsection_outline_dictionary[subsection_key].replace("→", "\n→").replace(";", ";\n") +
            "\n" + "="*40 + "\n\n"
        )
        
        # Insert after first line
        prompt_lines = prompt.split('\n', 1)
        prompt = prompt_lines[0] + context + (prompt_lines[1] if len(prompt_lines) > 1 else '')
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system", 
                    "content": "You are a scientific summarizer specializing in advances that enable the study of primate behavior in natural contexts. Focus on technical innovations, neural mechanisms, and implications for understanding natural behavior."
                },
                {"role": "user", "content": prompt + f"\n\nPaper text:\n{text}"},
            ],
            temperature=0.2,
            max_tokens=1024,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"OpenAI API error: {str(e)}")
        return ""


def summarize_text_with_gemini(text):
    """Summarize scientific text using Gemini API with structured output."""
    try:
        # Configure Gemini
        genai.configure(api_key=GEMINI_API_KEY)
        
        # Create model with specific config
        model = genai.GenerativeModel(
            model_name="gemini-1.5-pro",
            generation_config={
                "temperature": 0.2,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 1024,
            }
        )
        
        prompt = (
            "Create a structured paper analysis:\n\n"
            "1) Findings: Main results\n"
            "2) Argument: Central contribution\n"
            "3) Advances: Methods enabling naturalistic studies\n"
            "4) Limitations: Key caveats\n"
            "5) Implications & Context: Insights & connections to broader field\n\n"
            "Write each section as a concise paragraph. Focus on advances in studying natural behavior.\n\n"
            f"Paper text:\n{text}"
        )
        
        response = model.generate_content(prompt)
        return response.text.strip()
        
    except Exception as e:
        print(f"Gemini API error: {str(e)}")
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


def get_citation(zot, item):
    """Get short citation (Author et al., Year) for an item."""
    try:
        # Get creator info
        creators = item['data'].get('creators', [])
        first_author = creators[0]['lastName'] if creators else 'Unknown'
        
        # Get year
        date = item['data'].get('date', '')
        year = date.split('-')[0] if date else 'n.d.'
        
        # Format citation
        if len(creators) > 1:
            return f"{first_author} et al., {year}"
        else:
            return f"{first_author}, {year}"
    except Exception as e:
        print(f"Error creating citation: {str(e)}")
        return "Citation unavailable"


def find_target_collections(zot, parent_collection, target_name, path=""):
    """Recursively find all collections under the target collection.
    Returns list of tuples: (collection_key, full_path)"""
    results = []
    
    try:
        # Get collections at current level
        if not path:  # Top level
            collections = [c for c in zot.collections() 
                         if c['data']['name'] == parent_collection]
        else:
            parent_key = find_collection_key(zot, path.split('>')[-1])
            collections = zot.collections_sub(parent_key)
            
        for collection in collections:
            current_name = collection['data']['name']
            current_path = f"{path}>{current_name}" if path else current_name
            
            # If we find the target collection or we're already inside it
            if (target_name.lower() in current_name.lower() or 
                (path and target_name.lower() in path.lower())):
                # Add this collection
                if not any(collection['key'] == k for k, _ in results):
                    results.append((collection['key'], current_path))
                # Recursively get ALL nested subcollections
                def add_all_subcollections(coll_key, coll_path):
                    subs = zot.collections_sub(coll_key)
                    for sub in subs:
                        sub_path = f"{coll_path}>{sub['data']['name']}"
                        if not any(sub['key'] == k for k, _ in results):
                            results.append((sub['key'], sub_path))
                            # Recurse into this subcollection
                            add_all_subcollections(sub['key'], sub_path)
                
                add_all_subcollections(collection['key'], current_path)
            
            # Continue recursing only if we haven't found target yet
            if target_name.lower() not in current_path.lower():
                sub_results = find_target_collections(
                    zot, 
                    parent_collection,
                    target_name, 
                    current_path
                )
                for key, sub_path in sub_results:
                    if not any(key == k for k, _ in results):
                        results.append((key, sub_path))
            
        return results
        
    except Exception as e:
        print(f"Error searching collections: {str(e)}")
        return results


def main():
    # Initialize Zotero client
    zot = zotero.Zotero(LIBRARY_ID, LIBRARY_TYPE, ZOTERO_API_KEY)
    
    # Create data directory
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    
    # Find all matching collections
    print(f"Searching for collections containing '{TARGET_COLLECTION}'...")
    target_collections = find_target_collections(zot, PARENT_COLLECTION, TARGET_COLLECTION)
    if not target_collections:
        print(f"No collections found containing '{TARGET_COLLECTION}'")
        return
    
    print(f"\nFound {len(target_collections)} matching collections")
    
    # Prepare CSV file
    csv_filename = data_dir / f"zotero_summaries_{TARGET_COLLECTION}.csv".replace(" ", "_")
    print(f"Will save summaries to: {csv_filename}")
    
    with open(csv_filename, mode="w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Citation", "Short_Citation", "Collection_Path", "LLM Summary"])
        
        # Process each matching collection
        for coll_idx, (collection_key, collection_path) in enumerate(target_collections, 1):
            print(f"\n[{coll_idx}/{len(target_collections)}] Processing: {collection_path}")
            
            # Get items in this collection
            items = zot.collection_items(collection_key)
            if not items:
                print("  No items found in collection")
                continue
            
            # Filter out attachments and notes
            papers = [item for item in items 
                     if item["data"].get("itemType") not in ("attachment", "note")]
            
            print(f"  Found {len(papers)} papers")
            
            # Process items
            for paper_idx, item in enumerate(papers, 1):
                title = item["data"].get("title", "Untitled")
                short_citation = get_citation(zot, item)
                print(f"  [{paper_idx}/{len(papers)}] {short_citation}...", end="", flush=True)

                # Get PDF and process
                children = zot.children(item["key"])
                pdf_bytes = None
                for child in children:
                    if child["data"].get("contentType") == "application/pdf":
                        pdf_bytes = download_pdf_from_zotero(zot, child["key"])
                        break

                if not pdf_bytes:
                    print(" No PDF found")
                    continue

                extracted_text = extract_text_from_pdf(pdf_bytes)
                if not extracted_text:
                    print(" Could not extract text")
                    continue

                summary_text = summarize_text_with_openai(extracted_text, collection_path)
                writer.writerow([title, short_citation, collection_path, summary_text])
                print(" ✓")

    print(f"\nDone! Summaries saved to: {csv_filename}")


if __name__ == "__main__":
    main()
