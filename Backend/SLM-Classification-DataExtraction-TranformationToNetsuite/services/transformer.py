"""
Data transformation engine - bill_subtype REMOVED from NetSuite objects
Transforms generic JSON to NetSuite-compatible format.
Supports TWO distinct schemas: Invoice and Expense.
"""
from schemas.generic import GenericJSON
from schemas.netsuite import (
    NetSuiteInvoice,
    NetSuiteExpense,
    InvoiceLineItem,
    ItemRef,
    ExpenseItem,
    ExpenseBlock,
    EntityRef,
    get_category_for_subtype
)
from utils.parsers import extract_date, normalize_currency, generate_invoice_id
from typing import Union, Dict, List
import logging

logger = logging.getLogger(__name__)


def transform_to_netsuite(generic: GenericJSON, bill_type: str, bill_subtype: str) -> Union[NetSuiteInvoice, NetSuiteExpense]:
    """
    Route to appropriate transformation based on bill_type.
    """
    if bill_type == "Invoice Bill":
        return _transform_to_invoice(generic, bill_subtype)
    elif bill_type == "Expense Bill":
        return _transform_to_expense(generic, bill_subtype)
    else:
        raise ValueError(f"Unknown bill_type: {bill_type}")


def _clean_numeric_string(value: str) -> float:
    """
    Clean and convert numeric strings to float.

    Examples:
        "6.00" -> 6.0
        "3,480.00" -> 3480.0
    """
    if not value:
        return 0.0

    cleaned = str(value).replace(',', '').strip()

    try:
        return float(cleaned)
    except (ValueError, TypeError):
        logger.warning(f"Could not convert '{value}' to number, returning 0.0")
        return 0.0


def _parse_table_to_rows(table) -> Dict[int, Dict[int, str]]:
    """
    Parse DocumentTable cells into row dictionary.

    Returns:
        {row_num: {col_num: text, ...}, ...}
    """
    rows_dict = {}
    for cell in table.cells:
        if cell.row not in rows_dict:
            rows_dict[cell.row] = {}
        rows_dict[cell.row][cell.col] = cell.text.strip()
    return rows_dict


def _resolve_column_layout(rows_dict: Dict[int, Dict[int, str]], max_col: int) -> Dict[str, int]:
    """
    Read the header row (row 1) to determine which column index holds
    description, qty, rate, and amount — regardless of column order.

    Handles layouts like:
      • Qty / Item / Price          (3-col receipt: desc=col2)
      • Item / Qty / Price / Amount (4-col Indian receipt: desc=col1)
      • Qty / Description / Rate / Amount (4-col invoice: desc=col2)

    Returns a dict with keys: 'desc', 'qty', 'rate', 'amount'
    Values are 1-based column indices, or None if not found.
    """
    headers = {c: rows_dict.get(1, {}).get(c, "").lower().strip()
               for c in range(1, max_col + 1)}

    desc_col = None
    qty_col = None
    rate_col = None
    amount_col = None

    for col, h in headers.items():
        if any(kw in h for kw in ('item', 'description', 'desc', 'particulars', 'name', 'sku')):
            desc_col = col
        elif any(kw in h for kw in ('qty', 'quantity', 'units', 'nos')):
            qty_col = col
        elif any(kw in h for kw in ('amount', 'total', 'amt')):
            amount_col = col
        elif any(kw in h for kw in ('price', 'rate', 'unit price', 'mrp')):
            rate_col = col

    # If amount and rate are not distinguished, treat the last numeric-header col as amount
    if amount_col is None and rate_col is not None:
        amount_col = rate_col
        rate_col = None

    # Fallback: if headers are blank/non-standard, use positional defaults
    # For 3-col: 1=Qty, 2=Desc, 3=Price
    # For 4-col: 1=Qty, 2=Desc, 3=Rate, 4=Amount (standard invoice)
    if desc_col is None:
        if max_col == 3:
            qty_col, desc_col, amount_col = 1, 2, 3
        else:
            qty_col, desc_col, rate_col, amount_col = 1, 2, 3, 4

    logger.info(
        f"Column layout resolved: desc={desc_col}, qty={qty_col}, "
        f"rate={rate_col}, amount={amount_col} | headers={list(headers.values())}"
    )

    return {
        'desc': desc_col,
        'qty': qty_col,
        'rate': rate_col,
        'amount': amount_col,
    }


