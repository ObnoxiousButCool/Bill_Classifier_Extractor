"""
Data parsing utilities for bill processing.
Includes currency normalization, date extraction, fuzzy matching, and line item detection.
"""
import re
import uuid
from typing import Optional, Dict, Tuple
from datetime import datetime
from fuzzywuzzy import fuzz


def normalize_currency(text: str) -> Optional[float]:
    """
    Remove currency symbols and convert to float.
    Handles both US and European formats:
    - US: 1,234.56 (comma thousands, period decimal)
    - EU: 1.234,56 (period thousands, comma decimal)
    
    Args:
        text: Currency string (e.g., "$1,234.56", "1234.56", "1.234,56")
    
    Returns:
        Float value or None if parsing fails
    """
    if not text:
        return None
    
    try:
        # Remove currency symbols and whitespace
        cleaned = re.sub(r'[$₹€£¥\s]', '', str(text))
        
        # Detect format: if last comma is after last period, it's European format
        last_comma = cleaned.rfind(',')
        last_period = cleaned.rfind('.')
        
        if last_comma > last_period and last_comma != -1:
            # European format: period for thousands, comma for decimal
            # Example: 1.234,56 → 1234.56
            cleaned = cleaned.replace('.', '').replace(',', '.')
        else:
            # US format: comma for thousands, period for decimal
            # Example: 1,234.56 → 1234.56
            cleaned = cleaned.replace(',', '')
        
        return float(cleaned)
    except (ValueError, AttributeError):
        return None


def extract_date(text: str) -> str:
    """
    Extract date from text and format as YYYY-MM-DD.
    Supports European formats including French month names.
    Falls back to current date if no date found.
    
    Args:
        text: Text potentially containing date
    
    Returns:
        Date string in YYYY-MM-DD format
    """
    # French month mappings
    MONTHS_FR = {
        'janv': 1, 'janvier': 1,
        'févr': 2, 'fév': 2, 'fevrier': 2, 'février': 2,
        'mars': 3,
        'avr': 4, 'avril': 4,
        'mai': 5,
        'juin': 6,
        'juil': 7, 'juillet': 7,
        'août': 8, 'aout': 8,
        'sept': 9, 'septembre': 9,
        'oct': 10, 'octobre': 10,
        'nov': 11, 'novembre': 11,
        'déc': 12, 'dec': 12, 'décembre': 12, 'decembre': 12
    }
    
    # Try French format: "lun. oct. 23 2017" or "23 octobre 2017"
    fr_pattern = r'(?:lun|mar|mer|jeu|ven|sam|dim)?\.?\s*(' + '|'.join(MONTHS_FR.keys()) + r')\.?\s+(\d{1,2})\s+(\d{4})'
    match = re.search(fr_pattern, text.lower())
    if match:
        month_name = match.group(1)
        day = int(match.group(2))
        year = int(match.group(3))
        month = MONTHS_FR.get(month_name)
        if month:
            try:
                return datetime(year, month, day).strftime('%Y-%m-%d')
            except ValueError:
                pass
    
    # Common date patterns
    patterns = [
        r'\b(\d{4}[-/]\d{2}[-/]\d{2})\b',  # YYYY-MM-DD or YYYY/MM/DD
        r'\b(\d{2}[-/]\d{2}[-/]\d{4})\b',  # MM-DD-YYYY or DD-MM-YYYY
        r'\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b',  # Various formats
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            date_str = match.group(1)
            # Try to parse with common formats
            date_formats = [
                '%Y-%m-%d', '%Y/%m/%d',
                '%m-%d-%Y', '%m/%d/%Y',
                '%d-%m-%Y', '%d/%m/%Y',
                '%m-%d-%y', '%m/%d/%y',
                '%d-%m-%y', '%d/%m/%y',
            ]
            
            for fmt in date_formats:
                try:
                    parsed_date = datetime.strptime(date_str, fmt)
                    return parsed_date.strftime('%Y-%m-%d')
                except ValueError:
                    continue
    
    # Fallback to current date
    return datetime.now().strftime('%Y-%m-%d')


def fuzzy_match_anchor(text: str, threshold: int = 80) -> Optional[str]:
    """
    Identify financial anchors using fuzzy matching.
    
    Args:
        text: Text to match against anchor keywords
        threshold: Minimum fuzzy match score (0-100)
    
    Returns:
        Anchor type: "SUBTOTAL", "TAX", or "TOTAL", or None
    """
    text_lower = text.lower().strip()
    
    # Define anchor keywords
    anchors = {
        'SUBTOTAL': ['subtotal', 'sub total', 'net amount', 'amount', 'sub-total', 'sous-total'],
        'TAX': ['tax', 'gst', 'vat', 'sales tax', 'service tax', 'tva'],
        'TOTAL': ['total', 'total due', 'amount due', 'balance', 'grand total', 'total amount', 'total ttc'],
    }
    
    best_match = None
    best_score = threshold
    
    for anchor_type, keywords in anchors.items():
        for keyword in keywords:
            score = fuzz.ratio(text_lower, keyword)
            if score > best_score:
                best_score = score
                best_match = anchor_type
    
    return best_match


def parse_line_item(line: str, next_line: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    Detect line items with [Quantity] [Description] [Price] pattern.
    Merges if price appears on next line.
    
    Args:
        line: Current line to parse
        next_line: Next line (for price merging)
    
    Returns:
        Dict with col1 (qty), col2 (desc), col3 (price) or None
    """
    # Pattern: optional number, description, optional price
    # Example: "2 Widget A $50.00" or "Widget A $50.00" or "2 Widget A"
    
    # Try to match: qty desc price
    pattern1 = r'^(\d+(?:\.\d+)?)\s+(.+?)\s+([\$₹€£¥]?\d+(?:[,\.]\d+)*(?:\.\d{2})?)$'
    match = re.match(pattern1, line.strip())
    if match:
        return {
            'col1': match.group(1),
            'col2': match.group(2).strip(),
            'col3': match.group(3)
        }
    
    # Try to match: desc price
    pattern2 = r'^(.+?)\s+([\$₹€£¥]?\d+(?:[,\.]\d+)*(?:\.\d{2})?)$'
    match = re.match(pattern2, line.strip())
    if match:
        return {
            'col1': '',
            'col2': match.group(1).strip(),
            'col3': match.group(2)
        }
    
    # Check if next line contains just a price (merge scenario)
    if next_line:
        price_pattern = r'^([\$₹€£¥]?\d+(?:[,\.]\d+)*(?:\.\d{2})?)$'
        price_match = re.match(price_pattern, next_line.strip())
        if price_match:
            # Current line might have qty + desc
            qty_desc_pattern = r'^(\d+(?:\.\d+)?)\s+(.+)$'
            qty_match = re.match(qty_desc_pattern, line.strip())
            if qty_match:
                return {
                    'col1': qty_match.group(1),
                    'col2': qty_match.group(2).strip(),
                    'col3': price_match.group(1),
                    '_merged': True  # Flag to skip next line
                }
            else:
                # Just description on current line
                return {
                    'col1': '',
                    'col2': line.strip(),
                    'col3': price_match.group(1),
                    '_merged': True
                }
    
    return None


def generate_invoice_id() -> str:
    """
    Generate UUID v4 for missing invoice IDs.
    Ensures unique tranId for NetSuite to prevent duplicate errors.
    
    Returns:
        UUID string in format: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
    """
    return str(uuid.uuid4())

