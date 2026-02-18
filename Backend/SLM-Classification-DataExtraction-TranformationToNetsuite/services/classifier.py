"""
Document classification service.
Classifies bills as Invoice Bill or Expense Bill using LLM.
Also determines the subtype of bill (e.g., food, transport, utilities, etc.)
"""
from services.llm_service import llm_service

CLASSIFICATION_SYSTEM_PROMPT = """You are a bill classifier for a company expense system. Classify documents with TWO pieces of information:

1. BILL TYPE - ONE of these types:
   - "Invoice Bill" - Unpaid vendor bill (company must pay the vendor directly)
   - "Expense Bill" - Employee paid receipt (employee needs reimbursement from company)

2. BILL SUBTYPE - The category of expense:
   - "Food & Dining" - Restaurants, cafes, food delivery, catering
   - "Transportation" - Taxi/cab, ride-sharing, public transit, parking
   - "Travel" - Hotels, flights, accommodation, travel agencies
   - "Utilities" - Electricity, water, gas, internet, phone
   - "Office Supplies" - Stationery, equipment, furniture
   - "Professional Services" - Consulting, legal, accounting, marketing
   - "Maintenance & Repairs" - Equipment repairs, facility maintenance
   - "Medical & Healthcare" - Clinic, hospital, pharmacy, medical supplies
   - "Entertainment" - Events, team activities, client entertainment
   - "Retail & Shopping" - General retail purchases, clothing, electronics
   - "Other" - If none of the above categories fit

DECISION RULES FOR BILL TYPE:

INVOICE BILL indicators:
- "Bill To" with company/customer name
- Payment terms: "Net 15", "Net 30", "Due Date", "Payment due within X days"
- "Invoice #", "Invoice Number", "Invoice Date"
- "PAYMENT COUPON" or "Remittance" section
- "Amount Due", "Invoice Balance", "Total Due"
- No indication of payment already made
- Professional invoice format with terms and conditions

EXPENSE BILL indicators:
- "PAID", "Paid via UPI", "Cash", "Credit Card"
- "Receipt", "Token No", "Order #", "Table #", "Check #"
- "Cashier", "Server", "Biller"
- Restaurant receipts, retail store receipts, taxi receipts
- "Thank you" messages (typical of point-of-sale receipts)
- "Amount Enclosed" field filled in or marked as paid
- Timestamp showing immediate payment (like 13:49)
- No payment terms or due dates

KEY DIFFERENCE:
- Invoice Bill = Payment NOT YET made (has due date/terms)
- Expense Bill = Payment ALREADY made (has payment confirmation)

EXAMPLES:

Example 1:
Bill To: ABA Outreach
Terms: Net 15
PAYMENT COUPON
Invoice Balance: $268.44
Service: Marketing consultation
→ {"bill_type": "Invoice Bill", "bill_subtype": "Professional Services"}

Example 2:
Bill To: John Smith
Invoice Date: 11/02/2019
DUE DATE: 26/02/2019
Payment due within 15 days
Electric Company
→ {"bill_type": "Invoice Bill", "bill_subtype": "Utilities"}

Example 3:
Date: 03/02/26  13:49
Cashier: biller
Token No.: 53
Paid via UPI
Grand Total: 312.00
THANK YOU ** VISIT AGAIN
Restaurant Name: Spice Garden
→ {"bill_type": "Expense Bill", "bill_subtype": "Food & Dining"}

Example 4:
Uber Trip Receipt
Paid via Credit Card
Trip Date: 02/03/2026
Total Fare: $25.50
→ {"bill_type": "Expense Bill", "bill_subtype": "Transportation"}

Example 5:
INVOICE #: US-001
DUE DATE: 26/02/2019
TERMS & CONDITIONS: Payment is due within 15 days
Office Depot - Printer Supplies
→ {"bill_type": "Invoice Bill", "bill_subtype": "Office Supplies"}

RESPONSE FORMAT:
Return ONLY this JSON with no other text, no markdown, no code blocks:
{"bill_type": "Invoice Bill", "bill_subtype": "Professional Services"}
OR
{"bill_type": "Expense Bill", "bill_subtype": "Food & Dining"}

Classify this document:
"""

def classify_document(text: str) -> dict:
    """
    Classify document type and subtype using LLM.
    
    Args:
        text: Raw text content from bill
    
    Returns:
        Dictionary with:
        - bill_type: "Invoice Bill" or "Expense Bill"
        - bill_subtype: Category of expense
    
    Raises:
        ValueError: If classification is invalid
    """
    # Call LLM with classification prompt
    response = llm_service.call_llm(
        prompt=f"Classify this bill:\n\n{text}",
        system_prompt=CLASSIFICATION_SYSTEM_PROMPT,
        response_format="json"
    )
    
    # Parse response
    result = llm_service.parse_json_response(response)
    bill_type = result.get("bill_type", "").strip()
    bill_subtype = result.get("bill_subtype", "").strip()
    
    # Validate classification
    valid_types = ["Invoice Bill", "Expense Bill"]
    valid_subtypes = [
        "Food & Dining", "Transportation", "Travel", "Utilities",
        "Office Supplies", "Professional Services", "Maintenance & Repairs",
        "Medical & Healthcare", "Entertainment", "Retail & Shopping", "Other"
    ]
    
    if bill_type not in valid_types:
        raise ValueError(f"Invalid classification: {bill_type}. Must be one of {valid_types}")
    
    if bill_subtype not in valid_subtypes:
        raise ValueError(f"Invalid subtype: {bill_subtype}. Must be one of {valid_subtypes}")
    
    return {
        "bill_type": bill_type,
        "bill_subtype": bill_subtype
    }

# Test the classifier
result = classify_document(open("inv1.txt", "r").read())
print(f"Bill Type: {result['bill_type']}")
print(f"Bill Subtype: {result['bill_subtype']}")