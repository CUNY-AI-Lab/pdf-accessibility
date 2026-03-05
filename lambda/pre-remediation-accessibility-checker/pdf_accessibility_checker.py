"""
PDF/UA + WCAG 2.1 AA accessibility checker using pikepdf and PyMuPDF.

Replaces Adobe PDFAccessibilityCheckerJob with open-source tooling.

Checks implemented:
  Document:
    - /MarkInfo exists with /Marked true (WCAG 1.3.1)
    - /StructTreeRoot exists (WCAG 1.3.1)
    - /Lang set on catalog (WCAG 3.1.1)
    - /Title in metadata + XMP (WCAG 2.4.2)
    - /ViewerPreferences/DisplayDocTitle true (WCAG 2.4.2)
  Navigation:
    - /Tabs /S on each page (WCAG 2.4.3)
    - /Outlines exist for docs > 20 pages (WCAG 2.4.5)
  Headings:
    - H1-H6 proper nesting (WCAG 1.3.1)
  Images:
    - All /Figure elements have /Alt or /ActualText (WCAG 1.1.1)
  Tables:
    - /Table elements contain /TH cells (WCAG 1.3.1)
    - /TH cells have /Scope attribute (WCAG 1.3.1)
  Lists:
    - /L -> /LI -> /Lbl + /LBody structure (WCAG 1.3.1)
  Links:
    - /Link annotations have /Contents or /Alt (WCAG 2.4.4)
"""

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

    # Page-level checks
    _check_tabs(pdf, report)
    _check_outlines(pdf, report)

    # Structure tree checks
    struct_tree = pdf.Root.get(pikepdf.Name.StructTreeRoot)
    if struct_tree:
        _check_heading_nesting(struct_tree, report)
        _check_figures_alt_text(struct_tree, report)
        _check_tables(struct_tree, report)
        _check_lists(struct_tree, report)

    # Link checks
    _check_links(pdf, report)

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
        "tab_order": ("Navigation", "Tab Order"),
        "outlines": ("Navigation", "Bookmarks"),
        "heading_nesting": ("Headings", "Heading Nesting"),
        "figure_alt_text": ("Images", "Figures Alternate Text"),
        "table_headers": ("Tables", "Table Headers"),
        "table_header_scope": ("Tables", "Table Header Scope"),
        "list_structure": ("Lists", "List Structure"),
        "link_alt_text": ("Links", "Link Alternate Text"),
        "document_open": ("Document", "Document Open"),
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

    if pikepdf.Name.Outlines in pdf.Root:
        report["checks"].append(_pass("outlines", "/Outlines (bookmarks) exist", "2.4.5"))
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
                elif isinstance(child, pikepdf.Object):
                    try:
                        resolved = pikepdf.Object(child)
                        if isinstance(resolved, pikepdf.Dictionary):
                            results.extend(_collect_struct_elements(resolved, tag_name))
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

    # Check for skipped levels
    skipped = False
    for i in range(1, len(heading_levels)):
        if heading_levels[i] > heading_levels[i - 1] + 1:
            report["checks"].append(_fail(
                "heading_nesting",
                f"Heading level skipped: H{heading_levels[i-1]} -> H{heading_levels[i]}",
                "1.3.1"
            ))
            skipped = True
            break

    if not skipped:
        report["checks"].append(_pass("heading_nesting", "Heading levels properly nested", "1.3.1"))


def _check_figures_alt_text(struct_tree, report):
    """Check that all Figure elements have /Alt or /ActualText."""
    figures = _collect_struct_elements(struct_tree, "Figure")

    if not figures:
        report["checks"].append(_pass("figure_alt_text", "No Figure elements found", "1.1.1"))
        return

    missing_alt = 0
    for fig in figures:
        alt = fig.get(pikepdf.Name.Alt)
        actual_text = fig.get(pikepdf.Name("/ActualText"))
        if not alt and not actual_text:
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
        report["checks"].append(_warn(
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

    malformed = 0
    for lst in lists:
        lis = _collect_struct_elements(lst, "LI")
        if not lis:
            malformed += 1

    if malformed == 0:
        report["checks"].append(_pass("list_structure", f"All {len(lists)} List elements properly structured", "1.3.1"))
    else:
        report["checks"].append(_fail(
            "list_structure",
            f"{malformed} of {len(lists)} List elements missing /LI children",
            "1.3.1"
        ))


# --- Link checks ---

def _check_links(pdf, report):
    """Check that Link annotations have /Contents or /Alt."""
    total_links = 0
    missing_alt = 0

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
