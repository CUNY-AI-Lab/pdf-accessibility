"""
AI-based PDF tagger that replaces Adobe AutoTag API.

Three-phase pipeline:
  Phase A: PDF extraction using PyMuPDF (text blocks, images, metadata)
  Phase B: LLM structure analysis using vision model via Bedrock Converse API
  Phase C: PDF tag writing using pikepdf (PDF/UA structure tree)

Reuses from original adobe_autotag_processor.py:
  - TOC insertion (PyMuPDF)
  - Viewer preferences (pypdf)
  - SQLite DB creation for image context
  - Language detection (AWS Comprehend)
  - S3 upload/download patterns
"""

import os
import sys
import json
import re
import logging
import sqlite3
import zipfile
import io
import math

import boto3
import pymupdf  # PyMuPDF / fitz
import pikepdf
from pypdf import PdfReader, PdfWriter
from PIL import Image
import openpyxl
import pandas as pd

from lib.bedrock_model_client import BedrockModelClient

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

s3 = boto3.client('s3')


# ---------------------------------------------------------------------------
# S3 helpers
# ---------------------------------------------------------------------------

def download_file_from_s3(bucket_name, file_base_name, file_key, local_path):
    logging.info(f"File key in the download_file_from_s3: {file_key}")
    s3.download_file(bucket_name, f"temp/{file_base_name}/{file_key}", local_path)
    logging.info(f"Downloaded {file_key} from {bucket_name} to {local_path}")


def save_to_s3(filename, bucket_name, folder_name, file_basename, file_key):
    with open(filename, "rb") as data:
        s3.upload_fileobj(data, bucket_name, f"temp/{file_basename}/{folder_name}/COMPLIANT_{file_key}")


# ---------------------------------------------------------------------------
# Reused functions (no Adobe dependency)
# ---------------------------------------------------------------------------

def add_viewer_preferences(pdf_path, filename):
    reader = PdfReader(pdf_path)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.create_viewer_preferences()
    writer.viewer_preferences.display_doctitle = True
    with open(filename, "wb") as f:
        writer.write(f)
    logger.info(f'Filename : {filename} | Viewer preferences added to the PDF')


def add_toc_to_pdf(filename, pdf_document, structured_data):
    """Add TOC based on heading elements in structured data."""
    bookmarks = []
    for element in structured_data.get("elements", []):
        path = element.get("Path", "")
        if re.search(r'H[1-6]', path) and "Text" in element:
            # Determine heading level
            match = re.search(r'H(\d)', path)
            level = int(match.group(1)) if match else 1
            bookmarks.append((level, element["Text"], element.get("Page", 0) + 1))

    toc_list = [[level, title, page] for level, title, page in bookmarks]
    if toc_list:
        # Normalize levels: first entry must be level 1, no jumps > 1
        min_level = min(entry[0] for entry in toc_list)
        for entry in toc_list:
            entry[0] = entry[0] - min_level + 1
        # Ensure no level jumps > 1
        prev_level = 0
        for entry in toc_list:
            if entry[0] > prev_level + 1:
                entry[0] = prev_level + 1
            prev_level = entry[0]
        pdf_document.set_toc(toc_list)
        logging.info(f'Filename : {filename} | TOC entries added to the PDF ({len(toc_list)} entries)')
    else:
        logging.info(f'Filename : {filename} | No heading elements found for TOC')


def set_language_comprehend(filename, text_content, pdf_document):
    """Detect dominant language using AWS Comprehend and set it on the PDF."""
    if not text_content or len(text_content.strip()) < 10:
        pdf_document.set_language("en")
        logging.info(f'Filename : {filename} | Insufficient text for language detection, defaulting to en')
        return

    # Comprehend has a 5000 byte limit
    truncated = text_content[:4900]
    comprehend = boto3.client('comprehend')
    response = comprehend.detect_dominant_language(Text=truncated)
    languages = response['Languages']
    dominant_language = max(languages, key=lambda lang: lang['Score'])
    pdf_document.set_language(dominant_language['LanguageCode'])
    logging.info(f'Filename : {filename} | Language set to {dominant_language["LanguageCode"]}')


