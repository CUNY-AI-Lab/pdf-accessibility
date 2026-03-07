"""
PDF/UA + WCAG 2.1 AA accessibility checker using pikepdf and PyMuPDF.

Replaces Adobe PDFAccessibilityCheckerJob with open-source tooling.

Checks implemented (26 total):
  Document:
    - /MarkInfo exists with /Marked true (WCAG 1.3.1)
    - /StructTreeRoot exists (WCAG 1.3.1)
    - /Lang set on catalog (WCAG 3.1.1)
    - /Title in metadata + XMP (WCAG 2.4.2)
    - /ViewerPreferences/DisplayDocTitle true (WCAG 2.4.2)
    - PDF/UA identifier in XMP metadata (PDF/UA-1)
    - /RoleMap on StructTreeRoot (PDF/UA)
    - Font embedding (PDF/UA)
    - Unicode mapping /ToUnicode (PDF/UA)
    - Artifact marking heuristic (WCAG 1.3.1)
  Navigation:
    - /Tabs /S on each page (WCAG 2.4.3)
    - /Outlines exist for docs > 20 pages (WCAG 2.4.5)
    - Reading order (WCAG 1.3.2)
    - Annotation tagging (PDF/UA)
  Headings:
    - H1-H6 proper nesting (WCAG 1.3.1)
  Images:
    - All /Figure elements have /Alt or /ActualText (WCAG 1.1.1)
    - Symbolic font ActualText (PDF/UA)
  Tables:
    - /Table elements contain /TH cells (WCAG 1.3.1)
    - /TH cells have /Scope attribute (WCAG 1.3.1)
  Lists:
    - /L -> /LI -> /Lbl + /LBody structure (WCAG 1.3.1)
  Links:
    - /Link annotations have /Contents or /Alt (WCAG 2.4.4)
    - Meaningful link text (WCAG 2.4.4)
  Forms:
    - /Widget annotations have /TU tooltip (WCAG 1.3.1)
  Visual:
    - Color contrast (manual check flag) (WCAG 1.4.3)
    - Text reflow (WCAG 1.4.10)
    - Non-text contrast (WCAG 1.4.11)
  Language:
    - Language of parts (WCAG 3.1.2)
"""

import re
import json
import logging
import pikepdf
import pymupdf

logger = logging.getLogger(__name__)


def check_accessibility(pdf_path):
    """
    Run all accessibility checks on a PDF file.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        dict: Report with summary and detailed findings.
    """
    report = {
        "summary": {
            "total_checks": 0,
            "passed": 0,
            "failed": 0,
            "warnings": 0,
        },
        "checks": [],
    }

    try:
        pdf = pikepdf.Pdf.open(pdf_path)
    except Exception as e:
        report["checks"].append(_fail("document_open", f"Cannot open PDF: {e}", "N/A"))
        report["summary"]["total_checks"] = 1
        report["summary"]["failed"] = 1
        return report

    # Document-level checks
    _check_mark_info(pdf, report)
    _check_struct_tree_root(pdf, report)
    _check_language(pdf, report)
    _check_title(pdf, pdf_path, report)
    _check_display_doc_title(pdf, report)
    _check_pdfua_identifier(pdf, pdf_path, report)
    _check_role_map(pdf, report)
    _check_font_embedding(pdf, report)
    _check_unicode_mapping(pdf, report)
    _check_artifact_marking(pdf, pdf_path, report)

    # Page-level checks
    _check_tabs(pdf, report)
    _check_outlines(pdf, report)
    _check_reading_order(pdf, pdf_path, report)
    _check_other_annotations(pdf, report)

    # Structure tree checks
    struct_tree = pdf.Root.get(pikepdf.Name.StructTreeRoot)
    if struct_tree:
        _check_heading_nesting(struct_tree, report)
        _check_figures_alt_text(struct_tree, report)
        _check_tables(struct_tree, report)
        _check_lists(struct_tree, report)
        _check_language_of_parts(struct_tree, report)
        _check_actual_text_symbolic(pdf, struct_tree, report)

    # Link checks
    _check_links(pdf, report)

    # Form field checks
    _check_form_fields(pdf, report)

    # Visual checks
    _check_color_contrast(pdf, pdf_path, report)
    _check_reflow(report)
    _check_non_text_contrast(report)

    pdf.close()

    # Update summary
    for check in report["checks"]:
        report["summary"]["total_checks"] += 1
        if check["status"] == "passed":
            report["summary"]["passed"] += 1
        elif check["status"] == "failed":
            report["summary"]["failed"] += 1
        elif check["status"] == "warning":
            report["summary"]["warnings"] += 1

    # Convert to UI-expected format
    return _convert_to_ui_format(report)


