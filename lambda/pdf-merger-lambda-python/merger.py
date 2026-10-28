"""
Structure-tree-aware PDF merger using pikepdf.

Replaces the Java/PDFBox merger that destroyed all accessibility metadata.
Merges chunk PDFs while preserving and re-linking:
  - StructTreeRoot with all structure elements
  - ParentTree with MCID mappings
  - /Pg references (remapped to merged page indices)
  - /MarkInfo, /Lang, ViewerPreferences
"""

import os
import logging
import boto3
import pikepdf

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

s3 = boto3.client('s3')

WORK_DIR = '/tmp'


def _safe_copy_foreign(merged, obj):
    """Copy a foreign object, handling both direct and indirect objects."""
    try:
        return merged.copy_foreign(obj)
    except pikepdf._core.ForeignObjectError:
        # Direct object — rebuild it in the target PDF
        if isinstance(obj, pikepdf.Dictionary):
            new_dict = pikepdf.Dictionary()
            for key in obj.keys():
                try:
                    new_dict[key] = _safe_copy_foreign(merged, obj[key])
                except Exception:
                    new_dict[key] = obj[key]
            return new_dict
        elif isinstance(obj, pikepdf.Array):
            new_arr = pikepdf.Array()
            for item in obj:
                try:
                    new_arr.append(_safe_copy_foreign(merged, item))
                except Exception:
                    new_arr.append(item)
            return new_arr
        elif isinstance(obj, pikepdf.String):
            return pikepdf.String(str(obj))
        elif isinstance(obj, pikepdf.Name):
            return pikepdf.Name(str(obj))
        else:
            # For other scalar types, try to recreate
            try:
                return type(obj)(obj)
            except Exception:
                return obj


def download_chunk(bucket_name, s3_key, local_path):
    """Download a chunk PDF from S3."""
    logger.info(f"Downloading chunk: {s3_key}")
    s3.download_file(bucket_name, s3_key, local_path)


def upload_merged(bucket_name, s3_key, local_path):
    """Upload the merged PDF to S3."""
    logger.info(f"Uploading merged PDF: {s3_key}")
    with open(local_path, "rb") as f:
        s3.upload_fileobj(f, bucket_name, s3_key)


def _remap_page_refs(node, old_pages, new_pages_map):
    """Recursively update /Pg references in structure elements."""
    if not isinstance(node, pikepdf.Dictionary):
        return

    # Update /Pg reference
    pg = node.get(pikepdf.Name.Pg)
    if pg is not None:
        # Find which old page this refers to and remap
        for old_idx, old_page in enumerate(old_pages):
            try:
                if pg.objgen == old_page.objgen:
                    if old_idx in new_pages_map:
                        node["/Pg"] = new_pages_map[old_idx]
                    break
            except Exception:
                continue

    # Recurse into children
    k = node.get(pikepdf.Name.K)
    if k is not None:
        if isinstance(k, pikepdf.Array):
            for child in k:
                try:
                    if pikepdf.Name.S in child or pikepdf.Name.K in child:
                        _remap_page_refs(child, old_pages, new_pages_map)
                except Exception:
                    pass
        elif isinstance(k, pikepdf.Dictionary):
            _remap_page_refs(k, old_pages, new_pages_map)


def _update_parent_refs(node, new_parent_ref):
    """Update /P references on direct children of a node."""
    k = node.get(pikepdf.Name.K)
    if k is None:
        return
    if isinstance(k, pikepdf.Array):
        for child in k:
            try:
                if pikepdf.Name.S in child:
                    child["/P"] = new_parent_ref
            except Exception:
                pass
    elif isinstance(k, pikepdf.Dictionary):
        try:
            if pikepdf.Name.S in k:
                k["/P"] = new_parent_ref
        except Exception:
            pass


def _offset_mcids(node, offset):
    """Recursively offset MCID integer values in /K arrays."""
    if not isinstance(node, pikepdf.Dictionary):
        return

    k = node.get(pikepdf.Name.K)
    if k is not None:
        if isinstance(k, pikepdf.Array):
            new_k = pikepdf.Array()
            for item in k:
                if isinstance(item, (int, pikepdf.objects.Object)) and not isinstance(item, (pikepdf.Dictionary, pikepdf.Array)):
                    try:
                        val = int(item)
                        new_k.append(val + offset)
                        continue
                    except (TypeError, ValueError):
                        pass
                new_k.append(item)
                # Recurse into child struct elements
                try:
                    if isinstance(item, pikepdf.Dictionary) or (pikepdf.Name.S in item):
                        _offset_mcids(item, offset)
                except Exception:
                    pass
            node["/K"] = new_k
        elif isinstance(k, (int, pikepdf.objects.Object)):
            try:
                val = int(k)
                node["/K"] = pikepdf.Array([val + offset])
            except (TypeError, ValueError):
                pass


