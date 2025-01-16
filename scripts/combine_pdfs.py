"""Combine PDFs from Zotero collections with size management.

    Use pyzot conda env.

This script connects to Zotero API to download and combine PDFs from specified collections,
automatically splitting into multiple files when approaching 100MB size limit.

Usage:
    Single collection:
        python combine_pdfs.py
    
    Recursive (process all subcollections):
        python combine_pdfs.py --recursive

Args:
    --recursive (-r): Optional flag to process all subcollections

Returns:
    Creates one or more combined PDF files, named as:
        {collection_name}_papers_chunk{n}.pdf
    where n is the chunk number if size exceeds 95MB.

Requirements:
    - Zotero API credentials in environment
    - PyPDF2
    - pyzotero
    - requests
"""

import argparse
import os
import tempfile

import requests
from PyPDF2 import PdfMerger, PdfReader
from pyzotero import zotero

try:
    from config import API_KEY, CONFIG, LIBRARY_ID, LIBRARY_TYPE
except ImportError:
    raise ImportError(
        "Config file not found. Please create pyzotero_utils/config.py "
        "with your Zotero credentials and settings."
    )

# Collection and subcollection names
PARENT_COLLECTION = "TICS"
PARENT_TARGET_COLLECTION = "s3:sci-insights"
TARGET_SUBCOLLECTION = "s3.3:social"
RECURSIVE = False  # Set to True when you want to process all subcollections


def find_collection_key(zot, collection_name, parent_key=None):
    """Find the collection key for a given collection name"""
    if parent_key:
        collections = zot.collections_sub(parent_key)
    else:
        collections = zot.collections()

    for collection in collections:
        if collection["data"]["name"].lower() == collection_name.lower():
            return collection["key"]
    return None


def get_collection_items_with_pdfs(zot, collection_key):
    """Get all items with PDFs from a specific collection"""
    items_with_pdfs = []

    # Get items from the collection
    collection_items = zot.collection_items(collection_key)

    # Filter for items that have PDFs
    for item in collection_items:
        # Skip if not a regular item
        if item["data"].get("itemType") == "attachment":
            continue

        # Check if item has attachments
        try:
            children = zot.children(item["key"])
            for child in children:
                if child["data"].get("contentType") == "application/pdf" or (
                    child["data"].get("itemType") == "attachment"
                    and child["data"].get("filename", "").lower().endswith(".pdf")
                ):
                    items_with_pdfs.append((item, child))
                    break  # Only get the first PDF attachment
        except Exception as e:
            print(
                "Warning: Could not get attachments for "
                f"{item['data'].get('title', 'Unknown')}: {str(e)}"
            )
            continue

    return items_with_pdfs