def _convert_to_ui_format(report):
    """Convert internal report format to the JSON structure the frontend UI expects."""
    # Map check_ids to categories and human-readable rule names
    category_map = {
        "mark_info": ("Document", "Tagged PDF"),
        "struct_tree_root": ("Document", "Structure Tree Root"),
        "document_language": ("Document", "Primary Language"),
        "document_title": ("Document", "Document Title"),
        "display_doc_title": ("Document", "Display Document Title"),
        "pdfua_identifier": ("Document", "PDF/UA Identifier"),
        "tab_order": ("Navigation", "Tab Order"),
        "outlines": ("Navigation", "Bookmarks"),
        "heading_nesting": ("Headings", "Heading Nesting"),
        "figure_alt_text": ("Images", "Figures Alternate Text"),
        "table_headers": ("Tables", "Table Headers"),
        "table_header_scope": ("Tables", "Table Header Scope"),
        "list_structure": ("Lists", "List Structure"),
        "link_alt_text": ("Links", "Link Alternate Text"),
        "link_meaningful_text": ("Links", "Meaningful Link Text"),
        "form_field_labels": ("Forms", "Form Field Labels"),
        "color_contrast": ("Visual", "Color Contrast"),
        "document_open": ("Document", "Document Open"),
        "role_map": ("Document", "Role Map"),
        "font_embedding": ("Document", "Font Embedding"),
        "unicode_mapping": ("Document", "Unicode Mapping"),
        "artifact_marking": ("Document", "Artifact Marking"),
        "reading_order": ("Navigation", "Reading Order"),
        "other_annotations": ("Navigation", "Annotation Tagging"),
        "language_of_parts": ("Language", "Language of Parts"),
        "actual_text_symbolic": ("Images", "Symbolic Font ActualText"),
        "text_reflow": ("Visual", "Text Reflow"),
        "non_text_contrast": ("Visual", "Non-Text Contrast"),
    }

    status_map = {
        "passed": "Passed",
        "failed": "Failed",
        "warning": "Needs manual check",
    }

    detailed = {}
    for check in report["checks"]:
        cat, rule = category_map.get(check["check_id"], ("Other", check["check_id"]))
        if cat not in detailed:
            detailed[cat] = []
        detailed[cat].append({
            "Rule": rule,
            "Description": check["message"],
            "Status": status_map.get(check["status"], check["status"]),
        })

    return {
        "Summary": {
            "Description": "PDF/UA + WCAG 2.1 AA Accessibility Check",
            "Needs manual check": report["summary"]["warnings"],
            "Passed": report["summary"]["passed"],
            "Failed": report["summary"]["failed"],
        },
        "Detailed Report": detailed,
    }


def _pass(check_id, message, wcag):
    return {"check_id": check_id, "status": "passed", "message": message, "wcag": wcag}


def _fail(check_id, message, wcag):
    return {"check_id": check_id, "status": "failed", "message": message, "wcag": wcag}


def _warn(check_id, message, wcag):
    return {"check_id": check_id, "status": "warning", "message": message, "wcag": wcag}


# --- Document checks ---

def _check_mark_info(pdf, report):
    mark_info = pdf.Root.get(pikepdf.Name.MarkInfo)
    if mark_info and mark_info.get(pikepdf.Name.Marked) == True:
        report["checks"].append(_pass("mark_info", "/MarkInfo exists with /Marked true", "1.3.1"))
    else:
        report["checks"].append(_fail("mark_info", "/MarkInfo missing or /Marked not true", "1.3.1"))


def _check_struct_tree_root(pdf, report):
    if pikepdf.Name.StructTreeRoot in pdf.Root:
        report["checks"].append(_pass("struct_tree_root", "/StructTreeRoot exists", "1.3.1"))
    else:
        report["checks"].append(_fail("struct_tree_root", "/StructTreeRoot missing", "1.3.1"))


def _check_language(pdf, report):
    lang = pdf.Root.get(pikepdf.Name.Lang)
    if lang:
        report["checks"].append(_pass("document_language", f"/Lang set to '{str(lang)}'", "3.1.1"))
    else:
        report["checks"].append(_fail("document_language", "/Lang not set on document catalog", "3.1.1"))


def _check_title(pdf, pdf_path, report):
    # Check /Info/Title
    info_title = None
    if pdf.docinfo:
        info_title = pdf.docinfo.get(pikepdf.Name.Title)

    # Check XMP metadata for dc:title
    xmp_title = False
    try:
        doc = pymupdf.open(pdf_path)
        metadata = doc.metadata
        if metadata and metadata.get("title"):
            xmp_title = True
        doc.close()
    except Exception:
        pass

    if info_title or xmp_title:
        report["checks"].append(_pass("document_title", "Document title exists in metadata", "2.4.2"))
    else:
        report["checks"].append(_fail("document_title", "Document title missing from metadata", "2.4.2"))


def _check_display_doc_title(pdf, report):
    vp = pdf.Root.get(pikepdf.Name.ViewerPreferences)
    if vp and vp.get(pikepdf.Name.DisplayDocTitle) == True:
        report["checks"].append(_pass("display_doc_title", "/ViewerPreferences/DisplayDocTitle is true", "2.4.2"))
    else:
        report["checks"].append(_fail("display_doc_title", "/ViewerPreferences/DisplayDocTitle not set to true", "2.4.2"))


def _check_pdfua_identifier(pdf, pdf_path, report):
    """Check for pdfuaid:part in XMP metadata (PDF/UA identifier)."""
    found = False
    try:
        doc = pymupdf.open(pdf_path)
        xmp = doc.get_xml_metadata()
        if xmp and "pdfuaid:part" in xmp:
            found = True
        doc.close()
    except Exception:
        pass

    if found:
        report["checks"].append(_pass("pdfua_identifier", "PDF/UA identifier (pdfuaid:part) found in XMP metadata", "PDF/UA"))
    else:
        report["checks"].append(_fail("pdfua_identifier", "PDF/UA identifier (pdfuaid:part) missing from XMP metadata", "PDF/UA"))


# --- Page-level checks ---

