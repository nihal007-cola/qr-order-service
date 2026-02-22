import time
import re
import os
import json
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
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
# ✅ SAFE CREDENTIAL LOADING
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

# ================= DUMMY SERVER =================

def start_dummy_server():
    port = int(os.environ.get("PORT", 10000))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

    HTTPServer(("0.0.0.0", port), Handler).serve_forever()

# ================= HELPERS =================

def extract_design_number(filename):
    match = re.search(r'\d{3,8}', filename)
    return match.group(0) if match else None


def already_logged(design):
    records = sheet.get_all_values()
    return any(len(r) >= 3 and r[2] == design for r in records)


def log_order(design):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet.append_row(["UNKNOWN", "QR_ORDER", design, now])
    print(f"✔ WRITTEN → {design}")


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

        design = extract_design_number(name)

        if not design:
            print("❌ No design")
            delete_file(file_id)
            continue

        if already_logged(design):
            print("⚠ Duplicate")
            delete_file(file_id)
            continue

        print("QR ORDER →", design)

        log_order(design)
        delete_file(file_id)

# ================= RUN =================

def run():

    Thread(target=start_dummy_server, daemon=True).start()

    print("🚀 QR Service Started — polling:", DRIVE_FOLDER_ID)

    while True:
        try:
            poll_drive()
        except Exception as e:
            print("Polling error:", e)

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    run()
