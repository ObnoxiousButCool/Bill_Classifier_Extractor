import re
import json
from pathlib import Path
from typing import Optional

def parse_invoice_txt(txt_path: str, output_json_path: str):
    text = Path(txt_path).read_text(errors="ignore")
    raw = re.sub(r"\s+", " ", text)

    def find(patterns):
        for p in patterns:
            m = re.search(p, raw, re.IGNORECASE)
            if m:
                # If regex has a capturing group, use it
                if m.lastindex:
                    return m.group(1).strip()
                # Otherwise return full match
                return m.group(0).strip()
        return None


    invoice_data = {
        "invoice_number": find([
            r"Invoice\s*#?\s*[:\-]?\s*([A-Z0-9\-]+)",
            r"Invoce#\s*([A-Z0-9\-]+)"
        ]),

        "invoice_date": find([
            r"Invoice Date\s*[:\-]?\s*([\d/]+)",
            r"Date\s*[:\-]?\s*([\d/]+)"
        ]),

        "due_date": find([
            r"Due Date\s*[:\-]?\s*([\d/]+)",
            r"Payment due.*?([\d/]+)"
        ]),

        "seller": {
            "name": find([
                r"(East Repair Inc\.?|TOM GREEN HANDYMAN|WARDIEREINC|Wardiere Inc\.?)"
            ]),
            "address": find([
                r"\d+ .*?(?:NY|ST|City).*?\d{5}"
            ]),
            "email": find([
                r"[\w\.-]+@[\w\.-]+\.\w+"
            ]),
            "phone": find([
                r"Telephone:\s*([\d\sX]+)",
                r"Phone:\s*([\d\-]+)"
            ])
        },

        "buyer": {
            "name": find([
                r"Bill To\s*([A-Za-z\s]+)",
                r"Invoice to:\s*([A-Za-z\s]+)"
            ]),
            "address": find([
                r"Bill To.*?(\d+ .*?\d{5})"
            ])
        },

        "line_items": [],

        "subtotal": find([
            r"Subtotal\s*\$?([\d,]+\.\d{2})"
        ]),

        "tax": find([
            r"Tax\s*\$?([\d,]+\.\d{2})",
            r"Sales Tax.*?\$?([\d,]+\.\d{2})"
        ]),

        "tax_rate": find([
            r"(\d+\.\d+%)"
        ]),

        "total": find([
            r"Total\s*\$?([\d,]+\.\d{2})",
            r"Amount Due\s*\$?([\d,]+\.\d{2})"
        ]),

        "payment_terms": find([
            r"Payment is due within .*?",
            r"Pavment due .*?"
        ]),

        "payment_details": find([
            r"Account No[:\s]*([\d\- ]+)",
            r"Bank Account No.*?([\d ]+)"
        ])
    }

    # -------- Line item extraction (best-effort) --------
    line_item_pattern = re.findall(
        r"([A-Za-z].+?)\s+(\d+)\s+\$?([\d.]+)\s+\$?([\d.]+)",
        text
    )

    for desc, qty, unit_price, amount in line_item_pattern:
        invoice_data["line_items"].append({
            "description": desc.strip(),
            "quantity": int(qty),
            "unit_price": float(unit_price),
            "amount": float(amount)
        })

    # Convert empty line_items to null if nothing extracted
    if not invoice_data["line_items"]:
        invoice_data["line_items"] = None

    with open(output_json_path, "w") as f:
        json.dump(invoice_data, f, indent=4)

    return invoice_data

def find(patterns, text):
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            if m.lastindex:
                return m.group(1).strip()
            return m.group(0).strip()
    return None

