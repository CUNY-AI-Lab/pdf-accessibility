"""
AI-based PDF tagger Lambda function for WCAG 2.1 Level AA compliance.

Three-phase pipeline:
  Phase A: PDF extraction using PyMuPDF (text blocks, images, metadata)
  Phase B: LLM structure analysis using vision model via Bedrock Converse API
  Phase C: PDF tag writing using pikepdf (PDF/UA structure tree with MCID linkage)

Lambda wrapper around the original ECS-based ai_tagger_processor.
Reads s3_bucket, s3_key, chunk_key from the event instead of env vars.
Uses /tmp/ for all local file operations (Lambda ephemeral storage).
"""

import os
import sys
import json
import re
import logging
import sqlite3
import io

import boto3
import pymupdf  # PyMuPDF / fitz
import pikepdf
from pypdf import PdfReader, PdfWriter
from PIL import Image

from lib.bedrock_model_client import BedrockModelClient

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

s3 = boto3.client('s3')

WORK_DIR = '/tmp'


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
    """Detect dominant language using AWS Comprehend and set it on the PDF.

    Returns the detected language code (e.g. 'en', 'es').
    """
    if not text_content or len(text_content.strip()) < 10:
        pdf_document.set_language("en")
        logging.info(f'Filename : {filename} | Insufficient text for language detection, defaulting to en')
        return "en"

    truncated = text_content[:4900]
    comprehend = boto3.client('comprehend')
    response = comprehend.detect_dominant_language(Text=truncated)
    languages = response['Languages']
    dominant_language = max(languages, key=lambda lang: lang['Score'])
    lang_code = dominant_language['LanguageCode']
    pdf_document.set_language(lang_code)
    logging.info(f'Filename : {filename} | Language set to {lang_code}')
    return lang_code


# ---------------------------------------------------------------------------
# Phase A: PDF Extraction using PyMuPDF
# ---------------------------------------------------------------------------

def extract_pdf_content(pdf_path, filename):
    """Extract structured content from PDF using PyMuPDF."""
    doc = pymupdf.open(pdf_path)
    elements = []
    figure_dir = os.path.join(WORK_DIR, "output", "figures")
    os.makedirs(figure_dir, exist_ok=True)
    img_counter = 0

    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)

        for block in blocks.get("blocks", []):
            if block["type"] == 0:  # Text block
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

                # Detect symbolic fonts (Gap 12)
                is_symbolic = False
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        font_name = span.get("font", "").lower()
                        if any(pat in font_name for pat in ("symbol", "wingding", "zapfdingbat", "webding", "dingbat")):
                            is_symbolic = True
                            break
                    if is_symbolic:
                        break

                bbox = block["bbox"]
                elem_data = {
                    "Path": "//Document/P",
                    "Text": full_text,
                    "Page": page_num,
                    "Bounds": list(bbox),
                    "_font_size": max_font_size,
                    "_is_bold": is_bold,
                }
                if is_symbolic:
                    elem_data["_is_symbolic"] = True
                elements.append(elem_data)

            elif block["type"] == 1:  # Image block
                bbox = block["bbox"]
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

        for img_info in page.get_images(full=True):
            xref = img_info[0]
            try:
                pix = pymupdf.Pixmap(doc, xref)
                if pix.n > 4:
                    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                img_path = os.path.join(figure_dir, f"figure_{page_num}_{img_counter}.png")
                pix.save(img_path)
                img_rects = page.get_image_rects(xref)
                if img_rects:
                    rect = img_rects[0]
                    bbox = [rect.x0, rect.y0, rect.x1, rect.y1]
                else:
                    bbox = [0, 0, pix.width, pix.height]

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
    """Render a page to PNG and ask the vision LLM to classify each text block."""
    doc = pymupdf.open(pdf_path)
    page = doc[page_num]

    dpi = 150
    pix = page.get_pixmap(dpi=dpi)
    img_bytes = pix.tobytes("png")
    if len(img_bytes) > 3_500_000:
        dpi = 100
        pix = page.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")
    if len(img_bytes) > 3_500_000:
        dpi = 72
        pix = page.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")

    doc.close()

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

For multi-column layouts, assign reading order left column top-to-bottom before right column.

Return ONLY a JSON array where each element is the classification and logical reading order:
[{{"block": 0, "tag": "H1", "order": 0}}, {{"block": 1, "tag": "P", "order": 1}}, ...]

The "order" field is a 0-based integer indicating the logical reading order (not necessarily the same as block index).