def _find_line_items_table(generic: GenericJSON):
    """
    Find the table containing line items.

    Primary: looks for table with Qty/Description/Item/Price/Amount headers in row 1.
    Fallback: if headers are blank/missing, detects by data pattern —
              a table where data rows have text in col 2 and a numeric value in the last column.

    Returns:
        DocumentTable or None
    """
    best_table = None
    best_score = 0

    for table in generic.document_tables:
        if not table.cells:
            continue

        # Build a map of row -> col -> text
        rows_dict: Dict[int, Dict[int, str]] = {}
        for cell in table.cells:
            if cell.row not in rows_dict:
                rows_dict[cell.row] = {}
            rows_dict[cell.row][cell.col] = cell.text.strip()

        if not rows_dict:
            continue

        max_col = max(col for row_data in rows_dict.values() for col in row_data.keys())

        # ── Primary check: meaningful header row ──────────────────────
        headers = [rows_dict.get(1, {}).get(c, "").lower() for c in range(1, max_col + 1)]
        has_qty  = any('qty' in h or 'quantity' in h for h in headers)
        has_desc = any('desc' in h or 'sku' in h or 'item' in h for h in headers)
        has_price = any('amount' in h or 'price' in h or 'rate' in h for h in headers)

        if has_qty and has_desc and has_price:
            logger.info(f"Found line items table (header match) with headers: {headers}")
            return table  # Best possible match — return immediately

        # ── Fallback: detect by data pattern ─────────────────────────
        # Score based on how many data rows (row >= 2) have:
        #   col 2 = non-empty text (description)
        #   last col = numeric value (price/amount)
        data_rows = [rn for rn in rows_dict if rn >= 2]
        if not data_rows:
            continue

        score = 0
        for row_num in data_rows:
            row_data = rows_dict[row_num]
            col2_text = row_data.get(2, "")
            last_col_text = row_data.get(max_col, "").replace('$', '').replace(',', '').strip()
            has_desc_cell = bool(col2_text and not col2_text.replace('.', '').isdigit())
            has_numeric_last = False
            if last_col_text:
                try:
                    float(last_col_text)
                    has_numeric_last = True
                except ValueError:
                    pass
            if has_desc_cell and has_numeric_last:
                score += 1

        match_ratio = score / len(data_rows)
        logger.info(
            f"Table fallback score: {score}/{len(data_rows)} rows match pattern "
            f"(ratio={match_ratio:.2f}, headers={headers})"
        )

        if match_ratio >= 0.5 and score > best_score:
            best_score = score
            best_table = table

    if best_table:
        logger.info(f"Found line items table via data-pattern fallback (score={best_score})")
        # Check if row 1 looks like a misplaced data row (LLM put item in header position).
        # If col 1 of row 1 is blank/numeric AND col 2 is a non-header item description,
        # inject a proper header row and shift everything down by relabelling row 1 as row 0
        # so _parse_table_to_rows will skip it correctly when row_num==1 filter is applied.
        # We handle this by NOT relabelling — instead the expense/invoice transforms
        # already skip row 1, so the misplaced item in row 1 is naturally handled by
        # the HEADER_ROW_RECOVERY below in the transform functions.
        return best_table

    logger.warning("No line items table found")
    return None