# ---------------------------------------------------------------------------
# Phase A: PDF Extraction using PyMuPDF
# ---------------------------------------------------------------------------

def extract_pdf_content(pdf_path, filename):
    """
    Extract structured content from PDF using PyMuPDF.

    Returns a dict matching the schema expected by downstream code:
    {
        "elements": [
            {"Path": "//Document/H1", "Text": "...", "Page": 0, "Bounds": [x0,y0,x1,y1]},
            {"Path": "//Document/P", "Text": "...", "Page": 0, "Bounds": [x0,y0,x1,y1]},
            {"Path": "//Document/Figure", "Page": 0, "Bounds": [...], "filePaths": ["figures/img_0.png"]},
            ...
        ]
    }
    """
    doc = pymupdf.open(pdf_path)
    elements = []
    figure_dir = "output/figures"
    os.makedirs(figure_dir, exist_ok=True)
    img_counter = 0

    for page_num in range(len(doc)):
        page = doc[page_num]

        # Extract text blocks: (x0, y0, x1, y1, text, block_no, block_type)
        blocks = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)

        for block in blocks.get("blocks", []):
            if block["type"] == 0:  # Text block
                # Combine all spans in all lines
                full_text = ""
                max_font_size = 0
                is_bold = False
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        full_text += span["text"]
                        if span["size"] > max_font_size:
                            max_font_size = span["size"]
                        if "bold" in span.get("font", "").lower():
                            is_bold = True
                    full_text += "\n"
                full_text = full_text.strip()
                if not full_text:
                    continue

                bbox = block["bbox"]  # (x0, y0, x1, y1)
                elements.append({
                    "Path": "//Document/P",  # Will be reclassified by LLM
                    "Text": full_text,
                    "Page": page_num,
                    "Bounds": list(bbox),
                    "_font_size": max_font_size,
                    "_is_bold": is_bold,
                })

            elif block["type"] == 1:  # Image block
                bbox = block["bbox"]
                # Extract image
                img_data = block.get("image")
                if img_data:
                    img_path = os.path.join(figure_dir, f"figure_{page_num}_{img_counter}.png")
                    try:
                        img = Image.open(io.BytesIO(img_data))
                        img.save(img_path, "PNG")
                    except Exception as e:
                        logging.warning(f"Failed to save image block: {e}")
                        img_path = None
                else:
                    img_path = None

                element = {
                    "Path": "//Document/Figure",
                    "Page": page_num,
                    "Bounds": list(bbox),
                }
                if img_path:
                    element["filePaths"] = [img_path]
                elements.append(element)
                img_counter += 1

        # Also extract standalone images via page.get_images()
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            try:
                pix = pymupdf.Pixmap(doc, xref)
                if pix.n > 4:  # CMYK or other
                    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                img_path = os.path.join(figure_dir, f"figure_{page_num}_{img_counter}.png")
                pix.save(img_path)
                # Try to get image position from the page
                img_rects = page.get_image_rects(xref)
                if img_rects:
                    rect = img_rects[0]
                    bbox = [rect.x0, rect.y0, rect.x1, rect.y1]
                else:
                    bbox = [0, 0, pix.width, pix.height]

                # Check if we already have this image (from block extraction)
                already_exists = False
                for e in elements:
                    if e.get("Page") == page_num and "filePaths" in e:
                        existing_bounds = e["Bounds"]
                        if (abs(existing_bounds[0] - bbox[0]) < 10 and
                            abs(existing_bounds[1] - bbox[1]) < 10):
                            already_exists = True
                            break

                if not already_exists:
                    elements.append({
                        "Path": "//Document/Figure",
                        "Page": page_num,
                        "Bounds": bbox,
                        "filePaths": [img_path],
                    })
                    img_counter += 1
            except Exception as e:
                logging.warning(f"Failed to extract image xref={xref}: {e}")

    doc.close()
    logging.info(f'Filename : {filename} | Extracted {len(elements)} elements, {img_counter} images')
    return {"elements": elements}


# ---------------------------------------------------------------------------
# Phase B: LLM Structure Analysis
# ---------------------------------------------------------------------------

