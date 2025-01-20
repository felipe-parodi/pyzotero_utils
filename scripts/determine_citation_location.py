#!/usr/bin/env python
"""Determine optimal citation locations in review paper outline for papers.

This script takes CSV files output by llm_summarize_pdfs.py and uses GPT-4 to 
suggest where each paper should be cited in the review paper outline.

Usage:
    python determine_citation_location.py

Returns:
    Creates new CSV with added Citation_Locations column containing 
    comma-separated paragraph IDs.
"""

import pandas as pd
import openai
import sys
from pathlib import Path
import re

# Add the parent directory to the Python path
parent_dir = str(Path(__file__).resolve().parent.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from config import (
    OPENAI_API_KEY,
    review_outline_by_paragraph
)

# Configure OpenAI
openai.api_key = OPENAI_API_KEY

# Input CSV path
csv_file = r"/Users/felipeparodi/Documents/tics_docs/pyzotero_utils/data/zotero_summaries_s4.csv"


def parse_outline(outline_text):
    """Convert outline text to dict mapping paragraph IDs to content.
    
    Args:
        outline_text (str): Raw outline text to parse
    
    Returns:
        Dict[str, str]: Maps IDs like "2.1.1" to paragraph content
        Example: {
            "2.0.1": "First, a concise 'historical' paragraph...",
            "2.1.1": "Core breakthrough: stable wireless...",
        }
    """
    outline_dict = {}
    current_section = ""
    
    for line in outline_text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        
        # Main section header (e.g., "Section 2: Techniques...")
        if (line.startswith('Section ') and ':' in line and 
            'paragraph' not in line):
            current_section = line.split(':')[0].split()[-1]
            continue
        
        # Subsection header (e.g., "Section 2.1: Recording...")
        if (line.startswith('Section ') and '.' in line and ':' in line and 
            'paragraph' not in line):
            current_section = line.split(':')[0].split()[-1]
            continue
        
        # Paragraph content
        if 'paragraph' in line:
            # Extract section and paragraph numbers
            parts = line.split(':', 1)
            section_info = parts[0].strip()
            content = parts[1].strip()
            
            # Parse section and paragraph numbers
            if '.' in section_info:  # e.g., "Section 2.1 paragraph 1"
                section_num = section_info.split()[1]  # "2.1"
                para_num = section_info.split()[-1]    # "1"
                para_id = f"{section_num}.{para_num}"
            else:  # e.g., "Section 2 paragraph 1"
                section_num = section_info.split()[1]  # "2"
                para_num = section_info.split()[-1]    # "1"
                para_id = f"{section_num}.0.{para_num}"
            
            outline_dict[para_id] = content
        
        # Handle multi-line paragraphs (e.g., 3.2.1 has multiple lines)
        elif current_section and line and not line.startswith('Section'):
            last_key = list(outline_dict.keys())[-1]
            outline_dict[last_key] = outline_dict[last_key] + "\n" + line
    
    return outline_dict


def process_paper(summary, outline_dict, source_section=None):
    """Get paragraph suggestions for a paper using GPT-4.
    
    Args:
        summary (str): Paper summary from the CSV
        outline_dict (dict): Mapping of paragraph IDs to content
        source_section (str): Section number from CSV filename (e.g., "4" from "s4.csv")
    """
    # Extract primary section context for prompt
    section_context = ""
    if source_section:
        section_context = (
            f"\nNote: This paper was initially categorized for section {source_section}. "
            f"First identify relevant paragraphs in section {source_section}, "
            "then suggest additional relevant locations in other sections."
        )
    
    prompt = (
        "Given a paper summary and a review paper outline, determine the most "
        "relevant paragraphs where this paper should be cited. For each suggested "
        "paragraph, provide a brief one-line justification."
        f"{section_context}\n\n"
        "Format your response as:\n"
        "LOCATIONS: paragraph_id1, paragraph_id2, ...\n"
        "JUSTIFICATIONS:\n"
        "paragraph_id1: [one-line justification]\n"
        "paragraph_id2: [one-line justification]\n"
        "...\n\n"
        f"Paper Summary:\n{summary}\n\n"
        "Review Outline:\n"
    )
    
    # Add outline with IDs
    for para_id, content in outline_dict.items():
        prompt += f"\n[{para_id}]: {content}"

    try:
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system", 
                    "content": (
                        "You are a scientific citation assistant. Analyze where "
                        "papers should be cited and explain why. Be concise."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error processing paper: {str(e)}")
        return ""


def get_section_from_filename(filename):
    """Extract section number from filename (e.g., 's4' -> '4')."""
    match = re.search(r'summaries_s(\d+)', filename)
    return match.group(1) if match else None


def update_csv(input_csv, output_csv):
    """Process papers and update CSV with citation locations and justifications."""
    section = get_section_from_filename(input_csv)
    df = pd.read_csv(input_csv)
    outline_dict = parse_outline(review_outline_by_paragraph)
    
    # Add new columns with clear names for LLM interpretation
    df['Citation_Locations'] = ''
    df['Citation_Justifications'] = ''
    
    for idx, row in df.iterrows():
        print(f"Processing paper {idx+1}/{len(df)}: {row['Short_Citation']}...", 
              end='', flush=True)
        
        response = process_paper(row['LLM Summary'], outline_dict, section)
        
        # Parse response into clear, LLM-friendly format
        locations = ""
        justifications = []
        
        for line in response.split('\n'):
            if line.startswith('LOCATIONS:'):
                locations = line.replace('LOCATIONS:', '').strip()
            elif ':' in line and not line.startswith('JUSTIFICATIONS'):
                justifications.append(line.strip())
        
        # Store in natural language format
        df.at[idx, 'Citation_Locations'] = locations
        df.at[idx, 'Citation_Justifications'] = '\n'.join(justifications)
        print(" ✓")
    
    df.to_csv(output_csv, index=False)
    print(f"\nDone! Results saved to: {output_csv}")


def main():
    """Run the main citation location determination workflow."""
    # Define input CSVs
    base_path = Path("/Users/felipeparodi/Documents/tics_docs/pyzotero_utils/data")
    csv_files = [
        base_path / f"zotero_summaries_s{i}.csv" 
        for i in [2,3]  # sections to process
    ]
    
    # Process each CSV
    for csv_path in csv_files:
        if not csv_path.exists():
            print(f"\nSkipping {csv_path.name} - file not found")
            continue
            
        print(f"\nProcessing {csv_path.name}...")
        output_csv = csv_path.parent / csv_path.name.replace('.csv', '_with_citations.csv')
        
        try:
            update_csv(str(csv_path), str(output_csv))
            print(f"Completed processing {csv_path.name}")
        except Exception as e:
            print(f"Error processing {csv_path.name}: {str(e)}")


if __name__ == "__main__":
    main()