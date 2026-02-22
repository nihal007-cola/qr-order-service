import time
import re
import os
import json
import numpy as np
import cv2

from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from pyzbar.pyzbar import decode
import gspread


# ================= CONFIG =================

SPREADSHEET_ID = "16LPq3yLMR1B7LO5sWEfD8E14pydyj5dF8W0KJXEs1MU"
WORKSHEET_NAME = "MESSAGE_MAP"
DRIVE_FOLDER_ID = "1Tfv-0A-thHw7o6nVPtm3HQS4__Ogy4Hw"

POLL_INTERVAL = 2

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets"
]

# ==========================================
# ✅ SAFE CREDENTIAL LOADING (Render Secret)
# ==========================================

raw_json = os.environ.get("SERVICE_ACCOUNT_JSON")

if not raw_json:
    raise Exception("SERVICE_ACCOUNT_JSON missing in Render environment")

try:
    creds_dict = json.loads(raw_json)
except Exception as e:
    raise Exception(f"Invalid SERVICE_ACCOUNT_JSON → {e}")

creds = Credentials.from_service_account_info(
    creds_dict,
    scopes=SCOPES
)

drive_service = build("drive", "v3", credentials=creds)
gc = gspread.authorize(creds)
sheet = gc.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)

processed_files = set()

# ================= DUMMY SERVER (Render Requirement) =================

def start_dummy_server():
    port = int(os.environ.get("PORT", 10000))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

        def do_HEAD(self):
            self.send_response(200)
            self.end_headers()

    HTTPServer(("0.0.0.0", port), Handler).serve_forever()

# ================= QR DECODING =================

def extract_design_from_qr(file_id):

    try:
        request = drive_service.files().get_media(fileId=file_id)
        image_bytes = request.execute()

        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            print("❌ Image decode failed")
            return None

        decoded = decode(img)

        if not decoded:
            print("❌ No QR detected")
            return None

        raw_data = decoded[0].data.decode("utf-8")

        print("QR RAW →", raw_data)

        match = re.search(r'\d{3,8}', raw_data)

        return match.group(0) if match else None

    except Exception as e:
        print("QR decode error:", e)
        return None

# ================= SHEET LOGIC =================

def already_logged(design):
    records = sheet.get_all_values()
    return any(len(r) >= 3 and r[2] == design for r in records)

def log_order(design):
    now_ist = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")
    sheet.append_row(["UNKNOWN", "QR_ORDER", design, now_ist])
    print(f"✔ WRITTEN → {design} (IST)")

# ================= DRIVE CLEANUP =================

def delete_file(file_id):
    try:
        drive_service.files().delete(fileId=file_id).execute()
        print("🗑 Deleted")
    except Exception as e:
        print("Delete failed:", e)

# ================= CORE =================

def poll_drive():

    response = drive_service.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents and trashed=false",
        fields="files(id,name)"
    ).execute()

    for file in response.get("files", []):

        file_id = file["id"]
        name = file["name"]

        if file_id in processed_files:
            continue

        processed_files.add(file_id)

        print("NEW IMAGE →", name)

        design = extract_design_from_qr(file_id)

        if not design:
            print("❌ No valid design in QR")
            delete_file(file_id)
            continue

        if already_logged(design):
            print("⚠ Duplicate design")
            delete_file(file_id)
            continue

        print("✅ QR ORDER →", design)

        log_order(design)
        delete_file(file_id)

# ================= RUN =================

def run():

    Thread(target=start_dummy_server, daemon=True).start()

    print("🚀 QR Service Started — polling Drive folder")

    while True:
        try:
            poll_drive()
        except Exception as e:
            print("Polling error:", e)

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run()
