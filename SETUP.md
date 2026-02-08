# OCR Agent Setup Guide

## 1. Install Dependencies

```bash
pip install -r requirements-agent.txt
```

## 2. Google Cloud Credentials (one-time)

1. Go to https://console.cloud.google.com
2. Create a project (or use an existing one)
3. Enable **Google Sheets API** and **Google Drive API**:
   - Go to APIs & Services → Library
   - Search for "Google Sheets API" → Enable
   - Search for "Google Drive API" → Enable
4. Create a **Service Account**:
   - Go to APIs & Services → Credentials
   - Click "Create Credentials" → "Service Account"
   - Give it a name (e.g. `ocr-agent`)
   - Click "Done"
5. Create a key for the service account:
   - Click on the service account you just created
   - Go to "Keys" tab → "Add Key" → "Create new key" → JSON
   - Download the JSON file
6. Save the JSON file as `credentials.json` in the project root (`GLM-OCR/credentials.json`)

## 3. Google Spreadsheet Setup

1. Create a new Google Spreadsheet (or use an existing one)
2. Name it **"OCR Agent"** (or set `SPREADSHEET_NAME` env var)
3. Share the spreadsheet with the service account email:
   - Open the JSON key file and find the `client_email` field
   - In the spreadsheet, click "Share" and add that email with "Editor" access
4. The agent will auto-create `Logs` and `Expenses` tabs on first use

## 4. Environment Variables (optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `OCR_URL` | `http://localhost:8080/v1/chat/completions` | OCR server endpoint |
| `SPREADSHEET_NAME` | `OCR Agent` | Google Spreadsheet name |
| `GOOGLE_CREDENTIALS_PATH` | `./credentials.json` | Path to service account JSON |
| `AGENT_PORT` | `5055` | Port for the agent Flask server |

## 5. Running

### Start the OCR server first

```bash
python local_server.py
```

### Option A: Agent server (for API/camera use)

```bash
python agent.py serve
```

Then POST images to `http://localhost:5055/process`.

### Option B: Camera app (mobile-friendly)

```bash
python camera_app.py
```

Open `https://<your-ip>:5050` on your phone.

### Option C: Folder watcher

```bash
python watcher.py [WATCH_DIR]
```

Drop images into `./watch/` (default) and they'll be auto-processed.

### Option D: CLI (single image)

```bash
python agent.py path/to/image.jpg
```

## 6. Spreadsheet Tabs

- **Logs** tab: `Timestamp | Source | Raw Text | Summary`
- **Expenses** tab: `Timestamp | Vendor | Date | Items | Total | Payment Method | Raw Text`