Return ONLY the JSON array, no other text."""

    system_prompt = "You are a document structure analysis expert. You classify PDF content blocks into semantic HTML/PDF tags for accessibility."

    try:
        response = bedrock_client.invoke_with_image(
            prompt, img_bytes, image_format="png",
            system_prompt=system_prompt,
            max_tokens=2000,
            temperature=0.1,
        )

        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            classifications = json.loads(json_match.group())
        else:
            logging.warning(f"Page {page_num}: Could not parse LLM response, using heuristic fallback")
            return _heuristic_classify(page_elements)

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

        # Apply reading order if provided (Gap 2)
        order_map = {}
        for item in classifications:
            block_idx = item.get("block", -1)
            order = item.get("order")
            if order is not None and 0 <= block_idx < len(page_elements):
                order_map[block_idx] = order

        if order_map:
            for i, elem in enumerate(page_elements):
                elem["_orig_idx"] = i
                elem["_order"] = order_map.get(i, i)
            page_elements.sort(key=lambda e: e.get("_order", e.get("_orig_idx", 0)))

        logging.info(f'Filename : {filename} | Page {page_num}: classified {len(classifications)} blocks')
        return page_elements

    except Exception as e:
        logging.warning(f'Page {page_num}: LLM classification failed ({e}), using heuristic fallback')
        return _heuristic_classify(page_elements)


def _heuristic_classify(elements):
    """Fallback classification based on font size and position."""
    if not elements:
        return elements

    font_sizes = [e.get("_font_size", 0) for e in elements if e.get("_font_size", 0) > 0]
    if not font_sizes:
        return elements

    median_size = sorted(font_sizes)[len(font_sizes) // 2]

    for elem in elements:
        if "Figure" in elem.get("Path", ""):
            continue

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
        elif re.match(r'^\s*[\u2022\u2023\u25E6\u2043\u2219\u2022\u00B7\-\*]\s', text):
            elem["Path"] = "//Document/L/LI"
        elif re.match(r'^\s*\d+[\.\)]\s', text):
            elem["Path"] = "//Document/L/LI"
        else:
            elem["Path"] = "//Document/P"

    return elements


def run_llm_classification(pdf_path, structured_data, filename):
    """Run LLM classification on all pages."""
    bedrock_client = BedrockModelClient(model_type="vision")

    by_page = {}
    for elem in structured_data["elements"]:
        page = elem.get("Page", 0)
        if page not in by_page:
            by_page[page] = []
        by_page[page].append(elem)

    all_elements = []
    for page_num in sorted(by_page.keys()):
        page_elements = by_page[page_num]
        classified = classify_page_elements(pdf_path, page_num, page_elements, bedrock_client, filename)
        all_elements.extend(classified)

    structured_data["elements"] = all_elements

    # Parse table structure for Table elements
    _parse_table_structures(pdf_path, structured_data, bedrock_client, filename)

    return structured_data


def _parse_table_structures(pdf_path, structured_data, bedrock_client, filename):
    """For each Table element, ask the LLM to extract row/column structure."""
    doc = pymupdf.open(pdf_path)

    for elem in structured_data["elements"]:
        if "Table" not in elem.get("Path", ""):
            continue

        page_num = elem.get("Page", 0)
        if page_num >= len(doc):
            continue

        page = doc[page_num]
        dpi = 150
        pix = page.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")
        if len(img_bytes) > 3_500_000:
            dpi = 100
            pix = page.get_pixmap(dpi=dpi)
            img_bytes = pix.tobytes("png")

        text_preview = elem.get("Text", "")[:500]
        prompt = f"""Look at this PDF page and find the table near this text: "{text_preview}"

Extract the table structure as JSON:
{{"headers": ["Column1", "Column2", ...], "rows": [["val1", "val2", ...], ...]}}

