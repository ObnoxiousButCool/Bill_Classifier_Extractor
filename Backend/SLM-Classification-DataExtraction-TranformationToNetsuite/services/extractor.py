"""
Data extraction service using LLM.
Extracts structured data matching the expected schema format.
"""
from services.llm_service import llm_service
from schemas.generic import (
    GenericJSON, FormsObject, DocumentTable, TableCell,
    FinancialAnchors, TableRow, _str_values
)
from utils.parsers import normalize_currency
from typing import List, Dict, Any, Optional
import json
import re
import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# TABLE FORMAT CONVERTER
# ─────────────────────────────────────────────────────────────────────────────

def convert_headers_rows_to_cells(tables_data: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """
    Convert from headers/rows format to row/col/text cell format.

    Input: [{'headers': [...], 'rows': [[...], ...]}, ...]
    Output: [[{"row": 1, "col": 1, "text": "..."}, ...]]
    """
    if not tables_data or not isinstance(tables_data, list):
        logger.warning(f"tables_data is empty or not a list: {type(tables_data)}")
        return []

    result = []

    for table_idx, table_data in enumerate(tables_data):
        if not isinstance(table_data, dict):
            logger.warning(f"Table {table_idx} is not a dict: {type(table_data)}")
            continue

        headers = table_data.get('headers', [])
        rows = table_data.get('rows', [])

        if not isinstance(headers, list) or not isinstance(rows, list):
            logger.warning(f"Table {table_idx} has invalid headers or rows")
            continue

        cells = []

        # Add header row (row 1)
        for col_idx, header_text in enumerate(headers, start=1):
            cells.append({
                "row": 1,
                "col": col_idx,
                "text": str(header_text) if header_text is not None else ""
            })

        # Add data rows (row 2+)
        for row_idx, row_data in enumerate(rows, start=2):
            if not isinstance(row_data, list):
                logger.warning(f"Table {table_idx}, row {row_idx} is not a list")
                continue

            for col_idx, cell_value in enumerate(row_data, start=1):
                cells.append({
                    "row": row_idx,
                    "col": col_idx,
                    "text": str(cell_value) if cell_value is not None else ""
                })

        if cells:
            result.append(cells)
            logger.info(f"Converted table {table_idx}: {len(headers)} headers, {len(rows)} data rows -> {len(cells)} cells")
        else:
            logger.warning(f"Table {table_idx} produced no cells")
    logger.info(f"============== Converted headers rows to cells ===============")
    logger.info(f"Converted {len(result)} tables from headers/rows to cell format")
    logger.info(f"===============================================================")
    return result


def normalize_table_format(tables_data: Any) -> List[List[Dict[str, Any]]]:
    """
    Auto-detect and normalize table format.
    Handles both headers/rows format and row/col/text format.
    """
    if not tables_data or not isinstance(tables_data, list):
        logger.warning(f"tables_data is empty or not a list: {type(tables_data)}")
        return []

    if not tables_data:
        return []

    first = tables_data[0]

    # Case 1: headers/rows format
    if isinstance(first, dict) and ('headers' in first or 'rows' in first):
        logger.info("Detected headers/rows format, converting...")
        return convert_headers_rows_to_cells(tables_data)

    # Case 2: Already in row/col/text format
    elif isinstance(first, list) and len(first) > 0 and isinstance(first[0], dict) and 'row' in first[0]:
        logger.info("Already in row/col/text format, using as-is")
        return tables_data

    # Case 3: Old flat-dict format
    elif isinstance(first, dict) and any(k.startswith("col") for k in first.keys()):
        logger.warning("Detected legacy flat-dict format, converting...")
        return [_flat_dicts_to_cells(tables_data)]

    # Unknown format
    else:
        logger.error(f"Unknown table format, first item: {type(first)} = {first}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT
# ─────────────────────────────────────────────────────────────────────────────

EXTRACTION_SYSTEM_PROMPT = """Extract ALL data from the bill/receipt into JSON. Output ONLY valid JSON, nothing else.

EXACT OUTPUT STRUCTURE:
{
  "bill_category": "one of: Electronics / Restaurant / Food & Dining / Transportation / Travel / Utilities / Office Supplies / Professional Services / Maintenance & Repairs / Medical & Healthcare / Entertainment / Retail & Shopping / Other",
  "forms": {
    "key": "value"
  },
  "tables": [
    [{"row": 1, "col": 1, "text": "..."}, {"row": 1, "col": 2, "text": "..."}, ...]
  ],
  "anchors": {
    "subtotal": 0.0, "tax": 0.0, "cgst": null, "sgst": null, "igst": null,
    "total": 0.0, "invoice_total": 0.0
  }
}

FORMS RULES:
- Extract EVERY label:value pair from header/footer sections ONLY
- Do NOT extract line items into forms
- Key = the label text, lowercased exactly as written
- Value = the value, or "" if blank
- Examples: "chk", "tbl", "gst", "date", "server", "subtotal", "tax", "total due"

TABLES RULES:
- One inner array per distinct table found
- Row 1 = ALWAYS the header row with literal column label text
- For receipt/restaurant line items: row 1 MUST be: col1="Qty", col2="Item", col3="Price"
- For invoice line items: row 1 MUST be: col1="Qty", col2="Description", col3="Rate", col4="Amount"
- NEVER put an item name or price into row 1 — row 1 is headers only
- Rows 2+ = data rows (actual items)
- Every row must have the same number of col entries
- Empty cells = {"row": N, "col": N, "text": ""}
- Do NOT put table data in forms

ANCHORS RULES:
- Numbers only (no $, no commas)
- Extract: subtotal, tax, total, invoice_total
- cgst/sgst/igst = null if not present

TABLES COLUMN ALIGNMENT RULES (CRITICAL):
- Each item gets its OWN row. Never merge two items into one row.
- Prices often appear offset to the right or on the NEXT line in OCR output — they still belong to the item ABOVE them.
- Read prices strictly in document order: 1st price → 1st item, 2nd price → 2nd item, etc.
- A standalone number on its own line (with no item name) is the price for the item immediately above it.
- If an item truly has no price listed anywhere near it, use col3=""
- NEVER place a price in col2 (description column)
- VALIDATION: before outputting, sum all your col3 prices. They must equal the subtotal (±0.01). If they don't, you have a price assignment error — fix it.

EXAMPLE - RECEIPT WITH OFFSET PRICES (messy OCR):
Input:
                      JW MARRIOTT GRAND RAPIDS
              CHK       1033          TBL32/1
                                               GST
                         15 Apr'21 5:22 PM
               1 HOLIDAY MARGARITA
               1MUSSELS                        13.00
                                               16.00
             1/2 SMALL WARM SEAFO0D TOWER 27.50
              1.FIRE PASTA
                                               0.00
              1 SALMON ENTREE                  33.00
             1 CHEVRE CHEESECAKE
                                               10.00
                SUBTOTAL                      $99.50
               TAX                             $5.97
                    T0TAL DUE$105.47

Step-by-step price assignment (REQUIRED reasoning):
- "1 HOLIDAY MARGARITA" → next number is 13.00 → price = 13.00
- "1MUSSELS" → next number after 13.00 is 16.00 → price = 16.00
- "1/2 SMALL WARM SEAFO0D TOWER" → next number is 27.50 → price = 27.50
- "1.FIRE PASTA" → next number is 0.00 → price = 0.00
- "1 SALMON ENTREE" → next number is 33.00 → price = 33.00
- "1 CHEVRE CHEESECAKE" → next number is 10.00 → price = 10.00
- Check: 13+16+27.5+0+33+10 = 99.5 ✓ matches subtotal

Output:
{
  "bill_category": "Restaurant",
  "forms": {
    "chk": "1033",
    "tbl": "32/1",
    "gst": "1",
    "date": "15 Apr'21 5:22 PM",
    "subtotal": "$99.50",
    "tax": "$5.97",
    "total due": "$105.47",
    "tip": "",
    "room number": "",
    "signature": ""
  },
  "tables": [
    [
      {"row":1,"col":1,"text":"Qty"},{"row":1,"col":2,"text":"Item"},{"row":1,"col":3,"text":"Price"},
      {"row":2,"col":1,"text":"1"},{"row":2,"col":2,"text":"HOLIDAY MARGARITA"},{"row":2,"col":3,"text":"13.00"},
      {"row":3,"col":1,"text":"1"},{"row":3,"col":2,"text":"MUSSELS"},{"row":3,"col":3,"text":"16.00"},
      {"row":4,"col":1,"text":"1/2"},{"row":4,"col":2,"text":"SMALL WARM SEAFOOD TOWER"},{"row":4,"col":3,"text":"27.50"},
      {"row":5,"col":1,"text":"1"},{"row":5,"col":2,"text":"FIRE PASTA"},{"row":5,"col":3,"text":"0.00"},
      {"row":6,"col":1,"text":"1"},{"row":6,"col":2,"text":"SALMON ENTREE"},{"row":6,"col":3,"text":"33.00"},
      {"row":7,"col":1,"text":"1"},{"row":7,"col":2,"text":"CHEVRE CHEESECAKE"},{"row":7,"col":3,"text":"10.00"}
    ]
  ],
  "anchors": {
    "subtotal": 99.50, "tax": 5.97, "cgst": null, "sgst": null, "igst": null,
    "total": 105.47, "invoice_total": 105.47
  }
}

Now extract from this document:
"""


# ─────────────────────────────────────────────────────────────────────────────
# RESPONSE CLEANING
# ─────────────────────────────────────────────────────────────────────────────

def clean_llm_json_response(response: str) -> Dict[Any, Any]:
    """Clean LLM response and extract valid JSON."""
    original = response
    response = response.strip()

    # Strip markdown fences
    response = re.sub(r'```json\s*', '', response, flags=re.IGNORECASE)
    response = re.sub(r'```\s*', '', response)

    # Find outermost JSON object
    json_match = re.search(r'\{.*\}', response, re.DOTALL)
    if not json_match:
        logger.error(f"No JSON object found in LLM response.\nRaw output (first 500 chars):\n{original[:500]}")
        raise ValueError("No valid JSON found in LLM response")

    raw_json = json_match.group()
    try:
        return json.loads(raw_json)
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}\nAttempted JSON (first 500 chars):\n{raw_json[:500]}")
        raise ValueError(f"Invalid JSON in LLM response: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# FORMS
# ─────────────────────────────────────────────────────────────────────────────

def build_forms(forms_data: Any) -> FormsObject:
    """Build FormsObject from LLM output."""
    if not forms_data or not isinstance(forms_data, dict):
        logger.warning(f"forms_data is empty or non-dict: {type(forms_data)} = {forms_data!r}")
        return FormsObject(fields={})

    fo = FormsObject.from_dict(forms_data)

    if not fo.fields:
        logger.warning(f"FormsObject built but fields is empty. Input was: {forms_data}")
    else:
        logger.info(f"Forms extracted: {list(fo.fields.keys())}")

    return fo


# ─────────────────────────────────────────────────────────────────────────────
# TABLES
# ─────────────────────────────────────────────────────────────────────────────

def build_tables(tables_data: Any) -> List[DocumentTable]:
    """
    Build list of DocumentTable from LLM output.
    Auto-detects and handles multiple formats.
    """
    if not tables_data or not isinstance(tables_data, list):
        logger.warning(f"tables_data is empty or non-list: {type(tables_data)}")
        return []


    logger.info(f"========== LLM RAW TABLE DEBUG ==========")
    logger.info(f"Tables from LLM: {tables_data}")
    logger.info(f"Table count: {len(tables_data)}")
    logger.info(f"=========================================")

    # Normalize to row/col/text format
    normalized_tables = normalize_table_format(tables_data)

    if not normalized_tables:
        logger.warning("No valid tables after normalization")
        return []

    # Parse each table
    result = []
    for i, cell_list in enumerate(normalized_tables):
        cells = _parse_cell_list(cell_list)
        if cells:
            result.append(DocumentTable(cells=cells))
            logger.info(f"Built table {i} with {len(cells)} cells")
        else:
            logger.warning(f"Table {i} produced no valid cells, skipping")

    logger.info(f"Built {len(result)} DocumentTable objects")
    return result


def _parse_cell_list(raw: List[Any]) -> List[TableCell]:
    """Parse list of cell dicts into TableCell objects."""
    cells = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            cells.append(TableCell(
                row=int(item["row"]),
                col=int(item["col"]),
                text=str(item.get("text", "")) if item.get("text") is not None else ""
            ))
        except (KeyError, ValueError, TypeError) as e:
            logger.debug(f"Skipping malformed cell {item}: {e}")
    return cells


def _flat_dicts_to_cells(rows: List[Dict]) -> List[TableCell]:
    """Convert old flat-dict format to cells."""
    if not rows:
        return []
    n_cols = 4
    cells = []
    for r_idx, row in enumerate(rows, start=2):
        for c_idx in range(1, n_cols + 1):
            cells.append(TableCell(
                row=r_idx, col=c_idx,
                text=str(row.get(f"col{c_idx}", ""))
            ))
    return cells


# ─────────────────────────────────────────────────────────────────────────────
# ANCHORS
# ─────────────────────────────────────────────────────────────────────────────

def _to_float(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return normalize_currency(str(v))
    except Exception:
        return 0.0


def _to_opt_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    f = _to_float(v)
    return f if f != 0.0 else None


def extract_tax_components_from_text(raw_text: str, subtotal: float) -> dict:
    result = {"cgst": 0.0, "sgst": 0.0, "igst": 0.0, "tax": 0.0}

    patterns = {
        "cgst": r'(?:CGST|C-GST|Central\s+GST)[:\s@]*(?:[\d.]+%)?[:\s]*(?:Rs\.?|₹)?\s*([\d,]+\.?\d*)',
        "sgst": r'(?:SGST|S-GST|State\s+GST)[:\s@]*(?:[\d.]+%)?[:\s]*(?:Rs\.?|₹)?\s*([\d,]+\.?\d*)',
        "igst": r'(?:IGST|I-GST|Integrated\s+GST)[:\s@]*(?:[\d.]+%)?[:\s]*(?:Rs\.?|₹)?\s*([\d,]+\.?\d*)',
    }
    for key, pattern in patterns.items():
        for m in re.finditer(pattern, raw_text, re.IGNORECASE):
            try:
                result[key] += normalize_currency(m.group(1))
            except Exception:
                pass

    result["tax"] = result["cgst"] + result["sgst"] + result["igst"]

    if result["tax"] == 0.0 and subtotal > 0:
        for key, label in [("cgst", "CGST|C-GST"), ("sgst", "SGST|S-GST"), ("igst", "IGST|I-GST")]:
            m = re.search(rf'(?:{label})[:\s@]*([\d.]+)%', raw_text, re.IGNORECASE)
            if m:
                result[key] = subtotal * float(m.group(1)) / 100
        result["tax"] = result["cgst"] + result["sgst"] + result["igst"]

    if result["tax"] == 0.0:
        for m in re.finditer(
            r'(?:GST|VAT|Tax|Sales\s+Tax)[:\s@]*(?:[\d.]+%)?[:\s]*(?:Rs\.?|₹)?\s*([\d,]+\.?\d*)',
            raw_text, re.IGNORECASE
        ):
            try:
                result["tax"] += normalize_currency(m.group(1))
            except Exception:
                pass

    return result


def build_anchors(anchors_data: Dict[str, Any], raw_text: str = "") -> FinancialAnchors:
    if not anchors_data:
        anchors_data = {}

    subtotal = _to_float(anchors_data.get("subtotal"))
    cgst     = _to_opt_float(anchors_data.get("cgst"))
    sgst     = _to_opt_float(anchors_data.get("sgst"))
    igst     = _to_opt_float(anchors_data.get("igst"))
    tax      = _to_float(anchors_data.get("tax"))
    total    = _to_float(anchors_data.get("total"))

    has_gst = bool(raw_text) and any(
        kw in raw_text.upper()
        for kw in ('CGST', 'SGST', 'IGST', 'C-GST', 'S-GST', 'I-GST', 'GST @')
    )
    if has_gst and cgst is None and sgst is None and igst is None and subtotal > 0:
        fb = extract_tax_components_from_text(raw_text, subtotal)
        if fb["tax"] > 0:
            cgst = fb["cgst"] if fb["cgst"] > 0 else None
            sgst = fb["sgst"] if fb["sgst"] > 0 else None
            igst = fb["igst"] if fb["igst"] > 0 else None
            if tax == 0.0:
                tax = fb["tax"]

    component_sum = (cgst or 0.0) + (sgst or 0.0) + (igst or 0.0)
    if component_sum > 0:
        if abs(tax - component_sum) > 0.01:
            logger.warning(f"Tax mismatch: stated={tax}, components={component_sum}. Using component sum.")
        tax = component_sum

    if total < subtotal + tax and subtotal > 0 and tax > 0:
        total = round(subtotal + tax, 2)

    # Derive subtotal if missing: subtotal = total - tax (handles receipts that use
    # "Sub" or "Grand Total" labels that the LLM maps to total/invoice_total but not subtotal)
    if subtotal == 0.0 and total > 0.0 and tax > 0.0:
        subtotal = round(total - tax, 2)
        logger.info(f"Derived subtotal from total-tax: {total} - {tax} = {subtotal}")

    invoice_total = _to_float(anchors_data.get("invoice_total"))
    if invoice_total == 0.0 and total > 0.0:
        invoice_total = total

    return FinancialAnchors(
        subtotal=subtotal, cgst=cgst, sgst=sgst, igst=igst,
        tax=tax, total=total, invoice_total=invoice_total
    )


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────────────────────────────────────────

def validate_extraction(generic_json: GenericJSON) -> bool:
    print(f"---> validate_extraction: received {generic_json}")
    print("Internal tables:", generic_json.internal_tables)
    print("Document tables:", generic_json.document_tables)

    issues = []

    if not generic_json.forms and not generic_json.document_tables:
        issues.append("No meaningful data extracted")

    if generic_json.anchors.total == 0 and len(generic_json.document_tables) > 0:
        issues.append("Total is zero but tables exist")

    for field in ("subtotal", "tax", "total"):
        if getattr(generic_json.anchors, field) < 0:
            issues.append(f"Negative {field}")

    if (generic_json.anchors.tax == 0 and
            any(kw in generic_json.raw_text.upper() for kw in ('CGST', 'SGST', 'IGST', 'GST @'))):
        issues.append("Tax keywords found but tax amount is 0")

    if issues:
        logger.warning(f"Validation issues: {', '.join(issues)}")
        return False
    print(f"validation passed")
    logger.info("Validation passed")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def extract_generic_json(text: str) -> GenericJSON:
    """Extract structured data from bill text using LLM."""
    try:
        # ── call LLM ─────────────────────────────────────────────────
        raw_response = llm_service.extract_with_retry(
            prompt=f"{text}\n\nJSON output:",
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            response_format="json",
            temperature=0.0,
            max_tokens=3000,
            max_retries=2
        )
        logger.info(f"========== !! LLM RAW DATA DEBUG !! ==========")
        logger.debug(f"Raw LLM response type: {type(raw_response)}")
        logger.info(f"=========================================")


        # ── parse ─────────────────────────────────────────────────────
        if isinstance(raw_response, str):
            data = clean_llm_json_response(raw_response)
        elif isinstance(raw_response, dict):
            data = raw_response
        else:
            raise ValueError(f"Unexpected LLM response type: {type(raw_response)}")

        logger.info(f"========== EXTRACTION DEBUG ==========")
        logger.info(f"Parsed LLM data keys: {list(data.keys())}")
        logger.info(f"Tables data: {data.get('tables', [])}")
        logger.info(f"=====================================")

        # ── unwrap 'result' wrapper if model used it ──────────────────
        if "result" in data and isinstance(data["result"], dict) and "forms" not in data:
            logger.info("Unwrapping 'result' key from LLM output")
            data = data["result"]

        # ── build objects ─────────────────────────────────────────────
        forms   = build_forms(data.get("forms", {}))
        tables  = build_tables(data.get("tables", []))
        anchors = build_anchors(data.get("anchors", {}), raw_text=text)

        logger.info(f"========== BUILT OBJECTS ==========")
        logger.info(f"Forms fields: {len(forms.fields)}")
        logger.info(f"DocumentTable count: {len(tables)}")
        for i, table in enumerate(tables):
            logger.info(f"  Table {i}: {len(table.cells)} cells, {table.num_rows} rows, {table.num_cols} cols")
        logger.info(f"===================================")

        generic_json = GenericJSON(
            forms=forms,
            internal_tables=tables,  # ← Use _internal_tables
            anchors=anchors,
            raw_text=text,
            bill_category=data.get("bill_category") or data.get("billCategory"),
        )

        logger.info(
            f"Extracted: vendor={forms.vendor!r}, "
            f"form_fields={len(forms.fields)}, document_tables={len(tables)}, "
            f"subtotal={anchors.subtotal}, tax={anchors.tax}, total={anchors.total}"
        )

        validate_extraction(generic_json)
        return generic_json

    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)
        raise ValueError(f"Failed to extract data from bill: {e}")