"""
Google Sheets integration for the Job CRM tracker.

Authentication: Service account JSON, either via a file path (local)
or base64-encoded string stored in GCP_SA_KEY_B64 (GitHub Actions CI).

Sheet layout (1-indexed columns):
  1: Date Found  2: Position  3: Company  4: Location  5: Work Mode
  6: URL         7: Source    8: Language  9: Status    10: Notes
"""
from __future__ import annotations
import base64
import json
import logging
import os
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

from src.config import (
    GCP_SA_KEY_B64,
    GCP_SA_KEY_FILE,
    GOOGLE_SHEET_ID,
    SHEET_HEADERS,
    SHEET_STATUS_COL,
)
from src.models import Job

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_WORKSHEET_NAME = "Jobs"


def _get_credentials() -> Credentials:
    """Load Google service account credentials from env or file."""
    if GCP_SA_KEY_B64:
        key_dict = json.loads(base64.b64decode(GCP_SA_KEY_B64).decode("utf-8"))
        return Credentials.from_service_account_info(key_dict, scopes=_SCOPES)
    elif GCP_SA_KEY_FILE and os.path.exists(GCP_SA_KEY_FILE):
        return Credentials.from_service_account_file(GCP_SA_KEY_FILE, scopes=_SCOPES)
    else:
        raise EnvironmentError(
            "No Google credentials found. Set GCP_SA_KEY_B64 (CI) "
            "or GOOGLE_SERVICE_ACCOUNT_JSON (local) in your .env file."
        )


def _get_worksheet() -> gspread.Worksheet:
    """Connect to the Google Sheet and return the target worksheet."""
    creds = _get_credentials()
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(GOOGLE_SHEET_ID)

    # Get or create the worksheet
    try:
        ws = spreadsheet.worksheet(_WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(
            title=_WORKSHEET_NAME, rows=1000, cols=len(SHEET_HEADERS)
        )
        # Write header row
        ws.append_row(SHEET_HEADERS, value_input_option="USER_ENTERED")
        # Format header row bold (best-effort)
        try:
            ws.format("A1:J1", {"textFormat": {"bold": True}})
        except Exception:
            pass
        logger.info("Created new worksheet '%s' with headers", _WORKSHEET_NAME)

    return ws


# ─── Public API ───────────────────────────────────────────────────────────────

def ensure_headers() -> None:
    """Ensure the worksheet has the correct header row."""
    ws = _get_worksheet()
    first_row = ws.row_values(1)
    if not first_row or first_row[0] != SHEET_HEADERS[0]:
        ws.insert_row(SHEET_HEADERS, index=1, value_input_option="USER_ENTERED")
        ws.format("A1:J1", {"textFormat": {"bold": True}})
        logger.info("Inserted header row into sheet")


def append_job(job: Job) -> int:
    """
    Append a job as a new row in the sheet.
    Returns the 1-based row index of the newly appended row.
    """
    ws = _get_worksheet()
    row_data = job.to_sheet_row()
    ws.append_row(row_data, value_input_option="USER_ENTERED")

    # Determine the row number of the row we just appended
    all_values = ws.get_all_values()
    sheet_row = len(all_values)  # 1-based index of the last row
    logger.info(
        "Appended job '%s' @ %s to sheet row %d", job.title, job.company, sheet_row
    )
    return sheet_row


def update_status(sheet_row: int, status: str) -> None:
    """Update the Status cell for a given row (1-based)."""
    ws = _get_worksheet()
    ws.update_cell(sheet_row, SHEET_STATUS_COL, status.capitalize())
    logger.info("Updated sheet row %d status → %s", sheet_row, status)


def get_all_records() -> list[dict]:
    """Return all rows as a list of dicts (keyed by header)."""
    ws = _get_worksheet()
    return ws.get_all_records()


def get_status_counts() -> dict[str, int]:
    """Count rows grouped by their Status column value."""
    records = get_all_records()
    counts: dict[str, int] = {}
    for r in records:
        status = str(r.get("Status", "Unknown")).strip()
        counts[status] = counts.get(status, 0) + 1
    return counts