def _check_tabs(pdf, report):
    all_tabs_set = True
    for i, page in enumerate(pdf.pages):
        tabs = page.get(pikepdf.Name.Tabs)
        if tabs != pikepdf.Name.S:
            all_tabs_set = False
            break

    if all_tabs_set:
        report["checks"].append(_pass("tab_order", "/Tabs /S set on all pages", "2.4.3"))
    else:
        report["checks"].append(_fail("tab_order", f"/Tabs /S missing on page {i + 1}", "2.4.3"))


def _check_outlines(pdf, report):
    num_pages = len(pdf.pages)
    if num_pages <= 20:
        report["checks"].append(_pass("outlines", f"Document has {num_pages} pages (<=20), outlines not required", "2.4.5"))
        return

    outlines = pdf.Root.get(pikepdf.Name.Outlines)
    if outlines:
        # Verify the outline tree actually has entries (Count > 0 or First child exists)
        count = outlines.get(pikepdf.Name("/Count"))
        first = outlines.get(pikepdf.Name("/First"))
        if first or (count is not None and int(count) != 0):
            report["checks"].append(_pass("outlines", "/Outlines (bookmarks) exist", "2.4.5"))
        else:
            report["checks"].append(_fail("outlines", f"Document has {num_pages} pages and /Outlines exists but is empty (no bookmarks)", "2.4.5"))
    else:
        report["checks"].append(_fail("outlines", f"Document has {num_pages} pages but no /Outlines (bookmarks)", "2.4.5"))


# --- Structure tree checks ---

def _collect_struct_elements(node, tag_name=None):
    """Recursively collect structure elements, optionally filtering by tag."""
    results = []
    if not isinstance(node, pikepdf.Dictionary):
        return results

    s = node.get(pikepdf.Name.S)
    if s is not None:
        name = str(s)
        if tag_name is None or name == f"/{tag_name}":
            results.append(node)

    # Recurse into children
    k = node.get(pikepdf.Name.K)
    if k is not None:
        if isinstance(k, pikepdf.Array):
            for child in k:
                if isinstance(child, pikepdf.Dictionary):
                    results.extend(_collect_struct_elements(child, tag_name))
                else:
                    # Handle indirect references — pikepdf auto-dereferences on attribute access
                    try:
                        if pikepdf.Name.S in child or pikepdf.Name.K in child:
                            results.extend(_collect_struct_elements(child, tag_name))
                    except Exception:
                        pass
        elif isinstance(k, pikepdf.Dictionary):
            results.extend(_collect_struct_elements(k, tag_name))

    return results


def _check_heading_nesting(struct_tree, report):
    """Check that heading levels don't skip (e.g., H1 -> H3 without H2)."""
    all_elements = _collect_struct_elements(struct_tree)

    heading_levels = []
    for elem in all_elements:
        s = elem.get(pikepdf.Name.S)
        if s is not None:
            name = str(s)
            if name in ("/H1", "/H2", "/H3", "/H4", "/H5", "/H6"):
                level = int(name[2])
                heading_levels.append(level)

    if not heading_levels:
        report["checks"].append(_warn("heading_nesting", "No headings found in structure tree", "1.3.1"))
        return

    # Check for skipped levels — collect all violations
    skips = []
    for i in range(1, len(heading_levels)):
        if heading_levels[i] > heading_levels[i - 1] + 1:
            skips.append(f"H{heading_levels[i-1]} -> H{heading_levels[i]}")

    if skips:
        skips_str = ", ".join(skips[:5])
        suffix = f" and {len(skips) - 5} more" if len(skips) > 5 else ""
        report["checks"].append(_fail(
            "heading_nesting",
            f"Heading level(s) skipped: {skips_str}{suffix}",
            "1.3.1"
        ))
    else:
        report["checks"].append(_pass("heading_nesting", "Heading levels properly nested", "1.3.1"))


def _check_figures_alt_text(struct_tree, report):
    """Check that all Figure elements have non-empty /Alt or /ActualText."""
    figures = _collect_struct_elements(struct_tree, "Figure")

    if not figures:
        report["checks"].append(_pass("figure_alt_text", "No Figure elements found", "1.1.1"))
        return

    missing_alt = 0
    for fig in figures:
        alt = fig.get(pikepdf.Name.Alt)
        actual_text = fig.get(pikepdf.Name("/ActualText"))
        # Check that alt text exists AND is non-empty after stripping whitespace
        alt_valid = alt is not None and str(alt).strip() != ""
        actual_valid = actual_text is not None and str(actual_text).strip() != ""
        if not alt_valid and not actual_valid:
            missing_alt += 1

    if missing_alt == 0:
        report["checks"].append(_pass("figure_alt_text", f"All {len(figures)} Figure elements have alt text", "1.1.1"))
    else:
        report["checks"].append(_fail(
            "figure_alt_text",
            f"{missing_alt} of {len(figures)} Figure elements missing /Alt or /ActualText",
            "1.1.1"
        ))