def _transform_to_invoice(generic: GenericJSON, bill_subtype: str = None) -> NetSuiteInvoice:
    """
    Transform generic JSON to NetSuite Invoice schema.
    """
    # 1. Extract invoice number
    invoice_number = (
        generic.forms.fields.get("invoice no.") or
        generic.forms.fields.get("invoice no") or
        generic.forms.fields.get("invoice number") or
        generic.forms.invoice_number
    )

    # Generate UUID if no invoice number found
    if invoice_number:
        tran_id = str(invoice_number)
    else:
        tran_id = generate_invoice_id()
        logger.warning(f"No invoice number found, generated: {tran_id}")

    logger.info(f"Invoice number: {tran_id}")

    # 2. Extract and parse date
    date_text = generic.forms.fields.get("date") or generic.forms.date or ""
    tran_date = extract_date(date_text)

    if not tran_date:
        logger.warning(f"Could not parse date from '{date_text}'")
        from datetime import date
        tran_date = date.today().isoformat()

    logger.info(f"Transaction date: {tran_date} (parsed from: {date_text})")

    # 3. Build line items from tables
    items = []

    line_items_table = _find_line_items_table(generic)

    if line_items_table:
        rows_dict = _parse_table_to_rows(line_items_table)

        logger.info(f"Processing {len(rows_dict)} rows from line items table")

        max_col = max(
            (col for row_data in rows_dict.values() for col in row_data.keys()),
            default=4
        )

        # Resolve column layout from headers
        col_layout = _resolve_column_layout(rows_dict, max_col)
        desc_col   = col_layout['desc']
        qty_col    = col_layout['qty']
        rate_col   = col_layout['rate']
        amount_col = col_layout['amount']

        # ── Header-row recovery ───────────────────────────────────────
        _header_keywords = {'qty', 'quantity', 'item', 'description', 'desc',
                            'price', 'rate', 'amount', 'sku', 'total', 'unit',
                            'particulars', 'name', 'nos', 'mrp', 'amt'}
        row1 = rows_dict.get(1, {})
        row1_desc = row1.get(desc_col, "").strip().lower()
        row1_is_real_header = (
            not row1_desc or
            any(kw in row1_desc for kw in _header_keywords)
        )
        start_row = 2 if row1_is_real_header else 1
        if not row1_is_real_header:
            logger.info(f"Row 1 misplaced data row (desc_col={desc_col} text='{row1.get(desc_col,'')}'), including it")

        # Process data rows
        for row_num in sorted(rows_dict.keys()):
            if row_num < start_row:
                continue

            row_data = rows_dict[row_num]

            # Use resolved columns
            quantity_text = row_data.get(qty_col, "") if qty_col else ""
            description   = row_data.get(desc_col, "").strip() if desc_col else ""
            rate_text     = row_data.get(rate_col, "") if rate_col else ""
            amount_text   = row_data.get(amount_col, "") if amount_col else ""

            # If no amount from resolved column, fall back to last numeric col
            if not amount_text:
                for col in range(max_col, 0, -1):
                    if col == desc_col:
                        continue
                    candidate = row_data.get(col, "").strip()
                    if candidate:
                        cleaned = candidate.replace('$', '').replace(',', '').strip()
                        try:
                            float(cleaned)
                            amount_text = candidate
                            if not rate_text:
                                rate_text = candidate
                            break
                        except ValueError:
                            continue

            # Skip empty rows
            if not description and not amount_text:
                logger.debug(f"Skipping empty row {row_num}")
                continue

            # Clean and validate
            quantity = _clean_numeric_string(quantity_text) if quantity_text else 1.0
            if quantity <= 0:
                quantity = 1.0

            description = description.strip()
            if not description:
                description = "Item"

            rate = _clean_numeric_string(rate_text) if rate_text else 0.0
            amount = _clean_numeric_string(amount_text) if amount_text else (quantity * rate)

            if amount <= 0 and not amount_text:
                logger.warning(f"Skipping item with no amount data: {description}")
                continue

            logger.info(f"Line item: {description[:50]} | qty={quantity} | rate={rate} | amount={amount}")

            items.append(InvoiceLineItem(
                item=ItemRef(description=description),
                quantity=quantity,  # Will be auto-formatted by validator
                rate=rate,
                amount=amount
            ))

        logger.info(f"Extracted {len(items)} line items from table")
    else:
        logger.warning("No line items table found in document_tables")

    # 4. Validation
    expected_total = generic.anchors.invoice_total or generic.anchors.total
    if expected_total and items:
        actual_total = sum(_clean_numeric_string(item.amount) for item in items)
        tolerance = max(1.0, expected_total * 0.02)

        logger.info(f"Total validation: actual={actual_total:.2f}, expected={expected_total:.2f}")

        if abs(actual_total - expected_total) > tolerance:
            logger.error(
                f"Invoice total mismatch: items={actual_total:.2f}, "
                f"expected={expected_total:.2f}. Difference: {abs(actual_total - expected_total):.2f}"
            )

    # 5. Fallback if no items
    if not items:
        fallback_amount = expected_total or generic.anchors.subtotal or 0.0
        if fallback_amount > 0:
            logger.warning(f"No items extracted, creating fallback item: ${fallback_amount}")
            items = [InvoiceLineItem(
                item=ItemRef(description="General Items"),
                quantity=1.0,
                rate=fallback_amount,
                amount=fallback_amount
            )]

    # 6. Extract memo
    memo = generic.forms.fields.get("bill to") or generic.forms.vendor or "Unknown Vendor"
    logger.info(f"Memo: {memo}")

    # 7. Build NetSuite Invoice
    return NetSuiteInvoice(
        entity=EntityRef(id="9999"),
        tranDate=tran_date,
        tranId=tran_id,
        memo=memo,
        item=items  # Direct list, no wrapper
    )


