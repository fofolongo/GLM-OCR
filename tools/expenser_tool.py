"""Expenser tool — writes receipts/invoices to the Expenses tab in Google Sheets.

Columns: Timestamp | Vendor | Date | Items | Total | Payment Method | Raw Text
"""

import json
from datetime import datetime

from sheets_client import SheetsClient

TAB_NAME = "Expenses"
HEADERS = ["Timestamp", "Vendor", "Date", "Items", "Total", "Payment Method", "Raw Text"]


def expense_receipt(
    sheets: SheetsClient,
    receipt_data: dict,
    raw_text: str,
) -> dict:
    """Append one row to the Expenses tab and return the expensed data."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    vendor = receipt_data.get("vendor", "Unknown")
    date = receipt_data.get("date", "Unknown")
    items = receipt_data.get("items", [])
    total = receipt_data.get("total", "Unknown")
    payment_method = receipt_data.get("payment_method", "Unknown")

    # Format items as readable string for the spreadsheet cell
    if isinstance(items, list):
        items_str = json.dumps(items, ensure_ascii=False)
    else:
        items_str = str(items)

    row = [timestamp, vendor, date, items_str, str(total), payment_method, raw_text]
    sheets.append_row(TAB_NAME, HEADERS, row)

    return {
        "action": "expensed",
        "tab": TAB_NAME,
        "timestamp": timestamp,
        "vendor": vendor,
        "date": date,
        "total": total,
        "items": items,
        "payment_method": payment_method,
    }