def classify_page_elements(pdf_path, page_num, page_elements, bedrock_client, filename):
    """
    Render a page to PNG and ask the vision LLM to classify each text block.

    Returns the page_elements list with updated "Path" fields.
    """
    doc = pymupdf.open(pdf_path)
    page = doc[page_num]

    # Render page at 150 DPI
    dpi = 150
    pix = page.get_pixmap(dpi=dpi)

    # Check size — if too large, reduce DPI
    img_bytes = pix.tobytes("png")
    if len(img_bytes) > 3_500_000:  # 3.5 MB limit for Bedrock
        dpi = 100
        pix = page.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")
    if len(img_bytes) > 3_500_000:
        dpi = 72
        pix = page.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")

    doc.close()

    # Build block descriptions for the prompt
    block_descriptions = []
    for i, elem in enumerate(page_elements):
        text_preview = elem.get("Text", "")[:200]
        font_size = elem.get("_font_size", 0)
        is_bold = elem.get("_is_bold", False)
        elem_type = "image" if "Figure" in elem.get("Path", "") else "text"

        desc = f"Block {i}: type={elem_type}"
        if text_preview:
            desc += f", font_size={font_size:.1f}, bold={is_bold}, text=\"{text_preview}\""
        block_descriptions.append(desc)

    blocks_text = "\n".join(block_descriptions)

    prompt = f"""Analyze this PDF page image and classify each text/image block into its semantic role.

Here are the blocks extracted from page {page_num + 1}:
{blocks_text}

For each block, classify it as one of:
- H1, H2, H3, H4, H5, H6 (heading levels)
- P (paragraph)
- L (list container) / LI (list item)
- Table (table element)
- Figure (image/figure)
- Header (page header - repeating at top)
- Footer (page footer - repeating at bottom)
- Artifact (decorative, page numbers, watermarks)

Consider:
1. Font size relative to other text (larger = likely heading)
2. Bold text at start of sections = likely heading
3. Position on page (top/bottom edges = likely header/footer)
4. Numbered or bulleted text = list items
5. Short repeated text at edges = artifacts

Return ONLY a JSON array where each element is the classification for the corresponding block index:
[{{"block": 0, "tag": "H1"}}, {{"block": 1, "tag": "P"}}, ...]

Return ONLY the JSON array, no other text."""

    system_prompt = "You are a document structure analysis expert. You classify PDF content blocks into semantic HTML/PDF tags for accessibility."

    try:
        response = bedrock_client.invoke_with_image(
            prompt, img_bytes, image_format="png",
            system_prompt=system_prompt,
            max_tokens=2000,
            temperature=0.1,
        )

        # Parse JSON response
        # Try to extract JSON array from response
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            classifications = json.loads(json_match.group())
        else:
            logging.warning(f"Page {page_num}: Could not parse LLM response, using heuristic fallback")
            return _heuristic_classify(page_elements)

        # Apply classifications
        for item in classifications:
            block_idx = item.get("block", -1)
            tag = item.get("tag", "P")
            if 0 <= block_idx < len(page_elements):
                if tag in ("H1", "H2", "H3", "H4", "H5", "H6"):
                    page_elements[block_idx]["Path"] = f"//Document/{tag}"
                elif tag == "P":
                    page_elements[block_idx]["Path"] = "//Document/P"
                elif tag in ("L", "LI"):
                    page_elements[block_idx]["Path"] = f"//Document/L/LI"
                elif tag == "Table":
                    page_elements[block_idx]["Path"] = "//Document/Table"
                elif tag == "Figure":
                    page_elements[block_idx]["Path"] = "//Document/Figure"
                elif tag in ("Header", "Footer", "Artifact"):
                    page_elements[block_idx]["Path"] = f"//Document/Artifact"
                else:
                    page_elements[block_idx]["Path"] = "//Document/P"

        logging.info(f'Filename : {filename} | Page {page_num}: classified {len(classifications)} blocks')
        return page_elements

    except Exception as e:
        logging.warning(f'Page {page_num}: LLM classification failed ({e}), using heuristic fallback')
        return _heuristic_classify(page_elements)