def get_pdf_content(zot, pdf_item, title):
    """Try multiple methods to get PDF content"""
    # Method 1: Try Zotero storage first (since we know it's there if in iOS app)
    print("Attempting download from Zotero storage...")
    try:
        # Get the download URL with authentication
        download_url = (
            f"https://api.zotero.org/users/{LIBRARY_ID}/items/{pdf_item['key']}/file"
        )
        headers = {"Authorization": f"Bearer {API_KEY}", "Zotero-API-Version": "3"}

        # First request to get the signed URL
        response = requests.get(download_url, headers=headers, allow_redirects=False)
        if response.status_code == 302:  # Expected redirect
            signed_url = response.headers.get("Location")
            if signed_url:
                print("Got signed URL from Zotero, downloading file...")
                file_response = requests.get(signed_url)
                if file_response.status_code == 200:
                    return file_response.content
                print(f"File download failed with status {file_response.status_code}")
        elif response.status_code == 200:  # Direct download
            return response.content
        print(f"Zotero storage download failed with status {response.status_code}")
    except Exception as e:
        print(f"Zotero storage download failed: {str(e)}")

    # Method 2: Direct URL if it's a linked file (fallback)
    url = pdf_item["data"].get("url", "")
    if url and pdf_item["data"].get("linkMode") == "imported_url":
        print(f"Attempting download from URL: {url}")
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = requests.get(url, headers=headers, allow_redirects=True)
            if response.status_code == 200:
                return response.content
            print(f"URL download failed with status {response.status_code}")
        except Exception as e:
            print(f"URL download failed: {str(e)}")

    # Method 3: Check for alternative URLs (last resort)
    alt_urls = []
    if "DOI" in pdf_item["data"]:
        doi = pdf_item["data"]["DOI"]
        print(f"Found DOI: {doi}")
        try:
            unpaywall_url = f"https://api.unpaywall.org/v2/{doi}?email={CONFIG['EMAIL_FOR_UNPAYWALL']}"
            response = requests.get(unpaywall_url)
            if response.status_code == 200:
                data = response.json()
                if data.get("is_oa") and data.get("best_oa_location"):
                    alt_urls.append(data["best_oa_location"]["url"])
        except Exception as e:
            print(f"Unpaywall lookup failed: {str(e)}")

    for alt_url in alt_urls:
        try:
            print(f"Trying alternative URL: {alt_url}")
            response = requests.get(
                alt_url, headers={"User-Agent": "Mozilla/5.0"}, allow_redirects=True
            )
            if response.status_code == 200:
                return response.content
        except Exception as e:
            print(f"Alternative URL failed: {str(e)}")

    print("All download attempts failed. Manual intervention may be required.")
    return None


def combine_pdfs(items_with_pdfs, zot, output_path):
    """Combine PDFs with size management, splitting into chunks when approaching 100MB.

    Args:
        items_with_pdfs (list): List of tuples containing (parent_item, pdf_item)
        zot (zotero.Zotero): Initialized Zotero client
        output_path (str): Base path for output files

    Returns:
        list: List of dictionaries containing information about created chunks
            Each dict has:
            - 'path': Path to the chunk file
            - 'size': Size in MB
            - 'papers': List of papers in the chunk
    """
    MAX_SIZE_MB = 95  # Buffer before 100MB limit
    chunks_info = []
    current_chunk = 1
    processed_papers = []
    failed_papers = []

    def get_chunk_path(base_path, chunk_num):
        """Generate path for PDF chunk."""
        name, ext = os.path.splitext(base_path)
        return f"{name}_chunk{chunk_num}{ext}"

    def create_new_merger():
        """Create new PDF merger for next chunk."""
        if hasattr(create_new_merger, "current_merger"):
            create_new_merger.current_merger.close()
        create_new_merger.current_merger = PdfMerger()
        return create_new_merger.current_merger

    merger = create_new_merger()
    current_temp_path = get_chunk_path(output_path, current_chunk)
    current_chunk_papers = []

    # Create temporary directory for downloading PDFs
    with tempfile.TemporaryDirectory() as temp_dir:
        for parent_item, pdf_item in items_with_pdfs:
            try:
                title = parent_item["data"].get("title", "Untitled")
                print(f"\nProcessing: {title}")

                pdf_content = get_pdf_content(zot, pdf_item, title)

                if pdf_content:
                    temp_pdf_path = os.path.join(temp_dir, f"{pdf_item['key']}.pdf")
                    with open(temp_pdf_path, "wb") as f:
                        f.write(pdf_content)

                    # Check current file size
                    merger.append(temp_pdf_path, outline_item=title)
                    merger.write(current_temp_path)
                    current_size_mb = os.path.getsize(current_temp_path) / (1024 * 1024)

                    if current_size_mb >= MAX_SIZE_MB:
                        # Save current chunk info
                        chunks_info.append(
                            {
                                "path": current_temp_path,
                                "size": current_size_mb,
                                "papers": current_chunk_papers.copy(),
                            }
                        )

                        # Start new chunk
                        current_chunk += 1
                        current_temp_path = get_chunk_path(output_path, current_chunk)
                        merger = create_new_merger()
                        merger.append(temp_pdf_path, outline_item=title)
                        current_chunk_papers = []

                    current_chunk_papers.append(
                        {"title": title, "pages": len(PdfReader(temp_pdf_path).pages)}
                    )
                    processed_papers.append(current_chunk_papers[-1])
                    print(f"Added: {title} to chunk {current_chunk}")

                else:
                    print(f"Failed to get PDF for: {title}")
                    failed_papers.append(title)

            except Exception as e:
                print(f"Error processing {title}: {str(e)}")
                failed_papers.append(title)
                continue

    # Save final chunk
    if current_chunk_papers:
        merger.write(current_temp_path)
        final_size_mb = os.path.getsize(current_temp_path) / (1024 * 1024)
        chunks_info.append(
            {
                "path": current_temp_path,
                "size": final_size_mb,
                "papers": current_chunk_papers,
            }
        )

    # Print summary
    print("\nProcessing Summary:")
    print("=" * 50)
    for i, chunk in enumerate(chunks_info, 1):
        print(f"\nChunk {i} ({chunk['size']:.1f}MB):")
        for paper in chunk["papers"]:
            print(f"- {paper['title']}: {paper['pages']} pages")

    if failed_papers:
        print("\nFailed to process papers:")
        for paper in failed_papers:
            print(f"- {paper}")

    return chunks_info