def merge_pdfs(chunk_keys, bucket_name):
    """Merge chunk PDFs with structure tree preservation."""
    # Derive FINAL_ chunk keys (same pattern as Java merger)
    final_keys = []
    for key in chunk_keys:
        last_slash = key.rfind('/')
        if last_slash != -1:
            directory = key[:last_slash + 1]
            file_name = key[last_slash + 1:]
            final_keys.append(directory + "FINAL_" + file_name)
        else:
            final_keys.append("FINAL_" + key)

    # Derive output path
    first_key = chunk_keys[0]
    base_file_name = first_key[first_key.rfind('/') + 1:]
    # Remove chunk suffix like _chunk_0, _chunk_1, etc.
    import re
    base_file_name = re.sub(r'_chunk_\d+', '', base_file_name)
    output_key = f"temp/{base_file_name.replace('.pdf', '')}/merged_{base_file_name}"

    # Download all chunks
    chunk_pdfs = []
    local_paths = []
    for i, key in enumerate(final_keys):
        local_path = os.path.join(WORK_DIR, f"chunk_{i}.pdf")
        download_chunk(bucket_name, key, local_path)
        local_paths.append(local_path)
        chunk_pdfs.append(pikepdf.Pdf.open(local_path))

    logger.info(f"Loaded {len(chunk_pdfs)} chunk PDFs for merging")

    # Create merged PDF
    merged = pikepdf.Pdf.new()

    # Unified structure tree
    struct_tree_root = pikepdf.Dictionary()
    struct_tree_root["/Type"] = pikepdf.Name.StructTreeRoot
    struct_tree_root["/RoleMap"] = pikepdf.Dictionary()

    doc_elem = pikepdf.Dictionary()
    doc_elem["/Type"] = pikepdf.Name.StructElem
    doc_elem["/S"] = pikepdf.Name.Document
    doc_elem["/P"] = merged.make_indirect(struct_tree_root)
    doc_elem_ref = merged.make_indirect(doc_elem)

    all_children = pikepdf.Array()
    all_parent_tree_nums = pikepdf.Array()

    global_page_offset = 0
    global_mcid_offset = 0

    for chunk_idx, chunk_pdf in enumerate(chunk_pdfs):
        chunk_page_count = len(chunk_pdf.pages)

        # Copy pages from chunk to merged
        old_pages = [page.obj for page in chunk_pdf.pages]
        merged.pages.extend(chunk_pdf.pages)

        # Build old page -> new page mapping
        new_pages_map = {}
        for local_idx in range(chunk_page_count):
            global_idx = global_page_offset + local_idx
            new_pages_map[local_idx] = merged.pages[global_idx].obj

        # Copy /Tabs /S to new pages
        for local_idx in range(chunk_page_count):
            global_idx = global_page_offset + local_idx
            merged.pages[global_idx]["/Tabs"] = pikepdf.Name.S

        # Extract structure tree from chunk
        chunk_struct_tree = chunk_pdf.Root.get(pikepdf.Name.StructTreeRoot)
        if chunk_struct_tree:
            chunk_k = chunk_struct_tree.get(pikepdf.Name.K)
            if chunk_k is not None:
                # Get children: usually K is an array with one Document element
                if isinstance(chunk_k, pikepdf.Array):
                    for child in chunk_k:
                        _process_chunk_struct_children(
                            merged, child, doc_elem_ref, old_pages, new_pages_map,
                            global_mcid_offset, all_children
                        )
                elif isinstance(chunk_k, pikepdf.Dictionary):
                    _process_chunk_struct_children(
                        merged, chunk_k, doc_elem_ref, old_pages, new_pages_map,
                        global_mcid_offset, all_children
                    )

            # Extract ParentTree entries and remap
            parent_tree = chunk_struct_tree.get(pikepdf.Name("/ParentTree"))
            if parent_tree:
                nums = parent_tree.get(pikepdf.Name("/Nums"))
                if nums and isinstance(nums, pikepdf.Array):
                    i = 0
                    while i < len(nums) - 1:
                        try:
                            page_idx = int(nums[i])
                            refs = nums[i + 1]
                            # Remap page index to global
                            global_page_idx = page_idx + global_page_offset
                            all_parent_tree_nums.append(global_page_idx)
                            # Copy the refs array to merged PDF
                            all_parent_tree_nums.append(_safe_copy_foreign(merged,refs))
                        except Exception as e:
                            logger.warning(f"Failed to remap parent tree entry: {e}")
                        i += 2

            # Count MCIDs in this chunk for offset
            ptk = chunk_struct_tree.get(pikepdf.Name("/ParentTreeNextKey"))
            if ptk:
                try:
                    global_mcid_offset += int(ptk)
                except (TypeError, ValueError):
                    global_mcid_offset += chunk_page_count
            else:
                global_mcid_offset += chunk_page_count

        # Copy first chunk's metadata
        if chunk_idx == 0:
            # MarkInfo — always create fresh since it's simple
            mi = pikepdf.Dictionary()
            mi["/Marked"] = True
            merged.Root["/MarkInfo"] = mi

            # Lang — recreate as new string
            lang = chunk_pdf.Root.get(pikepdf.Name.Lang)
            if lang:
                merged.Root["/Lang"] = pikepdf.String(str(lang))

            # ViewerPreferences — recreate fresh
            vp = chunk_pdf.Root.get(pikepdf.Name.ViewerPreferences)
            if vp:
                new_vp = pikepdf.Dictionary()
                if vp.get(pikepdf.Name.DisplayDocTitle):
                    new_vp["/DisplayDocTitle"] = True
                merged.Root["/ViewerPreferences"] = new_vp

        global_page_offset += chunk_page_count

    # Assemble structure tree
    doc_elem["/K"] = all_children
    struct_tree_root["/K"] = pikepdf.Array([doc_elem_ref])

    # Build unified parent tree
    parent_tree = pikepdf.Dictionary()
    parent_tree["/Type"] = pikepdf.Name("/NumberTree")
    parent_tree["/Nums"] = all_parent_tree_nums
    struct_tree_root["/ParentTree"] = merged.make_indirect(parent_tree)
    struct_tree_root["/ParentTreeNextKey"] = len(merged.pages)

    merged.Root["/StructTreeRoot"] = merged.make_indirect(struct_tree_root)

    # Ensure MarkInfo exists
    if pikepdf.Name.MarkInfo not in merged.Root:
        mi = pikepdf.Dictionary()
        mi["/Marked"] = True
        merged.Root["/MarkInfo"] = mi

    # Save merged PDF
    merged_path = os.path.join(WORK_DIR, f"merged_{base_file_name}")
    merged.save(merged_path)
    merged.close()

    # Close chunk PDFs
    for pdf in chunk_pdfs:
        pdf.close()

    # Upload
    upload_merged(bucket_name, output_key, merged_path)

    logger.info(f"Merge complete: {len(chunk_keys)} chunks -> {output_key} ({global_page_offset} pages)")

    return bucket_name, output_key, base_file_name