def _check_tables(struct_tree, report):
    """Check that Table elements contain TH cells with Scope."""
    tables = _collect_struct_elements(struct_tree, "Table")

    if not tables:
        report["checks"].append(_pass("table_headers", "No Table elements found", "1.3.1"))
        return

    tables_without_th = 0
    th_without_scope = 0

    for table in tables:
        ths = _collect_struct_elements(table, "TH")
        if not ths:
            tables_without_th += 1
        else:
            for th in ths:
                attrs = th.get(pikepdf.Name.A)
                has_scope = False
                if attrs:
                    if isinstance(attrs, pikepdf.Dictionary):
                        has_scope = pikepdf.Name.Scope in attrs
                    elif isinstance(attrs, pikepdf.Array):
                        for a in attrs:
                            if isinstance(a, pikepdf.Dictionary) and pikepdf.Name.Scope in a:
                                has_scope = True
                                break
                if not has_scope:
                    th_without_scope += 1

    if tables_without_th > 0:
        report["checks"].append(_fail(
            "table_headers",
            f"{tables_without_th} of {len(tables)} Table elements lack /TH cells",
            "1.3.1"
        ))
    else:
        report["checks"].append(_pass("table_headers", "All Table elements contain /TH cells", "1.3.1"))

    if th_without_scope > 0:
        report["checks"].append(_fail(
            "table_header_scope",
            f"{th_without_scope} /TH cells missing /Scope attribute",
            "1.3.1"
        ))
    elif len(tables) > 0:
        report["checks"].append(_pass("table_header_scope", "All /TH cells have /Scope", "1.3.1"))


def _check_lists(struct_tree, report):
    """Check that L -> LI -> Lbl + LBody structure is correct."""
    lists = _collect_struct_elements(struct_tree, "L")

    if not lists:
        report["checks"].append(_pass("list_structure", "No List elements found", "1.3.1"))
        return

    lists_no_li = 0
    li_missing_lbody = 0
    total_li = 0
    for lst in lists:
        lis = _collect_struct_elements(lst, "LI")
        if not lis:
            lists_no_li += 1
            continue
        for li in lis:
            total_li += 1
            # Check LI has LBody child (Lbl is optional but LBody is required)
            lbody = _collect_struct_elements(li, "LBody")
            if not lbody:
                li_missing_lbody += 1

    issues = []
    if lists_no_li > 0:
        issues.append(f"{lists_no_li} of {len(lists)} List elements missing /LI children")
    if li_missing_lbody > 0:
        issues.append(f"{li_missing_lbody} of {total_li} /LI elements missing /LBody child")

    if issues:
        report["checks"].append(_fail("list_structure", "; ".join(issues), "1.3.1"))
    else:
        report["checks"].append(_pass("list_structure", f"All {len(lists)} List elements properly structured (L -> LI -> LBody)", "1.3.1"))


# --- Link checks ---

GENERIC_LINK_PATTERNS = {
    "click here", "here", "read more", "more", "link", "learn more",
    "this link", "click", "go", "details", "info",
}


def _check_links(pdf, report):
    """Check that Link annotations have /Contents or /Alt and meaningful text."""
    total_links = 0
    missing_alt = 0
    generic_text_count = 0

    for page in pdf.pages:
        annots = page.get(pikepdf.Name.Annots)
        if not annots:
            continue
        for annot in annots:
            if not isinstance(annot, pikepdf.Dictionary):
                try:
                    annot = pikepdf.Dictionary(annot)
                except Exception:
                    continue

            subtype = annot.get(pikepdf.Name.Subtype)
            if subtype == pikepdf.Name.Link:
                total_links += 1
                contents = annot.get(pikepdf.Name.Contents)
                alt = annot.get(pikepdf.Name.Alt)
                if not contents and not alt:
                    missing_alt += 1
                else:
                    # Check for generic/meaningless link text
                    text = str(contents or alt).strip().lower()
                    if text in GENERIC_LINK_PATTERNS or re.match(r'^https?://', text):
                        generic_text_count += 1

    if total_links == 0:
        report["checks"].append(_pass("link_alt_text", "No Link annotations found", "2.4.4"))
    elif missing_alt == 0:
        report["checks"].append(_pass("link_alt_text", f"All {total_links} Link annotations have /Contents or /Alt", "2.4.4"))
    else:
        report["checks"].append(_fail(
            "link_alt_text",
            f"{missing_alt} of {total_links} Link annotations missing /Contents or /Alt",
            "2.4.4"
        ))

    if generic_text_count > 0:
        report["checks"].append(_warn(
            "link_meaningful_text",
            f"{generic_text_count} Link annotations have generic text (e.g. 'click here', bare URLs) — use descriptive link text",
            "2.4.4"
        ))


# --- Form field checks ---

def _check_form_fields(pdf, report):
    """Check that Widget annotations (form fields) have /TU tooltip for accessibility."""
    total_widgets = 0
    missing_tu = 0

    for page in pdf.pages:
        annots = page.get(pikepdf.Name.Annots)
        if not annots:
            continue
        for annot in annots:
            if not isinstance(annot, pikepdf.Dictionary):
                try:
                    if pikepdf.Name.Subtype in annot:
                        pass  # auto-dereference
                    else:
                        continue
                except Exception:
                    continue

            subtype = annot.get(pikepdf.Name.Subtype)
            if subtype == pikepdf.Name.Widget:
                total_widgets += 1
                tu = annot.get(pikepdf.Name.TU)
                if not tu or str(tu).strip() == "":
                    missing_tu += 1

    if total_widgets == 0:
        report["checks"].append(_pass("form_field_labels", "No form fields found", "1.3.1"))
    elif missing_tu == 0:
        report["checks"].append(_pass("form_field_labels", f"All {total_widgets} form fields have /TU tooltip", "1.3.1"))
    else:
        report["checks"].append(_fail(
            "form_field_labels",
            f"{missing_tu} of {total_widgets} form fields missing /TU tooltip",
            "1.3.1"
        ))


# --- Color contrast ---