Rules:
- Include ALL header columns
- Include ALL data rows visible in the table
- If you cannot identify a table, return {{"headers": [], "rows": []}}
- Return ONLY the JSON, no other text."""

        try:
            response = bedrock_client.invoke_with_image(
                prompt, img_bytes, image_format="png",
                system_prompt="You are a table extraction expert. Extract table data from PDF pages.",
                max_tokens=3000,
                temperature=0.1,
            )
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                table_data = json.loads(json_match.group())
                if table_data.get("headers") or table_data.get("rows"):
                    elem["_table_data"] = table_data
                    logging.info(f'Filename : {filename} | Page {page_num}: extracted table with {len(table_data.get("headers", []))} columns, {len(table_data.get("rows", []))} rows')
        except Exception as e:
            logging.warning(f'Filename : {filename} | Page {page_num}: table parsing failed ({e})')

    doc.close()


# ---------------------------------------------------------------------------
# Phase C: PDF Tag Writing using pikepdf (with MCID linkage)
# ---------------------------------------------------------------------------

def write_pdf_tags(input_path, output_path, structured_data, filename):
    """Write PDF/UA structure tags with MCID content linkage using pikepdf."""
    pdf = pikepdf.Pdf.open(input_path)

    mark_info = pikepdf.Dictionary()
    mark_info["/Marked"] = True
    pdf.Root["/MarkInfo"] = mark_info

    for page in pdf.pages:
        page["/Tabs"] = pikepdf.Name.S

    struct_tree_root = pikepdf.Dictionary()
    struct_tree_root["/Type"] = pikepdf.Name.StructTreeRoot
    struct_tree_root["/RoleMap"] = pikepdf.Dictionary()

    doc_elem = pikepdf.Dictionary()
    doc_elem["/Type"] = pikepdf.Name.StructElem
    doc_elem["/S"] = pikepdf.Name.Document
    doc_elem["/P"] = pdf.make_indirect(struct_tree_root)

    doc_elem_ref = pdf.make_indirect(doc_elem)

    children = pikepdf.Array()

    # Global MCID counter and per-page parent tree tracking
    mcid_counter = 0
    # page_index -> list of struct element refs ordered by MCID
    page_parent_map = {}

    # Pre-process elements to group consecutive LI runs into L containers
    elements = structured_data.get("elements", [])
    processed_elements = _group_list_items(elements)

    # Track Figure struct element refs for pdf_obj_number mapping
    figure_obj_numbers = {}  # figure_index -> obj_number

    for elem in processed_elements:
        path = elem.get("Path", "")

        if "Artifact" in path:
            continue

        page_idx = elem.get("Page", 0)
        page_ref = pdf.pages[page_idx].obj if page_idx < len(pdf.pages) else None

        # Handle grouped list structure: L container with LI children
        if elem.get("_is_list_container"):
            l_elem = pikepdf.Dictionary()
            l_elem["/Type"] = pikepdf.Name.StructElem
            l_elem["/S"] = pikepdf.Name("/L")
            l_elem["/P"] = doc_elem_ref

            li_children = pikepdf.Array()
            for li_item in elem.get("_list_items", []):
                li_page_idx = li_item.get("Page", 0)
                li_page_ref = pdf.pages[li_page_idx].obj if li_page_idx < len(pdf.pages) else None

                li_elem = pikepdf.Dictionary()
                li_elem["/Type"] = pikepdf.Name.StructElem
                li_elem["/S"] = pikepdf.Name.LI
                li_elem["/P"] = pdf.make_indirect(l_elem)

                li_sub_children = pikepdf.Array()

                # Extract label (bullet/number) and body
                text = li_item.get("Text", "")
                label_match = re.match(r'^(\s*[\u2022\-\*]|\s*\d+[\.\)])\s*', text)
                if label_match:
                    label_text = label_match.group(0).strip()
                    body_text = text[label_match.end():]
                else:
                    label_text = ""
                    body_text = text

                # Lbl element
                if label_text:
                    lbl_elem = pikepdf.Dictionary()
                    lbl_elem["/Type"] = pikepdf.Name.StructElem
                    lbl_elem["/S"] = pikepdf.Name("/Lbl")
                    lbl_elem["/P"] = pdf.make_indirect(li_elem)
                    if li_page_ref is not None:
                        lbl_elem["/Pg"] = li_page_ref
                    lbl_elem["/K"] = pikepdf.Array([mcid_counter])
                    _register_mcid(page_parent_map, li_page_idx, mcid_counter, pdf.make_indirect(lbl_elem))
                    mcid_counter += 1
                    li_sub_children.append(pdf.make_indirect(lbl_elem))

                # LBody element
                lbody_elem = pikepdf.Dictionary()
                lbody_elem["/Type"] = pikepdf.Name.StructElem
                lbody_elem["/S"] = pikepdf.Name("/LBody")
                lbody_elem["/P"] = pdf.make_indirect(li_elem)
                if li_page_ref is not None:
                    lbody_elem["/Pg"] = li_page_ref
                lbody_elem["/K"] = pikepdf.Array([mcid_counter])
                # Language of parts on list body (Gap 5)
                if li_item.get("_lang"):
                    lbody_elem["/Lang"] = pikepdf.String(li_item["_lang"])
                _register_mcid(page_parent_map, li_page_idx, mcid_counter, pdf.make_indirect(lbody_elem))
                mcid_counter += 1
                li_sub_children.append(pdf.make_indirect(lbody_elem))

                li_elem["/K"] = li_sub_children
                li_children.append(pdf.make_indirect(li_elem))

            l_elem["/K"] = li_children
            children.append(pdf.make_indirect(l_elem))
            continue

        # Handle Table elements with parsed structure
        if "Table" in path and elem.get("_table_data"):
            table_ref = _build_table_structure(pdf, elem, doc_elem_ref, page_ref, page_idx,
                                                mcid_counter, page_parent_map)
            if table_ref is not None:
                children.append(table_ref)
                # Count MCIDs used by table
                table_data = elem["_table_data"]
                num_headers = len(table_data.get("headers", []))
                num_rows = len(table_data.get("rows", []))
                num_cells = num_headers + sum(len(r) for r in table_data.get("rows", []))
                mcid_counter += num_cells
                continue

        # Determine tag name
        tag_name = _resolve_tag_name(path)

        if tag_name == "LI":
            # Standalone LI (shouldn't happen after grouping, but handle gracefully)
            tag_name = "P"

        struct_elem = pikepdf.Dictionary()
        struct_elem["/Type"] = pikepdf.Name.StructElem
        struct_elem["/S"] = pikepdf.Name(f"/{tag_name}")
        struct_elem["/P"] = doc_elem_ref

        # Add page reference and MCID
        if page_ref is not None:
            struct_elem["/Pg"] = page_ref
        struct_elem["/K"] = pikepdf.Array([mcid_counter])

        if tag_name == "Figure" and "Alt" in elem:
            struct_elem["/Alt"] = pikepdf.String(elem["Alt"])

        # Language of parts (Gap 5)
        if elem.get("_lang"):
            struct_elem["/Lang"] = pikepdf.String(elem["_lang"])

        # Symbolic font ActualText (Gap 12)
        if elem.get("_actual_text"):
            struct_elem["/ActualText"] = pikepdf.String(elem["_actual_text"])

        ref = pdf.make_indirect(struct_elem)
        _register_mcid(page_parent_map, page_idx, mcid_counter, ref)
        mcid_counter += 1

        # Track Figure element refs for obj_number mapping
        if tag_name == "Figure":
            fig_idx = elem.get("_figure_index")
            if fig_idx is not None:
                figure_obj_numbers[fig_idx] = ref

        children.append(ref)

    doc_elem["/K"] = children
    struct_tree_root["/K"] = pikepdf.Array([doc_elem_ref])

    # Build ParentTree with real data
    parent_tree = pikepdf.Dictionary()
    parent_tree["/Type"] = pikepdf.Name("/NumberTree")
    nums_array = pikepdf.Array()
    for page_idx in sorted(page_parent_map.keys()):
        entries = page_parent_map[page_idx]
        nums_array.append(page_idx)
        refs_array = pikepdf.Array()
        for _mcid, ref in sorted(entries, key=lambda x: x[0]):
            refs_array.append(ref)
        nums_array.append(pdf.make_indirect(refs_array))
    parent_tree["/Nums"] = nums_array
    struct_tree_root["/ParentTree"] = pdf.make_indirect(parent_tree)
    struct_tree_root["/ParentTreeNextKey"] = len(pdf.pages)

    pdf.Root["/StructTreeRoot"] = pdf.make_indirect(struct_tree_root)

    # Tag non-Link/Widget annotations with /Contents (Gap 9)
    _tag_non_content_annotations(pdf, filename)

    # Write PDF/UA XMP metadata (Gap 3)
    _write_pdfua_xmp(pdf, filename)

    pdf.save(output_path)
    pdf.close()
    logging.info(f'Filename : {filename} | PDF/UA structure tags written with {mcid_counter} MCIDs to {output_path}')

    # Return figure obj numbers for downstream use
    return figure_obj_numbers


def _register_mcid(page_parent_map, page_idx, mcid, struct_ref):
    """Register a struct element reference in the per-page parent map."""
    if page_idx not in page_parent_map:
        page_parent_map[page_idx] = []
    page_parent_map[page_idx].append((mcid, struct_ref))


def _resolve_tag_name(path):
    """Resolve element path to a PDF tag name."""
    tag_map = {
        "H1": "H1", "H2": "H2", "H3": "H3", "H4": "H4", "H5": "H5", "H6": "H6",
        "P": "P", "Figure": "Figure", "Table": "Table",
        "L": "L", "LI": "LI", "Lbl": "Lbl", "LBody": "LBody",
    }
    for key in tag_map:
        if key in path:
            return tag_map[key]
    return "P"


def _group_list_items(elements):
    """Pre-process elements to wrap consecutive LI runs in L containers."""
    result = []
    li_run = []

    for elem in elements:
        path = elem.get("Path", "")
        is_li = "LI" in path and "Artifact" not in path

        if is_li:
            li_run.append(elem)
        else:
            if li_run:
                result.append({
                    "Path": "//Document/L",
                    "Page": li_run[0].get("Page", 0),
                    "_is_list_container": True,
                    "_list_items": list(li_run),
                })
                li_run = []
            result.append(elem)

    # Flush remaining LI run
    if li_run:
        result.append({
            "Path": "//Document/L",
            "Page": li_run[0].get("Page", 0),
            "_is_list_container": True,
            "_list_items": list(li_run),
        })

    return result


def _build_table_structure(pdf, elem, doc_elem_ref, page_ref, page_idx, mcid_start, page_parent_map):
    """Build a Table -> TR -> TH/TD structure tree from parsed table data."""
    table_data = elem.get("_table_data", {})
    headers = table_data.get("headers", [])
    rows = table_data.get("rows", [])

    if not headers and not rows:
        return None

    table_elem = pikepdf.Dictionary()
    table_elem["/Type"] = pikepdf.Name.StructElem
    table_elem["/S"] = pikepdf.Name("/Table")
    table_elem["/P"] = doc_elem_ref
    table_elem_ref = pdf.make_indirect(table_elem)

    tr_children = pikepdf.Array()
    mcid = mcid_start

    # Header row
    if headers:
        tr_elem = pikepdf.Dictionary()
        tr_elem["/Type"] = pikepdf.Name.StructElem
        tr_elem["/S"] = pikepdf.Name("/TR")
        tr_elem["/P"] = table_elem_ref

        th_children = pikepdf.Array()
        for header in headers:
            th_elem = pikepdf.Dictionary()
            th_elem["/Type"] = pikepdf.Name.StructElem
            th_elem["/S"] = pikepdf.Name("/TH")
            th_elem["/P"] = pdf.make_indirect(tr_elem)
            if page_ref is not None:
                th_elem["/Pg"] = page_ref
            th_elem["/K"] = pikepdf.Array([mcid])
            # Add Scope attribute
            scope_attr = pikepdf.Dictionary()
            scope_attr["/O"] = pikepdf.Name("/Table")
            scope_attr["/Scope"] = pikepdf.Name("/Column")
            th_elem["/A"] = scope_attr
            th_ref = pdf.make_indirect(th_elem)
            _register_mcid(page_parent_map, page_idx, mcid, th_ref)
            mcid += 1
            th_children.append(th_ref)

        tr_elem["/K"] = th_children
        tr_children.append(pdf.make_indirect(tr_elem))

    # Data rows
    for row in rows:
        tr_elem = pikepdf.Dictionary()
        tr_elem["/Type"] = pikepdf.Name.StructElem
        tr_elem["/S"] = pikepdf.Name("/TR")
        tr_elem["/P"] = table_elem_ref

        td_children = pikepdf.Array()
        for cell in row:
            td_elem = pikepdf.Dictionary()
            td_elem["/Type"] = pikepdf.Name.StructElem
            td_elem["/S"] = pikepdf.Name("/TD")
            td_elem["/P"] = pdf.make_indirect(tr_elem)
            if page_ref is not None:
                td_elem["/Pg"] = page_ref
            td_elem["/K"] = pikepdf.Array([mcid])
            td_ref = pdf.make_indirect(td_elem)
            _register_mcid(page_parent_map, page_idx, mcid, td_ref)
            mcid += 1
            td_children.append(td_ref)

        tr_elem["/K"] = td_children
        tr_children.append(pdf.make_indirect(tr_elem))

    table_elem["/K"] = tr_children
    return table_elem_ref


# ---------------------------------------------------------------------------
# PDF/UA XMP metadata (Gap 3)
# ---------------------------------------------------------------------------

def _write_pdfua_xmp(pdf, filename):
    """Write pdfuaid:part=1 into XMP metadata for PDF/UA compliance."""
    try:
        with pdf.open_metadata() as meta:
            meta["pdfuaid:part"] = "1"
        logging.info(f'Filename : {filename} | PDF/UA XMP metadata written (pdfuaid:part=1)')
    except Exception as e:
        logging.warning(f'Filename : {filename} | Failed to write PDF/UA XMP: {e}')


# ---------------------------------------------------------------------------
# Annotation tagging (Gap 9)
# ---------------------------------------------------------------------------

def _tag_non_content_annotations(pdf, filename):
    """Add /Contents descriptions to non-Link/Widget annotations for PDF/UA."""
    ANNOTATION_DESCRIPTIONS = {
        "/Text": "Text annotation",
        "/FreeText": "Free text annotation",
        "/Line": "Line annotation",
        "/Square": "Square annotation",
        "/Circle": "Circle annotation",
        "/Polygon": "Polygon annotation",
        "/PolyLine": "Polyline annotation",
        "/Highlight": "Highlight annotation",
        "/Underline": "Underline annotation",
        "/Squiggly": "Squiggly annotation",
        "/StrikeOut": "Strikeout annotation",
        "/Stamp": "Stamp annotation",
        "/Caret": "Caret annotation",
        "/Ink": "Ink annotation",
        "/Popup": "Popup annotation",
        "/FileAttachment": "File attachment annotation",
        "/Sound": "Sound annotation",
        "/Movie": "Movie annotation",
        "/Screen": "Screen annotation",
        "/PrinterMark": "Printer mark annotation",
        "/TrapNet": "Trap network annotation",
        "/Watermark": "Watermark annotation",
        "/3D": "3D annotation",
    }
    count = 0
    for page in pdf.pages:
        annots = page.get(pikepdf.Name.Annots)
        if not annots:
            continue
        for annot in annots:
            try:
                subtype = annot.get(pikepdf.Name.Subtype)
                if subtype in (pikepdf.Name.Link, pikepdf.Name("/Widget")):
                    continue
                contents = annot.get(pikepdf.Name.Contents)
                if contents and str(contents).strip():
                    continue
                # Add description based on annotation subtype
                subtype_str = str(subtype) if subtype else "/Unknown"
                desc = ANNOTATION_DESCRIPTIONS.get(subtype_str, f"{subtype_str.lstrip('/')} annotation")
                annot["/Contents"] = pikepdf.String(desc)
                count += 1
            except Exception:
                continue
    if count > 0:
        logging.info(f'Filename : {filename} | Tagged {count} non-content annotations with /Contents')


# ---------------------------------------------------------------------------
# Language of parts detection (Gap 5)
# ---------------------------------------------------------------------------

def _detect_per_element_languages(elements, doc_lang, filename):
    """Detect per-element languages using Comprehend for text blocks that differ from doc language."""
    comprehend = boto3.client('comprehend')
    detected_count = 0

    for elem in elements:
        text = elem.get("Text", "")
        if len(text.strip()) < 20:
            continue
        if "Artifact" in elem.get("Path", ""):
            continue
        if "Figure" in elem.get("Path", ""):
            continue

        try:
            truncated = text[:500]
            response = comprehend.detect_dominant_language(Text=truncated)
            languages = response.get('Languages', [])
            if not languages:
                continue
            top = max(languages, key=lambda l: l['Score'])
            if top['Score'] > 0.8 and top['LanguageCode'] != doc_lang:
                elem["_lang"] = top['LanguageCode']
                detected_count += 1
        except Exception:
            continue

    logging.info(f'Filename : {filename} | Detected {detected_count} elements with non-primary language')


# ---------------------------------------------------------------------------
# Symbolic font ActualText (Gap 12)
# ---------------------------------------------------------------------------

SYMBOLIC_FONT_PATTERNS = ("symbol", "wingding", "zapfdingbat", "webding", "dingbat")


def _detect_symbolic_fonts_in_elements(elements, pdf_path):
    """Flag text elements that use symbolic fonts."""
    doc = pymupdf.open(pdf_path)
    count = 0

    for elem in elements:
        if elem.get("Text") and elem.get("Page") is not None:
            page_num = elem["Page"]
            if page_num >= len(doc):
                continue
            page = doc[page_num]
            blocks = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
            for block in blocks.get("blocks", []):
                if block["type"] != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        font_name = span.get("font", "").lower()
                        if any(pat in font_name for pat in SYMBOLIC_FONT_PATTERNS):
                            if span["text"].strip():
                                elem["_is_symbolic"] = True
                                count += 1
                                break
                    if elem.get("_is_symbolic"):
                        break
                if elem.get("_is_symbolic"):
                    break

    doc.close()
    logging.info(f'Detected {count} elements with symbolic fonts')
    return count


def _generate_actual_text_for_symbols(elements, filename):
    """Use text model to interpret symbolic font characters."""
    bedrock_client = BedrockModelClient(model_type="text")
    count = 0

    for elem in elements:
        if not elem.get("_is_symbolic"):
            continue
        text = elem.get("Text", "").strip()
        if not text:
            continue

        try:
            prompt = f"""The following characters are from a symbolic font (like Wingdings, Symbol, or ZapfDingbats).
