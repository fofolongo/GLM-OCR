"""Google Sheets client wrapper using gspread.

Provides easy access to append rows to specific tabs (worksheets)
within a Google Spreadsheet.
"""

import os

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

DEFAULT_CREDENTIALS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "credentials.json"
)


class SheetsClient:
    """Thin wrapper around gspread for appending rows to named tabs."""

    def __init__(self, spreadsheet_name: str, credentials_path: str | None = None):
        creds_path = credentials_path or os.environ.get(
            "GOOGLE_CREDENTIALS_PATH", DEFAULT_CREDENTIALS_PATH
        )
        creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
        self.gc = gspread.authorize(creds)
        self.spreadsheet = self.gc.open(spreadsheet_name)

    def get_or_create_sheet(self, tab_name: str, headers: list[str]) -> gspread.Worksheet:
        """Return the worksheet named *tab_name*, creating it if needed."""
        try:
            ws = self.spreadsheet.worksheet(tab_name)
        except gspread.exceptions.WorksheetNotFound:
            ws = self.spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=len(headers))
            ws.append_row(headers, value_input_option="USER_ENTERED")
        return ws

    def append_row(self, tab_name: str, headers: list[str], row_data: list) -> None:
        """Append a single row to *tab_name*, creating the sheet if needed."""
        ws = self.get_or_create_sheet(tab_name, headers)
        ws.append_row(row_data, value_input_option="USER_ENTERED")