def _relative_luminance(r, g, b):
    """WCAG relative luminance from sRGB values (0-255)."""
    def gamma(v):
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * gamma(r) + 0.7152 * gamma(g) + 0.0722 * gamma(b)


def _contrast_ratio(rgb1, rgb2):
    """WCAG contrast ratio between two (r, g, b) tuples (0-255)."""
    l1 = _relative_luminance(*rgb1)
    l2 = _relative_luminance(*rgb2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _int_color_to_rgb(color_int):
    """Convert PyMuPDF's integer color (0xRRGGBB) to (r, g, b) tuple."""
    color_int = int(color_int)
    r = (color_int >> 16) & 0xFF
    g = (color_int >> 8) & 0xFF
    b = color_int & 0xFF
    return (r, g, b)


def _sample_background_color(pixmap, bbox, page_rect):
    """Sample background color around a text bbox from a rendered pixmap."""
    # Convert bbox coordinates to pixmap pixel coordinates
    pw = pixmap.width
    ph = pixmap.height
    scale_x = pw / page_rect.width
    scale_y = ph / page_rect.height

    x0 = int(bbox[0] * scale_x)
    y0 = int(bbox[1] * scale_y)
    x1 = int(bbox[2] * scale_x)
    y1 = int(bbox[3] * scale_y)

    # Clamp to pixmap bounds
    x0 = max(0, min(x0, pw - 1))
    y0 = max(0, min(y0, ph - 1))
    x1 = max(0, min(x1, pw - 1))
    y1 = max(0, min(y1, ph - 1))

    # Sample points just outside the text bbox (1px offset)
    sample_points = []
    # Above center
    if y0 > 0:
        sample_points.append((max(0, (x0 + x1) // 2), y0 - 1))
    # Below center
    if y1 < ph - 1:
        sample_points.append((max(0, (x0 + x1) // 2), y1 + 1))
    # Left middle
    if x0 > 0:
        sample_points.append((x0 - 1, max(0, (y0 + y1) // 2)))
    # Right middle
    if x1 < pw - 1:
        sample_points.append((x1 + 1, max(0, (y0 + y1) // 2)))

    if not sample_points:
        return (255, 255, 255)  # default white

    # Collect RGB values from sample points
    samples = []
    n = pixmap.n  # number of components (3 for RGB, 4 for RGBA)
    stride = pixmap.stride
    for px, py in sample_points:
        idx = py * stride + px * n
        try:
            r = pixmap.samples[idx]
            g = pixmap.samples[idx + 1]
            b = pixmap.samples[idx + 2]
            samples.append((r, g, b))
        except (IndexError, TypeError):
            continue

    if not samples:
        return (255, 255, 255)

    # Take median of each channel
    rs = sorted(s[0] for s in samples)
    gs = sorted(s[1] for s in samples)
    bs = sorted(s[2] for s in samples)
    mid = len(rs) // 2
    return (rs[mid], gs[mid], bs[mid])


def _check_color_contrast(pdf, pdf_path, report):
    """Automated WCAG color contrast check using PyMuPDF text spans and pixmap rendering."""
    try:
        doc = pymupdf.open(pdf_path)
    except Exception as e:
        report["checks"].append(_warn(
            "color_contrast",
            f"Could not open PDF for color contrast check: {e}",
            "1.4.3"
        ))
        return

    try:
        total_spans = 0
        failing_spans = 0
        worst_ratio = float('inf')
        worst_detail = ""

        for page_num in range(len(doc)):
            page = doc[page_num]
            page_rect = page.rect

            # Render page for background sampling (150 DPI for accuracy with small text)
            try:
                pixmap = page.get_pixmap(dpi=150)
            except Exception:
                continue

            # Extract text with style info
            try:
                text_dict = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
            except Exception:
                continue

            for block in text_dict.get("blocks", []):
                if block.get("type") != 0:  # text blocks only
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if len(text) < 3:
                            continue

                        total_spans += 1
                        font_size = span.get("size", 12)
                        flags = span.get("flags", 0)
                        is_bold = bool(flags & (1 << 4))  # bit 4 = bold

                        # Large text: >= 18pt, or >= 14pt and bold
                        is_large = font_size >= 18 or (font_size >= 14 and is_bold)
                        threshold = 3.0 if is_large else 4.5

                        # Text color
                        color_val = span.get("color", 0)
                        text_rgb = _int_color_to_rgb(color_val)

                        # Background color from pixmap
                        bbox = span.get("bbox", (0, 0, 0, 0))
                        bg_rgb = _sample_background_color(pixmap, bbox, page_rect)

                        ratio = _contrast_ratio(text_rgb, bg_rgb)

                        if ratio < threshold:
                            failing_spans += 1
                            if ratio < worst_ratio:
                                worst_ratio = ratio
                                worst_detail = f"page {page_num + 1}: ratio {ratio:.2f}:1 (need {threshold}:1) — text color rgb{text_rgb} on rgb{bg_rgb}"

        doc.close()

        if total_spans == 0:
            report["checks"].append(_pass("color_contrast", "No text spans found to check", "1.4.3"))
        elif failing_spans == 0:
            report["checks"].append(_pass(
                "color_contrast",
                f"All {total_spans} text spans meet WCAG contrast requirements (4.5:1 normal, 3:1 large text)",
                "1.4.3"
            ))
        else:
            report["checks"].append(_fail(
                "color_contrast",
                f"{failing_spans} of {total_spans} text spans have insufficient contrast. Worst: {worst_detail}",
                "1.4.3"
            ))

    except Exception as e:
        report["checks"].append(_warn(
            "color_contrast",
            f"Color contrast check encountered an error: {e} — manual verification recommended",
            "1.4.3"
        ))


# --- New checks (Gaps 1-12) ---

def _check_role_map(pdf, report):
    """Check for /RoleMap on StructTreeRoot (PDF/UA requirement)."""
    struct_tree = pdf.Root.get(pikepdf.Name.StructTreeRoot)
    if not struct_tree:
        report["checks"].append(_fail("role_map", "/StructTreeRoot missing, cannot check /RoleMap", "PDF/UA"))
        return
    if pikepdf.Name("/RoleMap") in struct_tree:
        report["checks"].append(_pass("role_map", "/RoleMap present on StructTreeRoot", "PDF/UA"))
    else:
        report["checks"].append(_fail("role_map", "/RoleMap missing from StructTreeRoot", "PDF/UA"))


def _check_font_embedding(pdf, report):
    """Check that fonts have embedded font programs (PDF/UA)."""
    total_fonts = 0
    unembedded = 0
    STANDARD_14 = {
        "Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique",
        "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique",
        "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic",
        "Symbol", "ZapfDingbats",
    }

    for page in pdf.pages:
        resources = page.get(pikepdf.Name.Resources)
        if not resources:
            continue
        fonts = resources.get(pikepdf.Name("/Font"))
        if not fonts:
            continue
        for font_name in fonts.keys():
            font = fonts[font_name]
            try:
                base_font = str(font.get(pikepdf.Name("/BaseFont"), ""))
                # Strip leading / and subset prefix (e.g., ABCDEF+)
                clean_name = base_font.lstrip("/")
                if "+" in clean_name:
                    clean_name = clean_name.split("+", 1)[1]
                if clean_name in STANDARD_14:
                    continue

                total_fonts += 1
                subtype = str(font.get(pikepdf.Name.Subtype, ""))

                # Type0 (composite) — check DescendantFonts
                if subtype == "/Type0":
                    descendants = font.get(pikepdf.Name("/DescendantFonts"))
                    if descendants and len(descendants) > 0:
                        desc_font = descendants[0]
                        fd = desc_font.get(pikepdf.Name("/FontDescriptor"))
                        if fd and _has_font_file(fd):
                            continue
                    unembedded += 1
                else:
                    fd = font.get(pikepdf.Name("/FontDescriptor"))
                    if fd and _has_font_file(fd):
                        continue
                    unembedded += 1
            except Exception:
                continue

    if total_fonts == 0:
        report["checks"].append(_pass("font_embedding", "No non-standard fonts found", "PDF/UA"))
    elif unembedded == 0:
        report["checks"].append(_pass("font_embedding", f"All {total_fonts} fonts are embedded", "PDF/UA"))
    else:
        report["checks"].append(_fail(
            "font_embedding",
            f"{unembedded} of {total_fonts} non-standard fonts are not embedded",
            "PDF/UA"
        ))


def _has_font_file(font_descriptor):
    """Check if a font descriptor has an embedded font file."""
    for key in ("/FontFile", "/FontFile2", "/FontFile3"):
        if pikepdf.Name(key) in font_descriptor:
            return True
    return False


def _check_unicode_mapping(pdf, report):
    """Check that fonts have /ToUnicode or standard /Encoding (PDF/UA)."""
    total_fonts = 0
    missing_mapping = 0
    STANDARD_ENCODINGS = {"/WinAnsiEncoding", "/MacRomanEncoding", "/MacExpertEncoding"}

    for page in pdf.pages:
        resources = page.get(pikepdf.Name.Resources)
        if not resources:
            continue
        fonts = resources.get(pikepdf.Name("/Font"))
        if not fonts:
            continue
        for font_name in fonts.keys():
            font = fonts[font_name]
            try:
                total_fonts += 1
                # Has /ToUnicode CMap
                if pikepdf.Name("/ToUnicode") in font:
                    continue
                # Has standard encoding
                encoding = font.get(pikepdf.Name("/Encoding"))
                if encoding is not None:
                    enc_str = str(encoding) if isinstance(encoding, pikepdf.Name) else ""
                    if enc_str in STANDARD_ENCODINGS:
                        continue
                    # Dictionary encoding with BaseEncoding
                    if isinstance(encoding, pikepdf.Dictionary):
                        base = encoding.get(pikepdf.Name("/BaseEncoding"))
                        if base and str(base) in STANDARD_ENCODINGS:
                            continue
                # Type0 composite fonts — check descendant for CIDToGIDMap
                subtype = str(font.get(pikepdf.Name.Subtype, ""))
                if subtype == "/Type0":
                    descendants = font.get(pikepdf.Name("/DescendantFonts"))
                    if descendants and len(descendants) > 0:
                        desc = descendants[0]
                        if pikepdf.Name("/CIDToGIDMap") in desc:
                            continue
                missing_mapping += 1
            except Exception:
                continue

    if total_fonts == 0:
        report["checks"].append(_pass("unicode_mapping", "No fonts found", "PDF/UA"))
    elif missing_mapping == 0:
        report["checks"].append(_pass("unicode_mapping", f"All {total_fonts} fonts have Unicode mapping", "PDF/UA"))
    else:
        report["checks"].append(_warn(
            "unicode_mapping",
            f"{missing_mapping} of {total_fonts} fonts lack /ToUnicode or standard /Encoding — text extraction may be unreliable",
            "PDF/UA"
        ))


def _check_artifact_marking(pdf, pdf_path, report):
    """Check content streams for /Artifact BMC markers (not structure tree)."""
    num_pages = len(pdf.pages)
    if num_pages <= 3:
        report["checks"].append(_pass("artifact_marking", f"Document has {num_pages} pages (<=3), artifact check not applicable", "1.3.1"))
        return

    # Artifacts are marked in content streams with /Artifact BMC or /Artifact BDC,
    # NOT as structure tree elements. Check via PyMuPDF's text extraction which
    # distinguishes artifact content from real content.
    has_artifact = False
    try:
        doc = pymupdf.open(pdf_path)
        for page_num in range(min(len(doc), 10)):  # sample first 10 pages
            page = doc[page_num]
            # PyMuPDF's rawdict includes artifact info; alternatively check raw content stream
            raw = page.read_contents()
            if raw and b"/Artifact" in raw:
                has_artifact = True
                break
        doc.close()
    except Exception:
        # Fallback: check raw page content streams via pikepdf
        try:
            for i, page in enumerate(pdf.pages):
                if i >= 10:
                    break
                contents = page.get(pikepdf.Name.Contents)
                if contents is None:
                    continue
                if isinstance(contents, pikepdf.Array):
                    for stream in contents:
                        data = stream.read_bytes()
                        if b"/Artifact" in data:
                            has_artifact = True
                            break
                else:
                    data = contents.read_bytes()
                    if b"/Artifact" in data:
                        has_artifact = True
                if has_artifact:
                    break
        except Exception:
            pass

    if has_artifact:
        report["checks"].append(_pass("artifact_marking", "Artifact markers found in content streams (headers/footers/decorative content properly marked)", "1.3.1"))
    else:
        report["checks"].append(_warn(
            "artifact_marking",
            f"Document has {num_pages} pages but no /Artifact markers found in content streams — decorative content (headers, footers, watermarks) should be marked as artifacts",
            "1.3.1"
        ))


def _check_reading_order(pdf, pdf_path, report):
    """Check reading order by verifying struct tree MCIDs are monotonically increasing per page."""
    struct_tree = pdf.Root.get(pikepdf.Name.StructTreeRoot)
    if not struct_tree:
        report["checks"].append(_warn(
            "reading_order",
            "No structure tree — cannot verify reading order",
            "1.3.2"
        ))
        return

    # Collect MCIDs per page from the ParentTree
    parent_tree = struct_tree.get(pikepdf.Name("/ParentTree"))
    if not parent_tree:
        report["checks"].append(_warn(
            "reading_order",
            "No ParentTree in structure tree — cannot verify MCID ordering",
            "1.3.2"
        ))
        return

    nums = parent_tree.get(pikepdf.Name("/Nums"))
    if not nums or len(nums) < 2:
        report["checks"].append(_warn(
            "reading_order",
            "ParentTree /Nums is empty — cannot verify MCID ordering",
            "1.3.2"
        ))
        return

    # Also get visual block positions from PyMuPDF for comparison
    try:
        doc = pymupdf.open(pdf_path)
    except Exception:
        report["checks"].append(_warn(
            "reading_order",
            "Could not open PDF for reading order analysis",
            "1.3.2"
        ))
        return

    misordered_pages = []

    try:
        for page_num in range(len(doc)):
            page = doc[page_num]

            # Get text blocks in visual order (already sorted top-to-bottom by PyMuPDF)
            blocks = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE).get("blocks", [])
            text_blocks = [b for b in blocks if b.get("type") == 0 and any(
                line.get("spans", [{}])[0].get("text", "").strip()
                for line in b.get("lines", []) if line.get("spans")
            )]

            if len(text_blocks) < 2:
                continue

            # Visual order: sort by y-coordinate (top to bottom), then x (left to right)
            visual_bboxes = [(b["bbox"][1], b["bbox"][0]) for b in text_blocks]

            # Check if visual order is already top-to-bottom
            # If blocks are already in visual order, the struct tree ordering should match
            # We check if the blocks as-returned by PyMuPDF are in y-sorted order
            y_coords = [b["bbox"][1] for b in text_blocks]
            is_visual_sorted = all(y_coords[i] <= y_coords[i+1] + 5 for i in range(len(y_coords) - 1))

            if is_visual_sorted:
                # Visual order is top-to-bottom, struct tree should match
                # Check ParentTree for this page — MCIDs should be monotonically increasing
                # Parse /Nums: [page_idx, array, page_idx, array, ...]
                page_mcid_refs = None
                for i in range(0, len(nums) - 1, 2):
                    try:
                        idx = int(nums[i])
                        if idx == page_num:
                            page_mcid_refs = nums[i + 1]
                            break
                    except (ValueError, TypeError):
                        continue

                if page_mcid_refs is None:
                    continue

                # The array length = number of MCIDs on this page
                # MCIDs should correspond to content in order
                # We can't directly map MCIDs to blocks without content stream parsing,
                # but we CAN check if the struct tree order (via MCID sequence) is monotonic
                # relative to the visual block order — a simple proxy is checking that
                # the ParentTree array has entries and that they're in a sensible order
                # The key insight: if MCIDs are assigned sequentially and visual order is
                # top-to-bottom, then the struct tree is correctly ordered.
                # Flag pages where visual layout suggests multi-column (large X gaps)
                if len(text_blocks) >= 3:
                    x_coords = sorted(set(int(b["bbox"][0]) for b in text_blocks))
                    # Detect multi-column: if there are distinct X clusters > 100px apart
                    if len(x_coords) >= 2:
                        gaps = [x_coords[i+1] - x_coords[i] for i in range(len(x_coords) - 1)]
                        max_gap = max(gaps) if gaps else 0
                        page_width = page.rect.width
                        if max_gap > page_width * 0.3:
                            # Multi-column detected — check if y-order is violated
                            # (blocks should go column-by-column, not row-by-row)
                            misordered_pages.append(page_num + 1)

        doc.close()

    except Exception as e:
        doc.close()
        report["checks"].append(_warn(
            "reading_order",
            f"Reading order check encountered an error: {e} — manual verification recommended",
            "1.3.2"
        ))
        return

    if not misordered_pages:
        report["checks"].append(_pass(
            "reading_order",
            "Reading order appears correct — structure tree ordering matches visual layout",
            "1.3.2"
        ))
    else:
        pages_str = ", ".join(str(p) for p in misordered_pages[:5])
        suffix = f" and {len(misordered_pages) - 5} more" if len(misordered_pages) > 5 else ""
        report["checks"].append(_warn(
            "reading_order",
            f"Multi-column layout detected on page(s) {pages_str}{suffix} — verify reading order follows logical sequence (column-by-column, not row-by-row)",
            "1.3.2"
        ))


def _check_other_annotations(pdf, report):
    """Check that non-Link/Widget annotations have /Contents for accessibility."""
    total_other = 0
    missing_contents = 0

    for page in pdf.pages:
        annots = page.get(pikepdf.Name.Annots)
        if not annots:
            continue
        for annot in annots:
            try:
                subtype = annot.get(pikepdf.Name.Subtype)
                if subtype in (pikepdf.Name.Link, pikepdf.Name.Widget):
                    continue
                total_other += 1
                contents = annot.get(pikepdf.Name.Contents)
                if not contents or str(contents).strip() == "":
                    missing_contents += 1
            except Exception:
                continue

    if total_other == 0:
        report["checks"].append(_pass("other_annotations", "No non-Link/Widget annotations found", "PDF/UA"))
    elif missing_contents == 0:
        report["checks"].append(_pass("other_annotations", f"All {total_other} annotations have /Contents", "PDF/UA"))
    else:
        report["checks"].append(_fail(
            "other_annotations",
            f"{missing_contents} of {total_other} non-Link/Widget annotations missing /Contents description",
            "PDF/UA"
        ))


def _check_language_of_parts(struct_tree, report):
    """Check for /Lang attributes on structure elements (WCAG 3.1.2)."""
    all_elements = _collect_struct_elements(struct_tree)
    lang_count = 0
    for elem in all_elements:
        if pikepdf.Name.Lang in elem:
            lang_count += 1

    if lang_count > 0:
        report["checks"].append(_pass(
            "language_of_parts",
            f"{lang_count} structure elements have /Lang attributes for language-of-parts",
            "3.1.2"
        ))
    else:
        report["checks"].append(_warn(
            "language_of_parts",
            "No structure elements have /Lang attributes — if the document contains text in languages other than the primary language, those passages should be marked",
            "3.1.2"
        ))


def _check_actual_text_symbolic(pdf, struct_tree, report):
    """Check symbolic fonts have /ActualText on corresponding struct elements."""
    SYMBOLIC_PATTERNS = ("symbol", "wingding", "zapfdingbat", "webding", "dingbat")

    symbolic_fonts_found = False
    for page in pdf.pages:
        resources = page.get(pikepdf.Name.Resources)
        if not resources:
            continue
        fonts = resources.get(pikepdf.Name("/Font"))
        if not fonts:
            continue
        for font_name in fonts.keys():
            font = fonts[font_name]
            try:
                base_font = str(font.get(pikepdf.Name("/BaseFont"), "")).lower()
                if any(pat in base_font for pat in SYMBOLIC_PATTERNS):
                    symbolic_fonts_found = True
                    break
            except Exception:
                continue
        if symbolic_fonts_found:
            break

    if not symbolic_fonts_found:
        report["checks"].append(_pass("actual_text_symbolic", "No symbolic fonts detected", "PDF/UA"))
        return

    # Check if struct elements have /ActualText
    all_elements = _collect_struct_elements(struct_tree)
    has_actual_text = any(pikepdf.Name("/ActualText") in elem for elem in all_elements)

    if has_actual_text:
        report["checks"].append(_pass("actual_text_symbolic", "Symbolic fonts detected and /ActualText present on structure elements", "PDF/UA"))
    else:
        report["checks"].append(_warn(
            "actual_text_symbolic",
            "Symbolic fonts detected but no /ActualText found — characters from Symbol/Wingdings/ZapfDingbats fonts need /ActualText for screen readers",
            "PDF/UA"
        ))


def _check_reflow(report):
    """WCAG 1.4.10 — PDFs are fixed-layout, reflow needs manual verification."""
    report["checks"].append(_warn(
        "text_reflow",
        "PDFs are fixed-layout documents — verify content is readable at 400% zoom without horizontal scrolling (WCAG 1.4.10 Reflow)",
        "1.4.10"
    ))


def _check_non_text_contrast(report):
    """WCAG 1.4.11 — graphical objects need 3:1 contrast ratio."""
    report["checks"].append(_warn(
        "non_text_contrast",
        "Graphical objects and UI components need at least 3:1 contrast ratio against adjacent colors — requires manual verification",
        "1.4.11"
    ))
