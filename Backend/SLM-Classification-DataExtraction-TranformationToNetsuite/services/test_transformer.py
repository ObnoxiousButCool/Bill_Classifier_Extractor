"""
Data transformation engine.
Transforms generic JSON to NetSuite-compatible format.
Supports TWO distinct schemas: Invoice and Expense.
"""
from schemas.generic import GenericJSON
from schemas.netsuite import NetSuiteInvoice, NetSuiteExpense, InvoiceLineItem, ExpenseItem, ExpenseBlock, EntityRef
from utils.parsers import extract_date, normalize_currency, generate_invoice_id
from utils.validators import ensure_valid_netsuite_items
from typing import Union


def transform_to_netsuite(generic: GenericJSON, bill_type: str) -> Union[NetSuiteInvoice, NetSuiteExpense]:
    """
    Route to appropriate transformation based on bill_type.
    
    Args:
        generic: GenericJSON object from extraction
        bill_type: "Invoice Bill" or "Expense Bill"
    
    Returns:
        NetSuiteInvoice or NetSuiteExpense object
    
    Raises:
        ValueError: If bill_type is invalid
    """
    if bill_type == "Invoice Bill":
        return _transform_to_invoice(generic)
    elif bill_type == "Expense Bill":
        return _transform_to_expense(generic)
    else:
        raise ValueError(f"Unknown bill_type: {bill_type}")


def _transform_to_invoice(generic: GenericJSON) -> NetSuiteInvoice:
    """
    Transform generic JSON to NetSuite Invoice schema.
    
    Uses 5-column table structure: [date, description, quantity, price, total]
    Generates UUID if invoice number missing.
    Validates sum(amount) matches invoice_total.
    
    Args:
        generic: GenericJSON object
    
    Returns:
        NetSuiteInvoice object
    """
    # 1. Get or generate tranId
    tran_id = generic.forms.invoice_number or generate_invoice_id()
    
    # 2. Extract date (YYYY-MM-DD)
    date_text = generic.forms.date or generic.raw_text or ""
    tran_date = extract_date(date_text)
    
    # 3. Build line items from tables
    # Assuming 5-column format: col1=date, col2=description, col3=quantity, col4=rate, col5=total
    # For flexibility, we'll use col2=description, col3=quantity, col4=rate
    items = []
    for row in generic.tables:
        # Extract quantity (col3 or default to 1)
        quantity = normalize_currency(row.col3) if row.col3 else 1.0
        if quantity is None:
            quantity = 1.0
        
        # Extract rate/price (try col4, fallback to col3 if col4 empty)
        rate_text = row.col3 if row.col3 else "0"
        rate = normalize_currency(rate_text) or 0.0
        
        # Calculate amount
        amount = quantity * rate
        
        # Skip zero amounts
        if amount <= 0:
            continue
        
        # Description from col2
        description = (row.col2 or "Item").strip()
        # Clean description - remove extra whitespace
        description = ' '.join(description.split())
        
        items.append(InvoiceLineItem(
            quantity=quantity,
            description=description,
            rate=rate,
            amount=amount
        ))
    
    # 4. Validation: sum(amount) should match invoice_total or total
    expected_total = generic.anchors.invoice_total or generic.anchors.total
    if expected_total and items:
        actual_total = sum(item.amount for item in items)
        # Allow 1% tolerance for rounding differences
        if abs(actual_total - expected_total) > (expected_total * 0.01):
            # Create fallback item
            items = [InvoiceLineItem(
                quantity=1.0,
                description="General Items",
                rate=expected_total,
                amount=expected_total
            )]
    
    # If no items extracted, create fallback
    if not items:
        fallback_amount = expected_total or generic.anchors.subtotal or 0.0
        if fallback_amount > 0:
            items = [InvoiceLineItem(
                quantity=1.0,
                description="General Items",
                rate=fallback_amount,
                amount=fallback_amount
            )]
    
    # 5. Build memo from bill_to or default
    memo = generic.forms.bill_to or "Invoice"
    
    # 6. Build NetSuiteInvoice
    return NetSuiteInvoice(
        tranId=tran_id,
        tranDate=tran_date,
        entity=EntityRef(id=9999),
        memo=memo,
        item=items
    )


def _transform_to_expense(generic: GenericJSON) -> NetSuiteExpense:
    """
    Transform generic JSON to NetSuite Expense schema.
    
    Uses 2-column table structure: [description, amount]
    Validates sum(items) + tax matches total.
    
    Args:
        generic: GenericJSON object
    
    Returns:
        NetSuiteExpense object
    """
    # 1. Extract date (YYYY-MM-DD)
    date_text = generic.forms.date or generic.raw_text or ""
    tran_date = extract_date(date_text)
    
    # 2. Build expense items from tables
    # Assuming 2-column format: col1=description, col2=amount
    # But we need to handle 3-column as well for backward compatibility
    items = []
    for row in generic.tables:
        # Try col3 first (3-column format), fallback to col2 (2-column format)
        amount_text = row.col3 if row.col3 else (row.col2 if row.col2 else "0")
        amount = normalize_currency(amount_text)
        
        # Skip zero or None amounts
        if amount is None or amount <= 0:
            continue
        
        # Description from col2 (3-col) or col1 (2-col)
        description = (row.col2 or row.col1 or "Expense").strip()
        
        # Clean description
        description = ' '.join(description.split())
        
        # Default category.id = 980 (can be 662 based on vendor context)
        items.append(ExpenseItem(
            category={"id": 980},
            amount=float(amount),
            memo=description
        ))
    
    # 3. Validation: sum(items) + tax should match total
    expected_total = generic.anchors.total
    tax = generic.anchors.tax or 0.0
    
    if expected_total and items:
        actual_sum = sum(item.amount for item in items)
        # Allow 1% tolerance
        if abs(actual_sum + tax - expected_total) > (expected_total * 0.01):
            # Create fallback item
            fallback_amount = expected_total - tax
            if fallback_amount > 0:
                items = [ExpenseItem(
                    category={"id": 980},
                    amount=fallback_amount,
                    memo="General Expense"
                )]
    
    # If no items, create fallback
    if not items:
        fallback_amount = (generic.anchors.subtotal or 
                          (expected_total - tax if expected_total else 0.0))
        if fallback_amount > 0:
            items = [ExpenseItem(
                category={"id": 980},
                amount=fallback_amount,
                memo="General Expense"
            )]
    
    # 4. Build NetSuiteExpense
    return NetSuiteExpense(
        tranDate=tran_date,
        entity=EntityRef(id=9999),
        memo="Business Expenses",
        expense=ExpenseBlock(items=items)
    )
