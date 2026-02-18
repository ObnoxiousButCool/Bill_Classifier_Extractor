"""
NetSuite API-compatible JSON schemas - bill_subtype REMOVED.
Supports TWO distinct formats: Invoice and Expense.

CRITICAL CHANGES:
- Invoice 'item' is now a FLAT LIST, not wrapped in ItemBlock
- ItemRef now uses 'description' field instead of 'id'
- Numeric values are formatted as strings with commas and decimals
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional


class EntityRef(BaseModel):
    """Vendor entity reference - NetSuite format."""
    id: str = Field("9999", description="Vendor ID (default 9999)")


# ============ EXPENSE CATEGORY MAPPING ============
EXPENSE_CATEGORY_MAP = {
    "Food & Dining": "980",
    "Transportation": "981",
    "Travel": "982",
    "Utilities": "983",
    "Office Supplies": "984",
    "Professional Services": "985",
    "Maintenance & Repairs": "986",
    "Medical & Healthcare": "987",
    "Entertainment": "988",
    "Retail & Shopping": "989",
    "Other": "662"
}


def get_category_for_subtype(bill_subtype: str) -> dict:
    """
    Map bill subtype to NetSuite expense category.
    Returns ONLY {"id": "xxx"} - no extra fields.
    """
    category_id = EXPENSE_CATEGORY_MAP.get(bill_subtype, "662")
    return {"id": category_id}


# ============ INVOICE SCHEMA ============

class ItemRef(BaseModel):
    """Item reference for invoice lines - uses description, not id."""
    description: str = Field(..., description="Item description text")


class InvoiceLineItem(BaseModel):
    """Line item for NetSuite Invoice."""
    item: ItemRef = Field(..., description="Item with description")
    quantity: str = Field(..., description="Item quantity as formatted string")
    rate: str = Field(..., description="Unit price/rate as formatted string")
    amount: str = Field(..., description="Line total as formatted string")

    @field_validator('quantity', 'rate', 'amount', mode='before')
    @classmethod
    def format_as_string(cls, v):
        """Ensure values are formatted as strings with commas and 2 decimals."""
        if isinstance(v, str):
            # Already a string, clean and reformat
            cleaned = v.replace(',', '').strip()
            try:
                num = float(cleaned)
                return f"{num:,.2f}"
            except ValueError:
                return v
        elif isinstance(v, (int, float)):
            return f"{v:,.2f}"
        return str(v)


class NetSuiteInvoice(BaseModel):
    """
    NetSuite Invoice format - PURE NetSuite fields only.

    CRITICAL: 'item' is a direct list, NOT wrapped in ItemBlock.
    This matches the expected output structure.
    """
    entity: EntityRef = Field(default_factory=EntityRef, description="Vendor reference")
    tranDate: str = Field(..., description="Transaction date in YYYY-MM-DD format")
    tranId: str = Field(..., description="Invoice number/transaction ID")
    memo: str = Field("Unknown Vendor", description="Invoice memo")
    item: List[InvoiceLineItem] = Field(default_factory=list, description="Invoice line items (flat array)")


# ============ EXPENSE SCHEMA ============

class ExpenseItem(BaseModel):
    """Individual expense line item for NetSuite."""
    category: dict = Field(
        default_factory=lambda: {"id": "980"},
        description="Expense category - ONLY id field (no name)"
    )
    amount: float = Field(..., description="Item amount as float")
    memo: str = Field(..., description="Item description")
    expenseDate: str = Field(..., description="Expense date in YYYY-MM-DD format")


class ExpenseBlock(BaseModel):
    """Expense items container."""
    items: List[ExpenseItem] = Field(default_factory=list, description="List of expense items")


class NetSuiteExpense(BaseModel):
    """
    NetSuite Expense format - PURE NetSuite fields only.
    """
    tranDate: str = Field(..., description="Transaction date in YYYY-MM-DD format")
    entity: EntityRef = Field(default_factory=EntityRef, description="Vendor reference")
    memo: str = Field("Business Expenses", description="Transaction memo")
    expense: ExpenseBlock = Field(default_factory=ExpenseBlock, description="Expense itemization")


# ============ HELPER FUNCTIONS ============

def create_invoice_with_items(
    tran_date: str,
    line_items: List[dict],
    memo: str = "Unknown Vendor",
    entity_id: str = "9999",
    tran_id: str = None
) -> NetSuiteInvoice:
    """
    Create NetSuite Invoice with flat item array structure.

    line_items format: [
        {'description': '...', 'quantity': float, 'rate': float, 'amount': float},
        ...
    ]
    """
    invoice_items = []

    for item_data in line_items:
        invoice_items.append(InvoiceLineItem(
            item=ItemRef(description=item_data['description']),
            quantity=item_data['quantity'],
            rate=item_data['rate'],
            amount=item_data['amount']
        ))

    return NetSuiteInvoice(
        entity=EntityRef(id=entity_id),
        tranDate=tran_date,
        tranId=tran_id,
        memo=memo,
        item=invoice_items  # Direct list, no wrapper
    )


def create_expense_with_subtype(
    tran_date: str,
    memo: str,
    items: List[dict],
    bill_subtype: str,
    entity_id: str = "9999"
) -> NetSuiteExpense:
    """
    Create NetSuite Expense with proper category based on bill subtype.
    """
    category = get_category_for_subtype(bill_subtype)

    expense_items = [
        ExpenseItem(
            category=category,
            amount=item["amount"],
            memo=item["memo"],
            expenseDate=tran_date
        )
        for item in items
    ]

    return NetSuiteExpense(
        tranDate=tran_date,
        entity=EntityRef(id=entity_id),
        memo=memo,
        expense=ExpenseBlock(items=expense_items)
    )