def parse_bill_txt(txt_path: str, json_path: str):
    raw = Path(txt_path).read_text(encoding="utf-8", errors="ignore")
    lines = [l.strip() for l in raw.splitlines() if l.strip()]

    data = {
        "document_type": find([r"INVOICE", r"RECEIPT", r"TAX INVOICE", r"TICKET"], raw),
        "bill_number": find([
            r"Bill\s*No\.?\s*([A-Z0-9\-]+)",
            r"BilNo\s*([A-Z0-9\-]+)"
        ], raw),
        "invoice_number": find([
            r"Invoice\s*No\.?\s*([A-Z0-9\-]+)"
        ], raw),
        "date": find([
            r"Date[:\.]?\s*([0-9\/\-A-Za-z]+)"
        ], raw),
        "time": find([
            r"Time\s*([0-9:\. ]+(?:AM|PM)?)"
        ], raw),

        "seller": {
            "name": find([
                r"^([A-Z][A-Z\s&]+)$",
                r"COMPANY NAME",
                r"TCPALLOFINDIA",
                r"MARRIOTT.*",
                r"Theatre in the Park"
            ], raw),
            "address": find([
                r"\d+.*(?:Street|St|Road|Rd|Sector|SEC|City|MI).*?\d{5}",
                r"NOIDA\d{6}",
            ], raw),
            "phone": find([
                r"Ph\s*No\s*([0-9\-]+)",
                r"(\d{3}[- ]\d{3}[- ]\d{4})"
            ], raw),
            "gst_number": find([
                r"GST\s*NO\s*([A-Z0-9]+)"
            ], raw),
        },

        "customer": {
            "name": find([
                r"Customer\s*[:\-]?\s*([A-Za-z ]+)",
                r"Cust\s*([A-Za-z ]+)"
            ], raw),
            "phone": find([
                r"Mob\s*([0-9]{10})"
            ], raw),
        },

        "items": extract_items(lines),

        "subtotal": find([
            r"SUBTOTAL\s*\$?([0-9]+\.[0-9]{2})"
        ], raw),
        "tax": find([
            r"TAX\s*\$?([0-9]+\.[0-9]{2})"
        ], raw),
        "cgst": find([
            r"CGST\s*\$?([0-9]+\.[0-9]{2})"
        ], raw),
        "sgst": find([
            r"SGST\s*\$?([0-9]+\.[0-9]{2})"
        ], raw),
        "total": find([
            r"TOTAL\s*\$?([0-9]+\.[0-9]{2})",
            r"TOTALDUE\s*\$?([0-9]+\.[0-9]{2})",
            r"NetAmount\s*([0-9]+\.[0-9]{2})"
        ], raw),

        "payment": {
            "mode": find([
                r"Credit Card",
                r"VISA",
                r"CASH"
            ], raw),
            "card_last4": find([
                r"CARDNO.*?(\d{4})"
            ], raw),
        },

        "additional_info": {
            "ticket_name": find([
                r"AN\s+[A-Z\s]+"
            ], raw),
            "seat": find([
                r"Seat\s*([A-Z0-9]+)"
            ], raw),
            "section": find([
                r"Section\s*([A-Z0-9]+)"
            ], raw),
            "event_date": find([
                r"\b\d{2}/\d{2}/\d{2}\b"
            ], raw),
        }
    }

    Path(json_path).write_text(
        json.dumps(data, indent=2, ensure_ascii=False)
    )

    return data

def extract_items(lines):
    items = []
    for i in range(len(lines) - 1):
        desc = lines[i]
        price_match = re.search(r"\$?([0-9]+\.[0-9]{2})", lines[i + 1])
        if price_match and len(desc) > 3 and not desc.isupper():
            items.append({
                "description": desc,
                "quantity": None,
                "unit_price": float(price_match.group(1)),
                "amount": float(price_match.group(1))
            })
    return items


uuids = ["0d4d8624-1136-42e2-bfbb-857ca1cdfebb", "2f49db16-97d4-4bd0-8734-0b76f3d0049f","5b7a1335-ea1d-4f9c-b54e-05198273c760","87c23b71-4609-4249-9ce3-271158144fee","791f4868-cf58-4b0c-889a-48d320ce5742","b8bf74b5-944e-4bf2-834f-65c0d05a1d9b","e4ce7abc-bd3c-4d2b-ab3c-a6d66d188f07","e05ceca0-0be5-4f29-922c-1ae4e3845443"]

# uuid = "d27a36dc-38fb-47c4-acaa-65fae6fef862"

for uuid in uuids:
    parsed = parse_bill_txt(f"/home/soham/bill_uploads/{uuid}.txt",f"/home/soham/bill_uploads/{uuid}.json")
    print(parsed)   