Provide the plain-text meaning of each character. If it's a common symbol, describe it concisely.

Characters: {text[:100]}

Return ONLY the plain-text equivalent, nothing else. For example:
- A checkmark symbol → "Checkmark"
- A bullet point → "Bullet"
- An arrow → "Right arrow"
"""
            response = bedrock_client.invoke(
                prompt,
                system_prompt="You interpret symbolic font characters into their plain-text equivalents for accessibility.",
                max_tokens=200,
                temperature=0.1,
            )
            if response and response.strip():
                elem["_actual_text"] = response.strip()
                count += 1
        except Exception as e:
            logging.warning(f'Filename : {filename} | Failed to generate ActualText for symbol: {e}')

    logging.info(f'Filename : {filename} | Generated ActualText for {count} symbolic elements')


# ---------------------------------------------------------------------------
# SQLite DB creation for alt-text generator
# ---------------------------------------------------------------------------

def create_sqlite_db(structured_data, filename, images_output_dir, bucket_name, s3_folder_autotag, file_key, figure_obj_numbers=None):
    """Create SQLite DB with image context data for the alt-text generator."""
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
            context TEXT,
            pdf_obj_number INTEGER
        )
    """)

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
        objid = str(figure_idx)

        # Get the PDF object number from the structure tree if available
        pdf_obj_num = None
        if figure_obj_numbers:
            fig_ref = figure_obj_numbers.get(figure_idx)
            if fig_ref is not None:
                try:
                    pdf_obj_num = fig_ref.objgen[0]
                except Exception:
                    pass

        cursor.execute("""
            INSERT INTO image_data (objid, img_path, context, pdf_obj_number)
            VALUES (?, ?, ?, ?)
        """, (objid, img_file, context, pdf_obj_num))

        img_local_path = elem["filePaths"][0]
        if os.path.exists(img_local_path):
            s3.upload_file(
                img_local_path, bucket_name,
                f'{s3_folder_autotag}/images/{file_key}_{img_file}'
            )

        figure_idx += 1

    conn.commit()
    conn.close()
    logging.info(f'Filename : {filename} | SQLite DB created with {figure_idx} images')

    s3.upload_file(db_path, bucket_name, f'{s3_folder_autotag}/{file_key}_temp_images_data.db')
    logging.info(f'Filename : {filename} | Uploaded SQLite DB to S3')


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    """
    Lambda entry point. Expects event with:
        s3_bucket: str - S3 bucket name
        s3_key: str    - S3 key path (e.g., "temp/<basename>/<file_key>")
        chunk_key: str - Chunk key identifier
    Returns:
        dict with s3_bucket, s3_key, chunk_key for downstream steps.
    """
    file_key = None
    file_base_name = None

    try:
        bucket_name = event['s3_bucket']
        s3_file_key = event['s3_key']

        file_key = s3_file_key.split('/')[2]
        file_base_name = s3_file_key.split('/')[1]
        logging.info(f'Filename : {file_key} | Bucket Name: {bucket_name}')

        local_file_path = os.path.join(WORK_DIR, os.path.basename(file_key))
        logging.info(f'Filename : {file_key} | Downloading file from S3...')
        download_file_from_s3(bucket_name, file_base_name, file_key, local_file_path)

        base_filename = os.path.basename(local_file_path)
        filename = os.path.join(WORK_DIR, "COMPLIANT_" + base_filename)

        # Add viewer preferences
        logging.info(f'Filename : {file_key} | Adding viewer preferences...')
        add_viewer_preferences(local_file_path, filename)

        # Phase A: Extract PDF content using PyMuPDF
        logging.info(f'Filename : {file_key} | Phase A: Extracting PDF content...')
        structured_data = extract_pdf_content(filename, file_key)

        # Phase B: LLM structure classification (includes table parsing)
        logging.info(f'Filename : {file_key} | Phase B: Running LLM structure analysis...')
        structured_data = run_llm_classification(filename, structured_data, file_key)

        # Assign figure indices for obj_number tracking
        fig_idx = 0
        for elem in structured_data["elements"]:
            if "Figure" in elem.get("Path", "") and "filePaths" in elem and elem["filePaths"]:
                elem["_figure_index"] = fig_idx
                fig_idx += 1

        # Detect document language early for per-element language detection (Gap 5)
        logging.info(f'Filename : {file_key} | Detecting document language...')
        all_text = " ".join(e.get("Text", "") for e in structured_data["elements"] if e.get("Text"))
        # Use a temporary PyMuPDF doc to detect language early
        temp_doc = pymupdf.open(filename)
        doc_lang = set_language_comprehend(file_key, all_text, temp_doc)
        temp_doc.saveIncr()
        temp_doc.close()

        # Detect per-element languages (Gap 5)
        logging.info(f'Filename : {file_key} | Detecting per-element languages...')
        _detect_per_element_languages(structured_data["elements"], doc_lang, file_key)

        # Generate ActualText for symbolic font elements (Gap 12)
        symbolic_count = sum(1 for e in structured_data["elements"] if e.get("_is_symbolic"))
        if symbolic_count > 0:
            logging.info(f'Filename : {file_key} | Generating ActualText for {symbolic_count} symbolic elements...')
            _generate_actual_text_for_symbols(structured_data["elements"], file_key)

        # Save structured data for downstream use
        zipfile_dir = os.path.join(WORK_DIR, "output", "zipfile")
        os.makedirs(zipfile_dir, exist_ok=True)
        structured_data_path = os.path.join(zipfile_dir, "structuredData.json")
        clean_data = {"elements": []}
        for elem in structured_data["elements"]:
            clean_elem = {k: v for k, v in elem.items() if not k.startswith("_")}
            clean_data["elements"].append(clean_elem)
        with open(structured_data_path, "w") as f:
            json.dump(clean_data, f, indent=2)

        # Phase C: Write PDF/UA tags using pikepdf (with MCID linkage)
        logging.info(f'Filename : {file_key} | Phase C: Writing PDF/UA structure tags...')
        tagged_path = os.path.join(WORK_DIR, "tagged_COMPLIANT_" + base_filename)
        figure_obj_numbers = write_pdf_tags(filename, tagged_path, structured_data, file_key)

        # Open tagged PDF with PyMuPDF for TOC and font subsetting
        pdf_document = pymupdf.open(tagged_path)

        # Add TOC
        logging.info(f'Filename : {file_key} | Adding TOC entries...')
        add_toc_to_pdf(file_key, pdf_document, clean_data)

        # Subset and embed fonts + generate /ToUnicode CMaps (Gaps 10, 11)
        logging.info(f'Filename : {file_key} | Subsetting and embedding fonts...')
        pdf_document.subset_fonts(fallback=True)

        pdf_document.saveIncr()
        pdf_document.close()

        # Upload tagged PDF to S3
        logging.info(f'Filename : {file_key} | Uploading processed PDF to S3...')
        save_to_s3(tagged_path, bucket_name, "output_autotag", file_base_name, file_key)

        logging.info(f"PDF saved with tags, metadata, and TOC. File location: COMPLIANT_{file_key}")

        # Create SQLite DB and upload images for alt-text generator
        images_output_dir = os.path.join(WORK_DIR, "output", "images")
        os.makedirs(images_output_dir, exist_ok=True)
        s3_folder_autotag = f"temp/{file_base_name}/output_autotag"

        logging.info(f'Filename : {file_key} | Creating image context DB...')
        create_sqlite_db(structured_data, file_key, images_output_dir, bucket_name, s3_folder_autotag, file_key, figure_obj_numbers)

        logging.info(f'Filename : {file_key} | Processing completed successfully')
        logger.info(f"File: {file_base_name}, Status: Succeeded in AI Tagger Lambda")

        return {
            "s3_bucket": bucket_name,
            "s3_key": s3_file_key,
            "chunk_key": event.get("chunk_key", ""),
        }

    except Exception as e:
        logger.error(f"File: {file_base_name}, Status: Failed in AI Tagger Lambda")
        logger.error(f"Filename : {file_key} | Error: {e}")
        import traceback
        traceback.print_exc()
        raise
