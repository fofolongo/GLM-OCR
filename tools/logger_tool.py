"""Logger tool — writes non-receipt documents to the Logs tab in Google Sheets.

Columns: Timestamp | Source | Raw Text | Summary
"""

from datetime import datetime

from sheets_client import SheetsClient

TAB_NAME = "Logs"
HEADERS = ["Timestamp", "Source", "Raw Text", "Summary"]


def log_document(
    sheets: SheetsClient,
    raw_text: str,
    source: str = "upload",
    summary: str | None = None,
) -> dict:
    """Append one row to the Logs tab and return the logged data."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if summary is None:
        summary = raw_text[:100] + ("..." if len(raw_text) > 100 else "")

    row = [timestamp, source, raw_text, summary]
    sheets.append_row(TAB_NAME, HEADERS, row)

    return {
        "action": "logged",
        "tab": TAB_NAME,
        "timestamp": timestamp,
        "source": source,
        "summary": summary,
    }
