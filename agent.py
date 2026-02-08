"""OCR Agent — orchestrator that reads images, classifies content, and routes
to the Logger or Expenser tool, writing results to Google Sheets.

Also runs as a Flask server with:
    POST /process   — process a single image (base64 or file upload)
    GET  /status    — health check
"""

import base64
import json
import os
import re
import sys

import requests
from flask import Flask, request, jsonify

from sheets_client import SheetsClient
from tools.logger_tool import log_document
from tools.expenser_tool import expense_receipt

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OCR_URL = os.environ.get("OCR_URL", "http://localhost:8080/v1/chat/completions")
SPREADSHEET_NAME = os.environ.get("SPREADSHEET_NAME", "OCR Agent")
CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH", None)

CLASSIFICATION_PROMPT = """\
You are a document classifier. Given the following OCR text extracted from an image, do two things:

1. Classify the document as either "RECEIPT" or "OTHER".
   - RECEIPT: any receipt, invoice, bill, purchase confirmation, or payment record.
   - OTHER: anything else (letter, note, sign, article, etc.).

2. If classified as RECEIPT, extract the following fields (use "Unknown" for any field you cannot determine):
   - vendor: the store or company name
   - date: the date on the receipt
   - items: a list of objects with "name" and "price" for each line item
   - total: the total amount
   - payment_method: how it was paid (cash, card, etc.)

Return ONLY valid JSON in this exact format (no markdown, no extra text):

For RECEIPT:
{"classification": "RECEIPT", "vendor": "...", "date": "...", "items": [{"name": "...", "price": "..."}], "total": "...", "payment_method": "..."}

For OTHER:
{"classification": "OTHER", "summary": "Brief one-line summary of the document content"}

OCR TEXT:
"""


# ---------------------------------------------------------------------------
# Core pipeline functions
# ---------------------------------------------------------------------------

def ocr_image(image_data_url: str) -> str:
    """Send an image (as data URL) to the local OCR server and return raw text."""
    payload = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "OCR this image. Extract all text content."},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            }
        ],
        "max_tokens": 4096,
        "temperature": 0.1,
    }
    resp = requests.post(OCR_URL, json=payload, timeout=300)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def classify_text(raw_text: str) -> dict:
    """Send OCR text back to the model for classification + extraction."""
    payload = {
        "messages": [
            {
                "role": "user",
                "content": CLASSIFICATION_PROMPT + raw_text,
            }
        ],
        "max_tokens": 2048,
        "temperature": 0.1,
    }
    resp = requests.post(OCR_URL, json=payload, timeout=300)
    resp.raise_for_status()
    reply = resp.json()["choices"][0]["message"]["content"]

    # Try to extract JSON from the response
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", reply)
    cleaned = cleaned.strip().rstrip("`")

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        # Fallback: treat as OTHER
        return {"classification": "OTHER", "summary": reply[:100]}


def image_to_data_url(image_path: str) -> str:
    """Read an image file and return a base64 data URL."""
    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    mime = mime_map.get(ext, "image/png")
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{b64}"


def process_image(
    image_input: str,
    source: str = "upload",
    sheets: SheetsClient | None = None,
) -> dict:
    """Full pipeline: OCR → classify → route to logger or expenser.

    Args:
        image_input: Either a file path or a base64 data URL.
        source: Origin of the image (camera / upload / folder).
        sheets: SheetsClient instance. If None, creates one from env.

    Returns:
        dict with action taken and details.
    """
    if sheets is None:
        sheets = SheetsClient(SPREADSHEET_NAME, CREDENTIALS_PATH)

    # Convert file path to data URL if needed
    if not image_input.startswith("data:"):
        image_data_url = image_to_data_url(image_input)
    else:
        image_data_url = image_input

    # Step 1: OCR
    raw_text = ocr_image(image_data_url)

    # Step 2: Classify
    classification = classify_text(raw_text)

    # Step 3: Route
    if classification.get("classification") == "RECEIPT":
        result = expense_receipt(sheets, classification, raw_text)
    else:
        summary = classification.get("summary")
        result = log_document(sheets, raw_text, source=source, summary=summary)

    result["raw_text"] = raw_text
    result["classification"] = classification
    return result


# ---------------------------------------------------------------------------
# Flask server
# ---------------------------------------------------------------------------

app = Flask(__name__)


@app.route("/status", methods=["GET"])
def status():
    return jsonify({"status": "ok", "service": "ocr-agent"})


@app.route("/process", methods=["POST"])
def process_endpoint():
    """Process an image via JSON body (base64) or multipart file upload."""
    source = "upload"

    # Handle multipart file upload
    if "file" in request.files:
        file = request.files["file"]
        if not file.filename:
            return jsonify(error="Empty file"), 400
        ext = os.path.splitext(file.filename)[1].lower()
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }
        mime = mime_map.get(ext, "image/png")
        b64 = base64.b64encode(file.read()).decode()
        image_input = f"data:{mime};base64,{b64}"
    else:
        # Handle JSON body
        data = request.get_json()
        if not data or "image" not in data:
            return jsonify(error="No image provided. Send 'image' as base64 data URL or upload a 'file'."), 400
        image_input = data["image"]
        source = data.get("source", "upload")

    try:
        sheets = SheetsClient(SPREADSHEET_NAME, CREDENTIALS_PATH)
        result = process_image(image_input, source=source, sheets=sheets)
        return jsonify(result)
    except requests.exceptions.ConnectionError:
        return jsonify(error="Cannot reach OCR server. Is local_server.py running on port 8080?"), 502
    except Exception as e:
        return jsonify(error=str(e)), 500


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    """Run as CLI tool or start the Flask server."""
    if len(sys.argv) > 1 and sys.argv[1] != "serve":
        # Process a single image file from CLI
        image_path = sys.argv[1]
        if not os.path.exists(image_path):
            print(f"Error: File not found: {image_path}")
            sys.exit(1)
        source = sys.argv[2] if len(sys.argv) > 2 else "cli"
        try:
            result = process_image(image_path, source=source)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        # Start Flask server
        port = int(os.environ.get("AGENT_PORT", 5055))
        print(f"\n=== OCR Agent Server ===")
        print(f"Running on http://0.0.0.0:{port}")
        print(f"POST /process  — process an image")
        print(f"GET  /status   — health check\n")
        app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
