import re
from datetime import datetime
import json
from xml.dom import minidom
import os


# -----------------------------
# Utility Functions
# -----------------------------

def clean_amount(amount_str):
    """
    Removes currency symbols and commas.
    Returns float.
    """
    if not amount_str:
        return 0.0
    cleaned = re.sub(r"[^\d.]", "", amount_str)
    return float(cleaned) if cleaned else 0.0


def format_date(date_str):
    """
    Converts date like '14-Aug-2009' to '20090814'
    """
    try:
        dt = datetime.strptime(date_str, "%d-%b-%Y")
        return dt.strftime("%Y%m%d")
    except:
        # fallback to today
        return datetime.today().strftime("%Y%m%d")


def create_envelope(voucher_xml):
    return f"""
<ENVELOPE>
    <HEADER>
        <TALLYREQUEST>Import Data</TALLYREQUEST>
    </HEADER>
    <BODY>
        <IMPORTDATA>
            <REQUESTDESC>
                <REPORTNAME>Vouchers</REPORTNAME>
            </REQUESTDESC>
            <REQUESTDATA>
                <TALLYMESSAGE>
                    {voucher_xml}
                </TALLYMESSAGE>
            </REQUESTDATA>
        </IMPORTDATA>
    </BODY>
</ENVELOPE>
"""


# -----------------------------
# SAFE GET HELPER
# -----------------------------
def safe_get(obj, key, default=None):
    """
    Works for both dict and object attributes.
    """
    if obj is None:
        return default

    # If dict
    if isinstance(obj, dict):
        return obj.get(key, default)

    # If object with attribute
    return getattr(obj, key, default)


# -----------------------------
# PURCHASE VOUCHER
# -----------------------------
def generate_purchase_xml(invoice_json):

    # Handle dict OR object
    forms_obj = safe_get(invoice_json, "forms", {})
    fields = safe_get(forms_obj, "fields", {})

    vendor_name = safe_get(fields, "bill to", "Unknown Vendor")
    invoice_no = safe_get(fields, "invoice no.", "")
    date_raw = safe_get(fields, "date", "")

    subtotal = clean_amount(safe_get(fields, "subtotal (usd)", "0"))
    gst = clean_amount(safe_get(fields, "sales tax (usd)", "0"))
    total = clean_amount(safe_get(fields, "total (usd)", "0"))

    date_formatted = format_date(date_raw)

    voucher = f"""
<VOUCHER VCHTYPE="Purchase" ACTION="Create" OBJVIEW="Invoice Voucher View">
    <DATE>{date_formatted}</DATE>
    <VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME>
    <REFERENCE>{invoice_no}</REFERENCE>
    <PARTYLEDGERNAME>{vendor_name}</PARTYLEDGERNAME>
    <NARRATION>Imported Invoice {invoice_no}</NARRATION>

    <ALLLEDGERENTRIES.LIST>
        <LEDGERNAME>Purchase Account</LEDGERNAME>
        <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
        <AMOUNT>-{subtotal}</AMOUNT>
    </ALLLEDGERENTRIES.LIST>

    <ALLLEDGERENTRIES.LIST>
        <LEDGERNAME>Input GST</LEDGERNAME>
        <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
        <AMOUNT>-{gst}</AMOUNT>
    </ALLLEDGERENTRIES.LIST>

    <ALLLEDGERENTRIES.LIST>
        <LEDGERNAME>{vendor_name}</LEDGERNAME>
        <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
        <AMOUNT>{total}</AMOUNT>
    </ALLLEDGERENTRIES.LIST>

</VOUCHER>
"""

    fin_xml = create_envelope(voucher)
    return minidom.parseString(fin_xml).toprettyxml(indent="  ")


# -----------------------------
# EXPENSE / PAYMENT VOUCHER
# -----------------------------
def generate_expense_xml(expense_json, employee_name):

    # Handle dict OR object
    forms_obj = safe_get(expense_json, "forms", {})
    fields = safe_get(forms_obj, "fields", {})

    category = safe_get(expense_json, "billCategory", "General Expense")

    subtotal = clean_amount(safe_get(fields, "subtotal", "0"))
    gst = clean_amount(safe_get(fields, "tax", "0"))
    total = clean_amount(safe_get(fields, "total due", "0"))

    date_formatted = datetime.today().strftime("%Y%m%d")

    expense_ledger = f"{category} Expense"

    voucher = f"""
<VOUCHER VCHTYPE="Payment" ACTION="Create">
    <DATE>{date_formatted}</DATE>
    <VOUCHERTYPENAME>Payment</VOUCHERTYPENAME>
    <PARTYLEDGERNAME>{employee_name}</PARTYLEDGERNAME>
    <NARRATION>Expense Reimbursement - {category}</NARRATION>

    <ALLLEDGERENTRIES.LIST>
        <LEDGERNAME>{expense_ledger}</LEDGERNAME>
        <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
        <AMOUNT>-{subtotal}</AMOUNT>
    </ALLLEDGERENTRIES.LIST>

    <ALLLEDGERENTRIES.LIST>
        <LEDGERNAME>Input GST</LEDGERNAME>
        <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
        <AMOUNT>-{gst}</AMOUNT>
    </ALLLEDGERENTRIES.LIST>

    <ALLLEDGERENTRIES.LIST>
        <LEDGERNAME>Bank Account</LEDGERNAME>
        <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
        <AMOUNT>{total}</AMOUNT>
    </ALLLEDGERENTRIES.LIST>

</VOUCHER>
"""

    fin_xml = create_envelope(voucher)
    return minidom.parseString(fin_xml).toprettyxml(indent="  ")


def save_xml_to_file(xml_string, file_path):
    """
    Saves XML string to a file.
    Automatically creates folder if not exists.
    Adds XML declaration at the top.
    """
    # Add XML declaration
    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_string.strip()

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(xml_content)

    print(f"XML saved successfully at: {file_path}")


def transform_to_tally(generic_json,bill_type,employee_name):
    if bill_type == "Invoice Bill":
        return generate_purchase_xml(generic_json)
    elif bill_type == "Expense Bill":
        return generate_expense_xml(generic_json,employee_name)
    else:
        raise ValueError(f"Unknown bill_type: {bill_type}")