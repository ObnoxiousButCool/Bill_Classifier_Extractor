import re
from datetime import datetime
import json
from xml.dom import minidom


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
# Purchase Voucher (Invoice)
# -----------------------------

def generate_purchase_xml(file_name,output_file):
    with open(file_name,'r') as f:
        invoice_json = json.load(f)
    forms = invoice_json["forms"]["fields"]

    vendor_name = forms.get("bill to", "Unknown Vendor")
    invoice_no = forms.get("invoice no.", "")
    date_raw = forms.get("date", "")
    subtotal = clean_amount(forms.get("subtotal (usd)", "0"))
    gst = clean_amount(forms.get("sales tax (usd)", "0"))
    total = clean_amount(forms.get("total (usd)", "0"))

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
    save_xml_to_file(fin_xml,output_file)    
    return minidom.parseString(fin_xml).toprettyxml(indent="  ")


# -----------------------------
# Payment Voucher (Expense)
# -----------------------------

def generate_expense_xml(employee_name,file_name,output_file):
    with open(file_name,'r') as f:
        expense_json = json.load(f)
    forms = expense_json["forms"]["fields"]
    category = expense_json.get("bill_category", "General Expense")

    subtotal = clean_amount(forms.get("subtotal", "0"))
    gst = clean_amount(forms.get("tax", "0"))
    total = clean_amount(forms.get("total due", "0"))

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
    save_xml_to_file(fin_xml,output_file) 
    return minidom.parseString(fin_xml).toprettyxml(indent="  ")

import os


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

xml1 = generate_expense_xml("Soham","/home/soham/technollama/netsuitev2/exp1.json","/home/soham/technollama/netsuitev2/exp1.xml") 
xml2 = generate_expense_xml("Soham","/home/soham/technollama/netsuitev2/exp3.json","/home/soham/technollama/netsuitev2/exp3.xml") 
# xml3 = generate_purchase_xml("/home/soham/technollama/netsuitev2/inv1.json","/home/soham/technollama/netsuitev2/inv1.xml")
xml4 = generate_purchase_xml("/home/soham/technollama/netsuitev2/inv2.json","/home/soham/technollama/netsuitev2/inv2.xml")  