def _process_chunk_struct_children(merged, node, doc_elem_ref, old_pages, new_pages_map, mcid_offset, all_children):
    """Process a chunk's structure tree node, copying its children to the merged document."""
    try:
        # If this is a Document element, grab its children
        s = node.get(pikepdf.Name.S)
        if s is not None and str(s) == "/Document":
            k = node.get(pikepdf.Name.K)
            if k is not None:
                if isinstance(k, pikepdf.Array):
                    for child in k:
                        try:
                            copied = _safe_copy_foreign(merged,child)
                            copied["/P"] = doc_elem_ref
                            _remap_page_refs(copied, old_pages, new_pages_map)
                            if mcid_offset > 0:
                                _offset_mcids(copied, mcid_offset)
                            all_children.append(merged.make_indirect(copied))
                        except Exception as e:
                            logger.warning(f"Failed to copy struct element: {e}")
                elif isinstance(k, pikepdf.Dictionary):
                    try:
                        copied = _safe_copy_foreign(merged,k)
                        copied["/P"] = doc_elem_ref
                        _remap_page_refs(copied, old_pages, new_pages_map)
                        if mcid_offset > 0:
                            _offset_mcids(copied, mcid_offset)
                        all_children.append(merged.make_indirect(copied))
                    except Exception as e:
                        logger.warning(f"Failed to copy struct element: {e}")
        else:
            # Not a Document element — copy the whole thing
            copied = _safe_copy_foreign(merged,node)
            copied["/P"] = doc_elem_ref
            _remap_page_refs(copied, old_pages, new_pages_map)
            if mcid_offset > 0:
                _offset_mcids(copied, mcid_offset)
            all_children.append(merged.make_indirect(copied))
    except Exception as e:
        logger.warning(f"Failed to process chunk struct node: {e}")


def lambda_handler(event, context):
    """
    Lambda entry point. Same input/output contract as the Java merger.

    Expects event with:
        fileNames: list of S3 keys for chunk PDFs

    Returns:
        String with merge result (same format as Java merger).
    """
    bucket_name = os.environ.get('BUCKET_NAME')

    file_names = event.get('fileNames', [])
    if not file_names:
        return "No files to merge."

    try:
        bucket, output_key, base_file_name = merge_pdfs(file_names, bucket_name)
        result = f"PDFs merged successfully.\nBucket: {bucket}\nMerged File Key: {output_key}\nMerged File Name: {base_file_name}"
        logger.info(f"File: {base_file_name.replace('.pdf', '')}, Status: succeeded")
        return result
    except Exception as e:
        import re
        import traceback
        base_name = file_names[0] if file_names else "unknown"
        base_name = base_name[base_name.rfind('/') + 1:]
        base_name = re.sub(r'_chunk_\d+', '', base_name).replace('.pdf', '')
        print(f"File: {base_name}, Status: Failed in Merging the PDF")
        print(f"Error: {e}")
        print(traceback.format_exc())
        return "Failed to merge PDFs."
