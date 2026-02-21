import os
import io
import requests
import pandas as pd
from PIL import Image
import qrcode
from qrcode.constants import ERROR_CORRECT_H

OUTPUT_DIR = "OUTPUT"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def extract_drive_file_id(link):
    if "/file/d/" in link:
        return link.split("/file/d/")[1].split("/")[0]
    if "id=" in link:
        return link.split("id=")[1].split("&")[0]
    raise ValueError("Cannot parse Drive file ID")


def load_image_from_link(link):
    if "drive.google.com" in link:
        file_id = extract_drive_file_id(link)
        link = f"https://drive.google.com/uc?id={file_id}"

    response = requests.get(link, timeout=15)
    response.raise_for_status()

    return Image.open(io.BytesIO(response.content)).convert("RGB")


def generate_qr(value):
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H,   # CRITICAL FOR WHATSAPP
        box_size=8,
        border=2,
    )

    qr.add_data(str(value))
    qr.make(fit=True)

    return qr.make_image(fill_color="black", back_color="white")


def process_excel(excel_path):
    df = pd.read_excel(excel_path)

    for _, row in df.iterrows():

        design_name = row["DESIGN NAME"]   # ← UPDATED SOURCE
        link = row["LINK"]
        desno = row["DESNO"]               # Only for output filename

        try:
            img = load_image_from_link(link)
        except Exception as e:
            print(f"Image load failed for {design_name}: {e}")
            continue

        qr_img = generate_qr(design_name)

        img_w, img_h = img.size

        # WhatsApp-safe QR sizing rule
        qr_target_width = int(img_w * 0.18)
        qr_ratio = qr_img.size[1] / qr_img.size[0]
        qr_target_height = int(qr_target_width * qr_ratio)

        qr_img = qr_img.resize(
            (qr_target_width, qr_target_height),
            Image.NEAREST   # VERY IMPORTANT (prevents blur)
        )

        position = (
            img_w - qr_target_width - 20,
            img_h - qr_target_height - 20,
        )

        img.paste(qr_img, position)

        save_path = os.path.join(OUTPUT_DIR, f"{desno}.jpg")

        img.save(save_path, quality=95, subsampling=0)

        print(f"Processed → {design_name}")


if __name__ == "__main__":
    process_excel("CATALOGUE.xlsx")
