#!/usr/bin/env python3
"""
GLM-OCR Camera Web App

A self-contained Flask app that serves a mobile-friendly camera UI over HTTPS,
captures photos, and sends them to the GLM-OCR model running on localhost:8080.

Usage:
    python camera_app.py

Then open https://<your-ip>:5050 from any device on the LAN.
Requires local_server.py to be running on port 8080.
"""

import os
import ssl
import subprocess
import json
import requests
from flask import Flask, request, jsonify

from agent import process_image
from sheets_client import SheetsClient

app = Flask(__name__)

CERT_DIR = "/tmp/glmocr_ssl"
CERT_FILE = os.path.join(CERT_DIR, "cert.pem")
KEY_FILE = os.path.join(CERT_DIR, "key.pem")
OCR_URL = "http://localhost:8080/v1/chat/completions"
SPREADSHEET_NAME = os.environ.get("SPREADSHEET_NAME", "OCR Agent")
CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH", None)

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>GLM-OCR Camera</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #111;
    color: #eee;
    min-height: 100dvh;
    display: flex;
    flex-direction: column;
    align-items: center;
}
.header {
    width: 100%;
    padding: 12px 16px;
    background: #1a1a2e;
    text-align: center;
    font-size: 1.1rem;
    font-weight: 600;
    letter-spacing: 0.5px;
}
.container {
    width: 100%;
    max-width: 640px;
    flex: 1;
    display: flex;
    flex-direction: column;
    padding: 12px;
    gap: 12px;
}
.viewfinder {
    position: relative;
    width: 100%;
    aspect-ratio: 4/3;
    background: #000;
    border-radius: 12px;
    overflow: hidden;
}
video, #preview {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
}
#preview { display: none; }
canvas { display: none; }
.controls {
    display: flex;
    gap: 12px;
    justify-content: center;
}
button {
    padding: 14px 32px;
    border: none;
    border-radius: 10px;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.2s;
}
button:active { opacity: 0.7; }
button:disabled { opacity: 0.4; cursor: not-allowed; }
#captureBtn {
    background: #e94560;
    color: #fff;
    flex: 1;
    max-width: 280px;
}
#retakeBtn {
    background: #333;
    color: #eee;
    display: none;
}
.result-box {
    background: #1a1a2e;
    border-radius: 12px;
    padding: 16px;
    min-height: 60px;
    display: none;
    overflow-x: auto;
    line-height: 1.6;
    font-size: 0.95rem;
}
.result-box h1, .result-box h2, .result-box h3 {
    margin: 0.6em 0 0.3em;
    color: #e94560;
}
.result-box p { margin: 0.4em 0; }
.result-box table {
    border-collapse: collapse;
    width: 100%;
    margin: 0.5em 0;
    font-size: 0.85rem;
}
.result-box th, .result-box td {
    border: 1px solid #444;
    padding: 6px 8px;
    text-align: left;
}
.result-box th { background: #2a2a4a; }
.result-box pre {
    background: #0d0d1a;
    padding: 10px;
    border-radius: 6px;
    overflow-x: auto;
}
.result-box code {
    font-family: 'Courier New', monospace;
    font-size: 0.9em;
}
.spinner {
    display: inline-block;
    width: 20px; height: 20px;
    border: 3px solid #555;
    border-top-color: #e94560;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    vertical-align: middle;
    margin-right: 8px;
}
@keyframes spin { to { transform: rotate(360deg); } }
.status {
    text-align: center;
    color: #888;
    font-size: 0.9rem;
    min-height: 1.4em;
}
</style>
</head>
<body>

<div class="header">GLM-OCR Camera</div>

<div class="container">
    <div class="viewfinder">
        <video id="video" autoplay playsinline muted></video>
        <img id="preview" alt="Captured photo">
    </div>

    <canvas id="canvas"></canvas>

    <div class="controls">
        <button id="retakeBtn" onclick="retake()">Retake</button>
        <button id="captureBtn" onclick="capture()">Capture</button>
    </div>

    <div class="status" id="status"></div>
    <div class="result-box" id="result"></div>
</div>

<script>
const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const preview = document.getElementById('preview');
const captureBtn = document.getElementById('captureBtn');
const retakeBtn = document.getElementById('retakeBtn');
const status = document.getElementById('status');
const result = document.getElementById('result');

let stream = null;

async function startCamera() {
    try {
        stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1440 } },
            audio: false
        });
        video.srcObject = stream;
    } catch (err) {
        status.textContent = 'Camera error: ' + err.message;
    }
}

function capture() {
    if (!stream) return;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);

    const dataUrl = canvas.toDataURL('image/png');
    preview.src = dataUrl;
    video.style.display = 'none';
    preview.style.display = 'block';

    captureBtn.disabled = true;
    retakeBtn.style.display = 'inline-block';
    result.style.display = 'none';
    status.innerHTML = '<span class="spinner"></span> Processing (OCR + Agent)...';

    fetch('/ocr', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image: dataUrl })
    })
    .then(r => r.json())
    .then(data => {
        status.textContent = '';
        result.style.display = 'block';
        if (data.error) {
            result.innerHTML = '<p style="color:#f66">Error: ' + escapeHtml(data.error) + '</p>';
        } else {
            result.innerHTML = renderAgentResult(data);
        }
    })
    .catch(err => {
        status.textContent = '';
        result.style.display = 'block';
        result.innerHTML = '<p style="color:#f66">Request failed: ' + escapeHtml(err.message) + '</p>';
    });
}

function retake() {
    video.style.display = 'block';
    preview.style.display = 'none';
    captureBtn.disabled = false;
    retakeBtn.style.display = 'none';
    result.style.display = 'none';
    status.textContent = '';
}

function escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