def _transform_to_expense(generic: GenericJSON, bill_subtype: str = None) -> NetSuiteExpense:
    """
    Transform generic JSON to NetSuite Expense schema.
    """
    # 1. Extract and parse date
    date_text = generic.forms.fields.get("date") or generic.forms.date or ""
    tran_date = extract_date(date_text)

    if not tran_date:
        from datetime import date
        tran_date = date.today().isoformat()

    # 2. Build expense items
    items = []

    line_items_table = _find_line_items_table(generic)

    if line_items_table:
        rows_dict = _parse_table_to_rows(line_items_table)

        max_col = max(
            (col for row_data in rows_dict.values() for col in row_data.keys()),
            default=3
        )

        # Resolve column layout from headers
        col_layout = _resolve_column_layout(rows_dict, max_col)
        desc_col   = col_layout['desc']
        amount_col = col_layout['amount']

        # ── Header-row recovery ───────────────────────────────────────
        # If the LLM accidentally placed a real item in row 1 (header position),
        # detect it by checking if the desc column of row 1 contains a non-header value.
        _header_keywords = {'qty', 'quantity', 'item', 'description', 'desc',
                            'price', 'rate', 'amount', 'sku', 'total', 'unit',
                            'particulars', 'name', 'nos', 'mrp', 'amt'}
        row1 = rows_dict.get(1, {})
        row1_desc = row1.get(desc_col, "").strip().lower()
        row1_is_real_header = (
            not row1_desc or
            any(kw in row1_desc for kw in _header_keywords)
        )
        start_row = 2 if row1_is_real_header else 1
        if not row1_is_real_header:
            logger.info(f"Row 1 misplaced data row (desc_col={desc_col} text='{row1.get(desc_col,'')}'), including it")

        for row_num in sorted(rows_dict.keys()):
            if row_num < start_row:
                continue

            row_data = rows_dict[row_num]

            # Use resolved desc column
            description = row_data.get(desc_col, "").strip()

            if not description:
                continue

            # Use resolved amount column; fall back to last numeric column
            amount_text = row_data.get(amount_col, "").strip() if amount_col else ""
            if not amount_text:
                for col in range(max_col, 0, -1):
                    if col == desc_col:
                        continue
                    candidate = row_data.get(col, "").strip()
                    if candidate:
                        cleaned = candidate.replace('$', '').replace(',', '').strip()
                        try:
                            float(cleaned)
                            amount_text = candidate
                            break
                        except ValueError:
                            continue

            amount = _clean_numeric_string(amount_text) if amount_text else 0.0

            # Include $0.00 items (e.g. comped dishes) — do NOT skip zero amounts
            category_dict = get_category_for_subtype(bill_subtype)

            items.append(ExpenseItem(
                category=category_dict,
                amount=float(amount),
                memo=description,
                expenseDate=tran_date
            ))

    # 3. Validate against subtotal + repair price-shift errors
    # Use pre-tax subtotal if available, otherwise fall back to total
    expected_subtotal = generic.anchors.subtotal if generic.anchors.subtotal > 0 else None
    if expected_subtotal is None:
        # Try to derive subtotal from total - tax
        if generic.anchors.total > 0 and generic.anchors.tax > 0:
            expected_subtotal = round(generic.anchors.total - generic.anchors.tax, 2)
            logger.info(f"Derived subtotal from total-tax: {expected_subtotal}")
        else:
            expected_subtotal = generic.anchors.total
    if expected_subtotal and items:
        actual_sum = sum(item.amount for item in items)
        tolerance = max(0.5, expected_subtotal * 0.01)

        if abs(actual_sum - expected_subtotal) > tolerance:
            missing_amount = round(expected_subtotal - actual_sum, 2)
            logger.warning(
                f"Expense subtotal mismatch: items={actual_sum:.2f}, "
                f"expected subtotal={expected_subtotal:.2f} (diff={missing_amount:.2f})"
            )

            # ── Price-shift repair ────────────────────────────────────────
            # When the LLM misplaces the first item in the header row with no price,
            # the first item gets amount=0 and the missing amount = subtotal - sum.
            # Strategy: if the FIRST item has amount=0 and there is a positive missing
            # amount, assign it to the first item (best-effort subtotal balancing).
            # This handles the consistent LLM off-by-one pattern without corrupting
            # intentionally zero-priced items elsewhere in the list.
            first_item_zero = items and items[0].amount == 0.0
            if first_item_zero and missing_amount > 0:
                logger.info(
                    f"Price-shift repair: assigning inferred amount {missing_amount} "
                    f"to first item '{items[0].memo}' (was 0.0)"
                )
                items[0] = ExpenseItem(
                    category=items[0].category,
                    amount=missing_amount,
                    memo=items[0].memo,
                    expenseDate=items[0].expenseDate
                )
                new_sum = sum(item.amount for item in items)
                logger.info(f"After repair: sum={new_sum:.2f}, expected={expected_subtotal:.2f}")

    # 4. Fallback if no items
    if not items:
        fallback_amount = expected_subtotal or 0.0
        if fallback_amount > 0:
            logger.warning(f"No expense items extracted, creating fallback: ${fallback_amount}")
            category_dict = get_category_for_subtype(bill_subtype)
            items = [ExpenseItem(
                category=category_dict,
                amount=fallback_amount,
                memo="General Expense",
                expenseDate=tran_date
            )]

    # 5. Extract memo
    memo = generic.forms.vendor or "Business Expenses"

    # 6. Build NetSuite Expense
    return NetSuiteExpense(
        tranDate=tran_date,
        entity=EntityRef(id="9999"),
        memo=memo,
        expense=ExpenseBlock(items=items)
    )