def test_zotero_access(zot):
    """Test basic Zotero access"""
    print("\nTesting Zotero access...")
    try:
        # Test basic access
        items = zot.top(limit=1)
        print("✓ Can access library")

        # Test collection access
        collections = zot.collections()
        print("✓ Can access collections")

        # Test file access
        try:
            # Try to get first PDF attachment
            for item in zot.top(limit=50):
                children = zot.children(item["key"])
                for child in children:
                    if child["data"].get("contentType") == "application/pdf":
                        print(
                            f"Testing file download for {item['data'].get('title', 'Unknown')}"
                        )
                        content = zot.file(child["key"])
                        if content:
                            print("✓ Can download files")
                            return True
        except Exception as e:
            print(f"✗ File access failed: {str(e)}")
            return False

    except Exception as e:
        print(f"✗ Basic access failed: {str(e)}")
        return False


def print_detailed_summary(processed_papers, failed_papers):
    """Print detailed summary of processing results"""
    print("\nDetailed Summary:")
    print("=" * 50)

    # Success rate
    total = len(processed_papers) + len(failed_papers)
    success_rate = (len(processed_papers) / total) * 100
    print(f"Success Rate: {success_rate:.1f}% ({len(processed_papers)}/{total})")

    # Analyze failures
    failure_reasons = {"403": 0, "EOF": 0, "proxy": 0, "other": 0}

    for paper in failed_papers:
        if "403" in paper.get("error", ""):
            failure_reasons["403"] += 1
        elif "EOF" in paper.get("error", ""):
            failure_reasons["EOF"] += 1
        elif "proxy" in paper.get("error", "").lower():
            failure_reasons["proxy"] += 1
        else:
            failure_reasons["other"] += 1

    print("\nFailure Analysis:")
    for reason, count in failure_reasons.items():
        print(f"- {reason}: {count} papers")


def find_nested_collection(zot, collection_path):
    """Find a collection by its full path (e.g., 'rev/s2:advances/s2.1:neurotech')"""
    print(f"Looking for collection path: {collection_path}")
    collection_names = collection_path.split(">")
    current_key = None

    for i, name in enumerate(collection_names):
        name = name.strip()  # Remove any whitespace
        if i == 0:
            # Find top-level collection
            print(f"Looking for top-level collection: {name}")
            collections = zot.collections()
        else:
            # Find subcollection
            print(f"Looking for subcollection: {name}")
            collections = zot.collections_sub(current_key)

        found = False
        for collection in collections:
            if collection["data"]["name"].lower() == name.lower():
                current_key = collection["key"]
                print(f"Found: {name}")
                found = True
                break

        if not found:
            print(f"Collection '{name}' not found in path {collection_path}")
            return None

    return current_key


def get_all_subcollections(zot, parent_key):
    """Get all subcollections of a given collection"""
    subcollections = zot.collections_sub(parent_key)
    return subcollections