function renderMarkdown(md) {
    // Minimal markdown renderer: headers, bold, italic, code blocks, tables, paragraphs
    let html = escapeHtml(md);

    // Code blocks
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
    // Inline code
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Tables
    html = html.replace(/((?:^\|.+\|$\n?)+)/gm, function(table) {
        const rows = table.trim().split('\n').filter(r => r.trim());
        if (rows.length < 2) return table;
        // Check for separator row
        const sepIdx = rows.findIndex(r => /^\|[\s\-:|]+\|$/.test(r));
        let thead = '', tbody = '';
        rows.forEach((row, i) => {
            if (i === sepIdx) return;
            const cells = row.split('|').slice(1, -1).map(c => c.trim());
            const tag = (sepIdx > 0 && i < sepIdx) ? 'th' : 'td';
            const tr = '<tr>' + cells.map(c => '<' + tag + '>' + c + '</' + tag + '>').join('') + '</tr>';
            if (tag === 'th') thead += tr; else tbody += tr;
        });
        return '<table>' + (thead ? '<thead>' + thead + '</thead>' : '') + '<tbody>' + tbody + '</tbody></table>';
    });

    // Headers
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

    // Bold & italic
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // Line breaks: consecutive newlines become paragraphs, single newlines become <br>
    html = html.replace(/\n{2,}/g, '</p><p>');
    html = html.replace(/\n/g, '<br>');
    html = '<p>' + html + '</p>';

    // Clean empty paragraphs around block elements
    html = html.replace(/<p>\s*(<h[1-3]>)/g, '$1');
    html = html.replace(/(<\/h[1-3]>)\s*<\/p>/g, '$1');
    html = html.replace(/<p>\s*(<table>)/g, '$1');
    html = html.replace(/(<\/table>)\s*<\/p>/g, '$1');
    html = html.replace(/<p>\s*(<pre>)/g, '$1');
    html = html.replace(/(<\/pre>)\s*<\/p>/g, '$1');
    html = html.replace(/<p>\s*<\/p>/g, '');

    return html;
}

function renderAgentResult(data) {
    let html = '';
    const action = data.action || 'unknown';

    if (action === 'expensed') {
        html += '<h2 style="color:#4ecdc4">Receipt Expensed</h2>';
        html += '<table>';
        html += '<tr><th>Vendor</th><td>' + escapeHtml(data.vendor || 'Unknown') + '</td></tr>';
        html += '<tr><th>Date</th><td>' + escapeHtml(data.date || 'Unknown') + '</td></tr>';
        html += '<tr><th>Total</th><td>' + escapeHtml(String(data.total || 'Unknown')) + '</td></tr>';
        html += '<tr><th>Payment</th><td>' + escapeHtml(data.payment_method || 'Unknown') + '</td></tr>';
        html += '</table>';
        if (data.items && data.items.length > 0) {
            html += '<h3>Items</h3><table><thead><tr><th>Item</th><th>Price</th></tr></thead><tbody>';
            data.items.forEach(function(item) {
                html += '<tr><td>' + escapeHtml(item.name || '') + '</td><td>' + escapeHtml(String(item.price || '')) + '</td></tr>';
            });
            html += '</tbody></table>';
        }
    } else if (action === 'logged') {
        html += '<h2 style="color:#f9a825">Document Logged</h2>';
        html += '<p><strong>Summary:</strong> ' + escapeHtml(data.summary || '') + '</p>';
    } else {
        html += '<h2>Processed</h2>';
    }

    if (data.raw_text) {
        html += '<details style="margin-top:10px"><summary style="cursor:pointer;color:#888">Raw OCR Text</summary>';
        html += '<pre style="margin-top:6px">' + escapeHtml(data.raw_text) + '</pre></details>';
    }

    html += '<p style="color:#888;margin-top:8px;font-size:0.85rem">Written to Google Sheets &rarr; ' + escapeHtml(data.tab || '') + ' tab</p>';
    return html;
}

startCamera();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return HTML_PAGE, 200, {"Content-Type": "text/html"}


@app.route("/ocr", methods=["POST"])
def ocr():
    data = request.get_json()
    if not data or "image" not in data:
        return jsonify(error="No image provided"), 400

    image_data_url = data["image"]

    try:
        sheets = SheetsClient(SPREADSHEET_NAME, CREDENTIALS_PATH)
        result = process_image(image_data_url, source="camera", sheets=sheets)
        return jsonify(result)
    except requests.exceptions.ConnectionError:
        return jsonify(error="Cannot reach OCR server on localhost:8080. Is local_server.py running?"), 502
    except requests.exceptions.Timeout:
        return jsonify(error="OCR server timed out"), 504
    except Exception as e:
        return jsonify(error=str(e)), 500


def generate_ssl_cert():
    """Generate a self-signed SSL certificate using openssl CLI."""
    os.makedirs(CERT_DIR, exist_ok=True)
    if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
        print(f"[SSL] Using existing certificate in {CERT_DIR}")
        return
    print(f"[SSL] Generating self-signed certificate in {CERT_DIR}")
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", KEY_FILE, "-out", CERT_FILE,
            "-days", "365", "-nodes",
            "-subj", "/CN=GLM-OCR Camera App",
        ],
        check=True,
        capture_output=True,
    )
    print("[SSL] Certificate generated.")


if __name__ == "__main__":
    generate_ssl_cert()
    print("\n=== GLM-OCR Camera App ===")
    print("Open https://<your-ip>:5050 from any device on the LAN")
    print("Accept the self-signed certificate warning in your browser.")
    print("Make sure local_server.py is running on port 8080.\n")
    app.run(host="0.0.0.0", port=5050, ssl_context=(CERT_FILE, KEY_FILE), threaded=True)
