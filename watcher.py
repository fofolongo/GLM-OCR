"""Folder watcher — monitors a directory for new images and processes them
through the OCR agent pipeline.

Processed files are moved to a /processed subfolder.

Usage:
    python watcher.py [WATCH_DIR]

    WATCH_DIR defaults to ./watch
"""

import os
import shutil
import sys
import time

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from agent import process_image
from sheets_client import SheetsClient

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif"}

SPREADSHEET_NAME = os.environ.get("SPREADSHEET_NAME", "OCR Agent")
CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH", None)


class ImageHandler(FileSystemEventHandler):
    """Process new image files dropped into the watch directory."""

    def __init__(self, processed_dir: str, sheets: SheetsClient):
        self.processed_dir = processed_dir
        self.sheets = sheets

    def on_created(self, event):
        if event.is_directory:
            return

        ext = os.path.splitext(event.src_path)[1].lower()
        if ext not in IMAGE_EXTENSIONS:
            return

        # Brief pause to let file writing finish
        time.sleep(1)

        filepath = event.src_path
        filename = os.path.basename(filepath)
        print(f"[watcher] New image detected: {filename}")

        try:
            result = process_image(filepath, source="folder", sheets=self.sheets)
            action = result.get("action", "unknown")
            print(f"[watcher] {filename} → {action}")

            if result.get("action") == "expensed":
                vendor = result.get("vendor", "?")
                total = result.get("total", "?")
                print(f"           Vendor: {vendor}, Total: {total}")
            else:
                summary = result.get("summary", "")
                print(f"           Summary: {summary[:80]}")

        except Exception as e:
            print(f"[watcher] Error processing {filename}: {e}")
            return

        # Move to processed folder
        dest = os.path.join(self.processed_dir, filename)
        # Avoid overwriting: add suffix if file exists
        if os.path.exists(dest):
            name, ext = os.path.splitext(filename)
            dest = os.path.join(self.processed_dir, f"{name}_{int(time.time())}{ext}")
        shutil.move(filepath, dest)
        print(f"[watcher] Moved to {dest}")


def main():
    watch_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "watch")
    processed_dir = os.path.join(watch_dir, "processed")

    os.makedirs(watch_dir, exist_ok=True)
    os.makedirs(processed_dir, exist_ok=True)

    sheets = SheetsClient(SPREADSHEET_NAME, CREDENTIALS_PATH)
    handler = ImageHandler(processed_dir, sheets)

    observer = Observer()
    observer.schedule(handler, watch_dir, recursive=False)
    observer.start()

    print(f"[watcher] Watching {watch_dir} for new images...")
    print(f"[watcher] Processed files will be moved to {processed_dir}")
    print("[watcher] Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