def _heuristic_classify(elements):
    """Fallback classification based on font size and position."""
    if not elements:
        return elements

    # Collect font sizes for text elements
    font_sizes = [e.get("_font_size", 0) for e in elements if e.get("_font_size", 0) > 0]
    if not font_sizes:
        return elements

    median_size = sorted(font_sizes)[len(font_sizes) // 2]

    for elem in elements:
        if "Figure" in elem.get("Path", ""):
            continue  # Keep figures as figures

        font_size = elem.get("_font_size", 0)
        is_bold = elem.get("_is_bold", False)
        text = elem.get("Text", "")

        if font_size > median_size * 1.5 and is_bold:
            elem["Path"] = "//Document/H1"
        elif font_size > median_size * 1.3 and is_bold:
            elem["Path"] = "//Document/H2"
        elif font_size > median_size * 1.1 and is_bold:
            elem["Path"] = "//Document/H3"
        elif is_bold and len(text) < 100:
            elem["Path"] = "//Document/H4"
        elif re.match(r'^\s*[\u2022\u2023\u25E6\u2043\u2219•·\-\*]\s', text):
            elem["Path"] = "//Document/L/LI"
        elif re.match(r'^\s*\d+[\.\)]\s', text):
            elem["Path"] = "//Document/L/LI"
        else:
            elem["Path"] = "//Document/P"

    return elements


def run_llm_classification(pdf_path, structured_data, filename):
    """Run LLM classification on all pages."""
    bedrock_client = BedrockModelClient(model_type="vision")

    # Group elements by page
    by_page = {}
    for elem in structured_data["elements"]:
        page = elem.get("Page", 0)
        if page not in by_page:
            by_page[page] = []
        by_page[page].append(elem)

    # Classify each page
    all_elements = []
    for page_num in sorted(by_page.keys()):
        page_elements = by_page[page_num]
        classified = classify_page_elements(pdf_path, page_num, page_elements, bedrock_client, filename)
        all_elements.extend(classified)

    structured_data["elements"] = all_elements
    return structured_data


# ---------------------------------------------------------------------------
# Phase C: PDF Tag Writing using pikepdf
# ---------------------------------------------------------------------------

def write_pdf_tags(input_path, output_path, structured_data, filename):
    """
    Write PDF/UA structure tags using pikepdf.

    Creates:
    - /MarkInfo with /Marked true
    - /StructTreeRoot with /Document root element
    - Semantic structure elements (H1-H6, P, Figure, Table, L/LI)
    - /Tabs /S on each page
    """
    pdf = pikepdf.Pdf.open(input_path)

    # Set MarkInfo
    mark_info = pikepdf.Dictionary()
    mark_info["/Marked"] = True
    pdf.Root["/MarkInfo"] = mark_info

    # Set Tabs /S on each page
    for page in pdf.pages:
        page["/Tabs"] = pikepdf.Name.S

    # Create structure tree
    struct_tree_root = pikepdf.Dictionary()
    struct_tree_root["/Type"] = pikepdf.Name.StructTreeRoot

    # Create Document element
    doc_elem = pikepdf.Dictionary()
    doc_elem["/Type"] = pikepdf.Name.StructElem
    doc_elem["/S"] = pikepdf.Name.Document
    doc_elem["/P"] = pdf.make_indirect(struct_tree_root)

    children = pikepdf.Array()

    # Map path to PDF tag name
    tag_map = {
        "H1": "H1", "H2": "H2", "H3": "H3", "H4": "H4", "H5": "H5", "H6": "H6",
        "P": "P", "Figure": "Figure", "Table": "Table",
        "L": "L", "LI": "LI", "Lbl": "Lbl", "LBody": "LBody",
        "Artifact": "Artifact",
    }

    doc_elem_ref = pdf.make_indirect(doc_elem)

    for elem in structured_data.get("elements", []):
        path = elem.get("Path", "")

        # Extract tag name from path
        tag_name = "P"  # default
        for key in tag_map:
            if key in path:
                tag_name = tag_map[key]
                break

        if tag_name == "Artifact":
            continue  # Artifacts don't get structure elements

        struct_elem = pikepdf.Dictionary()
        struct_elem["/Type"] = pikepdf.Name.StructElem
        struct_elem["/S"] = pikepdf.Name(f"/{tag_name}")
        struct_elem["/P"] = doc_elem_ref

        # Add Alt text for figures
        if tag_name == "Figure" and "Alt" in elem:
            struct_elem["/Alt"] = pikepdf.String(elem["Alt"])

        # Handle list items: wrap in L > LI > LBody
        if tag_name == "LI":
            li_elem = pikepdf.Dictionary()
            li_elem["/Type"] = pikepdf.Name.StructElem
            li_elem["/S"] = pikepdf.Name.LI
            li_elem["/P"] = doc_elem_ref
            lbody = pikepdf.Dictionary()
            lbody["/Type"] = pikepdf.Name.StructElem
            lbody["/S"] = pikepdf.Name.LBody
            lbody["/P"] = pdf.make_indirect(li_elem)
            li_elem["/K"] = pikepdf.Array([pdf.make_indirect(lbody)])
            children.append(pdf.make_indirect(li_elem))
            continue

        children.append(pdf.make_indirect(struct_elem))

    doc_elem["/K"] = children
    struct_tree_root["/K"] = pikepdf.Array([doc_elem_ref])

    # Set ParentTree (required for PDF/UA)
    parent_tree = pikepdf.Dictionary()
    parent_tree["/Type"] = pikepdf.Name.NumberTree
    parent_tree["/Nums"] = pikepdf.Array()
    struct_tree_root["/ParentTree"] = pdf.make_indirect(parent_tree)

    pdf.Root["/StructTreeRoot"] = pdf.make_indirect(struct_tree_root)

    pdf.save(output_path)
    pdf.close()
    logging.info(f'Filename : {filename} | PDF/UA structure tags written to {output_path}')


# ---------------------------------------------------------------------------
# SQLite DB creation for alt-text generator (reused logic)
# ---------------------------------------------------------------------------

def create_sqlite_db(structured_data, filename, images_output_dir, bucket_name, s3_folder_autotag, file_key):
    """Create SQLite DB with image context data for the alt-text generator container."""
    db_path = os.path.join(images_output_dir, "temp_images_data.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS image_data (
            objid TEXT,
            img_path TEXT,
            prev TEXT,
            current TEXT,
            next TEXT,
            context TEXT
        )
    """)

    # Group elements by page for context building
    by_page = {}
    for elem in structured_data["elements"]:
        page = elem.get("Page", 0)
        if page not in by_page:
            by_page[page] = []
        by_page[page].append(elem)

    figure_idx = 0
    for elem in structured_data["elements"]:
        if "Figure" not in elem.get("Path", ""):
            continue
        if "filePaths" not in elem or not elem["filePaths"]:
            continue

        page = elem.get("Page", 0)
        img_file = os.path.basename(elem["filePaths"][0])

        # Build context from all elements on the same page
        context_parts = []
        for page_elem in by_page.get(page, []):
            if page_elem.get("Text"):
                context_parts.append(page_elem["Text"])
            if "filePaths" in page_elem and page_elem["filePaths"]:
                img_name = os.path.basename(page_elem["filePaths"][0])
                if page_elem is elem:
                    context_parts.append(f"<IMAGE INTERESTED>{img_name}</IMAGE INTERESTED>")
                else:
                    context_parts.append(f"<OTHER IMAGE>{img_name}</OTHER IMAGE>")

        context = " ".join(context_parts)

        # Use figure index as objid (will map to PDF object later)
        objid = str(figure_idx)
        figure_idx += 1

        cursor.execute("""
            INSERT INTO image_data (objid, img_path, context)
            VALUES (?, ?, ?)
        """, (objid, img_file, context))

        # Upload image to S3
        img_local_path = elem["filePaths"][0]
        if os.path.exists(img_local_path):
            s3.upload_file(
                img_local_path, bucket_name,
                f'{s3_folder_autotag}/images/{file_key}_{img_file}'
            )

    conn.commit()
    conn.close()
    logging.info(f'Filename : {filename} | SQLite DB created with {figure_idx} images')

    # Upload DB to S3
    s3.upload_file(db_path, bucket_name, f'{s3_folder_autotag}/{file_key}_temp_images_data.db')
    logging.info(f'Filename : {filename} | Uploaded SQLite DB to S3')


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main():
    file_key = None
    file_base_name = None

    try:
        bucket_name = os.getenv('S3_BUCKET_NAME')
        s3_file_key = os.getenv('S3_FILE_KEY')

        if not bucket_name or not s3_file_key:
            logging.error("Error: S3_BUCKET_NAME and S3_FILE_KEY environment variables are required.")
            sys.exit(1)

        file_key = s3_file_key.split('/')[2]
        file_base_name = s3_file_key.split('/')[1]
        logging.info(f'Filename : {file_key} | Bucket Name: {bucket_name}')

        local_file_path = os.path.basename(file_key)
        logging.info(f'Filename : {file_key} | Downloading file from S3...')
        download_file_from_s3(bucket_name, file_base_name, file_key, local_file_path)

        base_filename = os.path.basename(local_file_path)
        filename = "COMPLIANT_" + base_filename

        # Add viewer preferences (no Adobe dependency)
        logging.info(f'Filename : {file_key} | Adding viewer preferences...')
        add_viewer_preferences(local_file_path, filename)

        # Phase A: Extract PDF content using PyMuPDF
        logging.info(f'Filename : {file_key} | Phase A: Extracting PDF content...')
        structured_data = extract_pdf_content(filename, file_key)

        # Phase B: LLM structure classification
        logging.info(f'Filename : {file_key} | Phase B: Running LLM structure analysis...')
        structured_data = run_llm_classification(filename, structured_data, file_key)

        # Save structured data for downstream use
        os.makedirs("output/zipfile", exist_ok=True)
        structured_data_path = f"output/zipfile/structuredData.json"
        # Clean internal keys before saving
        clean_data = {"elements": []}
        for elem in structured_data["elements"]:
            clean_elem = {k: v for k, v in elem.items() if not k.startswith("_")}
            clean_data["elements"].append(clean_elem)
        with open(structured_data_path, "w") as f:
            json.dump(clean_data, f, indent=2)

        # Phase C: Write PDF/UA tags using pikepdf
        logging.info(f'Filename : {file_key} | Phase C: Writing PDF/UA structure tags...')
        tagged_path = "tagged_" + filename
        write_pdf_tags(filename, tagged_path, structured_data, file_key)

        # Open tagged PDF with PyMuPDF for TOC and language
        pdf_document = pymupdf.open(tagged_path)

        # Add TOC
        logging.info(f'Filename : {file_key} | Adding TOC entries...')
        add_toc_to_pdf(file_key, pdf_document, clean_data)

        # Detect and set language
        logging.info(f'Filename : {file_key} | Detecting language...')
        all_text = " ".join(e.get("Text", "") for e in structured_data["elements"] if e.get("Text"))
        set_language_comprehend(file_key, all_text, pdf_document)

        pdf_document.saveIncr()
        pdf_document.close()

        # Upload tagged PDF to S3
        logging.info(f'Filename : {file_key} | Uploading processed PDF to S3...')
        save_to_s3(tagged_path, bucket_name, "output_autotag", file_base_name, file_key)

        logging.info(f"PDF saved with tags, metadata, and TOC. File location: COMPLIANT_{file_key}")

        # Create SQLite DB and upload images for alt-text generator
        images_output_dir = "output/images"
        os.makedirs(images_output_dir, exist_ok=True)
        s3_folder_autotag = f"temp/{file_base_name}/output_autotag"

        logging.info(f'Filename : {file_key} | Creating image context DB...')
        create_sqlite_db(structured_data, file_key, images_output_dir, bucket_name, s3_folder_autotag, file_key)

        logging.info(f'Filename : {file_key} | Processing completed successfully')
        logger.info(f"File: {file_base_name}, Status: Succeeded in First ECS task")

    except Exception as e:
        logger.error(f"File: {file_base_name}, Status: Failed in First ECS task")
        logger.error(f"Filename : {file_key} | Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
