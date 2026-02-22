import time
import re
import os
import json
from datetime import datetime
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import gspread

# ================= CONFIG =================

SPREADSHEET_ID = "16LPq3yLMR1B7LO5sWEfD8E14pydyj5dF8W0KJXEs1MU"
WORKSHEET_NAME = "MESSAGE_MAP"

DRIVE_FOLDER_ID = "1Tfv-0A-thHw7o6nVPtm3HQS4__Ogy4Hw"

POLL_INTERVAL = 2  # seconds

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets"
]

# ==========================================

creds = Credentials.from_service_account_info(
    json.loads(os.environ["GOOGLE_CREDS"]),
    scopes=SCOPES
)

drive_service = build("drive", "v3", credentials=creds)
gc = gspread.authorize(creds)

sheet = gc.open_by_key(SPREADSHEET_ID).worksheet(WORKSHEET_NAME)

processed_files = set()

# ================= HELPERS =================

def extract_design_number(filename):
    match = re.search(r'\d{3,8}', filename)
    return match.group(0) if match else None


def already_logged(design):
    records = sheet.get_all_values()
    for row in records:
        if len(row) >= 3 and row[2] == design:
            return True
    return False


def log_order(design):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet.append_row(["UNKNOWN", "QR_ORDER", design, now])
    print(f"✔ WRITTEN → {design}")


def delete_file(file_id):
    try:
        drive_service.files().delete(fileId=file_id).execute()
        print("🗑 Deleted from Drive")
    except Exception as e:
        print("⚠ Could not delete file:", e)

# ================= CORE LOOP =================

def poll_drive():

    global processed_files

    response = drive_service.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents and trashed = false",
        fields="files(id, name)"
    ).execute()

    files = response.get("files", [])

    for file in files:

        file_id = file["id"]
        name = file["name"]

        if file_id in processed_files:
            continue

        processed_files.add(file_id)

        print(f"NEW IMAGE → {name}")

        design = extract_design_number(name)

        if not design:
            print("❌ No design detected")
            delete_file(file_id)
            continue

        if already_logged(design):
            print("⚠ Duplicate design ignored")
            delete_file(file_id)
            continue

        print(f"QR ORDER DETECTED → {design}")

        log_order(design)

        delete_file(file_id)

def run():

    print("QR Service Started — polling Drive folder:", DRIVE_FOLDER_ID)

    while True:
        poll_drive()
        time.sleep(POLL_INTERVAL)

# ================= START =================

if __name__ == "__main__":
    run()
