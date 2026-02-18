"""
Validation guardrails for bill processing.
Ensures data integrity and handles fallback scenarios.
"""
from typing import List, Dict, Optional


def validate_totals(items: List[Dict], tax: Optional[float], total: Optional[float]) -> bool:
    """
    Verify that sum of items + tax equals total.
    
    Args:
        items: List of expense items with 'amount' field
        tax: Tax amount
        total: Total amount
    
    Returns:
        True if validation passes, False otherwise
    """
    if total is None:
        # Can't validate without total
        return True
    
    items_sum = sum(item.get('amount', 0) for item in items)
    tax_amount = tax or 0
    calculated_total = items_sum + tax_amount
    
    # Allow small floating point differences (within 0.01)
    return abs(calculated_total - total) < 0.01


def create_fallback_item(subtotal: float, description: str = "General Expense") -> Dict:
    """
    Create a single fallback expense item when line items are unparseable.
    
    Args:
        subtotal: Amount to use for the fallback item
        description: Description for the item
    
    Returns:
        Dict representing a NetSuite expense item
    """
    return {
        "category": {"id": 662},
        "amount": float(subtotal),
        "memo": description
    }


def ensure_valid_netsuite_items(items: List[Dict], subtotal: Optional[float], 
                                 tax: Optional[float], total: Optional[float]) -> List[Dict]:
    """
    Ensure NetSuite items list is valid.
    If items are empty or validation fails, create fallback item.
    
    Args:
        items: List of extracted expense items
        subtotal: Subtotal amount
        tax: Tax amount
        total: Total amount
    
    Returns:
        Valid list of expense items
    """
    # If we have items and they validate, return them
    if items and validate_totals(items, tax, total):
        return items
    
    # If we have a subtotal, create a fallback item
    if subtotal is not None and subtotal > 0:
        return [create_fallback_item(subtotal)]
    
    # If we have a total, use that instead
    if total is not None and total > 0:
        # Subtract tax to get subtotal
        fallback_amount = total - (tax or 0)
        if fallback_amount > 0:
            return [create_fallback_item(fallback_amount)]
    
    # Last resort: return items as-is or empty list
    return items if items else []