def main():
    """Main function to process Zotero collections and combine PDFs.

    Handles both single collection and recursive subcollection processing.
    Creates multiple PDF chunks when combined size approaches 100MB.
    """
    # Initialize Zotero client
    zot = zotero.Zotero(LIBRARY_ID, LIBRARY_TYPE, API_KEY)

    # Add command line argument parsing with default from RECURSIVE constant
    parser = argparse.ArgumentParser(description="Combine PDFs from Zotero collections")
    parser.add_argument(
        "--recursive",
        "-r",
        action="store_true",
        default=RECURSIVE,
        help="Process subcollections recursively",
    )
    args = parser.parse_args()

    # Use path to parent collection
    COLLECTION_PATH = (
        f"{PARENT_COLLECTION}>{PARENT_TARGET_COLLECTION}>{TARGET_SUBCOLLECTION}"
    )

    # Find the parent collection
    parent_key = find_nested_collection(zot, COLLECTION_PATH)

    if not parent_key:
        print("Parent collection not found!")
        return

    if args.recursive:
        # Get all subcollections
        print(f"\nFetching subcollections from {COLLECTION_PATH}...")
        subcollections = get_all_subcollections(zot, parent_key)

        if not subcollections:
            print("No subcollections found. Processing parent collection only...")
            subcollections = [
                {"key": parent_key, "data": {"name": COLLECTION_PATH.split(">")[-1]}}
            ]
        else:
            print(f"Found {len(subcollections)} subcollections")
            subcollections.append(
                {"key": parent_key, "data": {"name": COLLECTION_PATH.split(">")[-1]}}
            )

        # Process each subcollection
        for collection in subcollections:
            collection_name = collection["data"]["name"]
            print(f"\n{'='*50}")
            print(f"Processing collection: {collection_name}")
            print(f"{'='*50}")

            items_with_pdfs = get_collection_items_with_pdfs(zot, collection["key"])

            if not items_with_pdfs:
                print("No PDFs found in this collection")
                continue

            print(f"Found {len(items_with_pdfs)} items with PDFs")

            # Create base filename for chunks
            path_parts = COLLECTION_PATH.split(">")
            if collection_name != path_parts[-1]:
                full_name = f"{path_parts[1]}_{path_parts[2]}_{collection_name}"
            else:
                full_name = f"{path_parts[1]}_{path_parts[2]}"

            output_name = full_name.replace(":", "_").replace("&", "_and_")
            output_path = f"{output_name}_papers.pdf"

            # Combine PDFs and get chunk information
            chunks_info = combine_pdfs(items_with_pdfs, zot, output_path)

            # Print final summary for this collection
            print(f"\nCreated {len(chunks_info)} chunks for {collection_name}:")
            total_size = sum(chunk["size"] for chunk in chunks_info)
            total_papers = sum(len(chunk["papers"]) for chunk in chunks_info)
            print(f"Total size: {total_size:.1f}MB")
            print(f"Total papers: {total_papers}")
    else:
        # Process single collection
        items_with_pdfs = get_collection_items_with_pdfs(zot, parent_key)
        if not items_with_pdfs:
            print("No PDFs found in the collection")
            return

        print(f"Found {len(items_with_pdfs)} items with PDFs")

        path_parts = COLLECTION_PATH.split(">")
        output_name = f"{path_parts[1]}_{path_parts[2]}".replace(":", "_").replace(
            "&", "_and_"
        )
        output_path = f"{output_name}_papers.pdf"

        # Combine PDFs and get chunk information
        chunks_info = combine_pdfs(items_with_pdfs, zot, output_path)

        # Print final summary
        print(f"\nCreated {len(chunks_info)} chunks:")
        total_size = sum(chunk["size"] for chunk in chunks_info)
        total_papers = sum(len(chunk["papers"]) for chunk in chunks_info)
        print(f"Total size: {total_size:.1f}MB")
        print(f"Total papers: {total_papers}")


if __name__ == "__main__":
    main()
