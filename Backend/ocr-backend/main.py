import os

os.environ['FLAGS_enable_pir_api'] = '0'
os.environ['FLAGS_enable_new_executor'] = '0'
os.environ["FLAGS_use_mkldnn"] = "0"

import uuid
import shutil
import requests
import cv2
import numpy as np
from pathlib import Path
from PIL import Image
from fastapi import FastAPI, File, UploadFile, HTTPException, Request, BackgroundTasks
from paddleocr import PaddleOCR
import pytesseract
import uvicorn
import config

app = FastAPI()

UPLOAD_DIR = Path.home() / "bill_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
print(f"✅ Storage initialized at: {UPLOAD_DIR}")

# -------------------------------------------------------------------
# ⭐ CONFIG
# -------------------------------------------------------------------
OTHER_BACKEND_URL = "https://arcade-alan-tim-timothy.trycloudflare.com/process"

# Teams
TEAMS_APP_ID = config.TEAMS_APP_ID
TEAMS_APP_PASSWORD = config.TEAMS_APP_PASSWORD

# WhatsApp
WHATSAPP_ACCESS_TOKEN = config.WHATSAPP_ACCESS_TOKEN
PHONE_NUMBER_ID = config.PHONE_NUMBER_ID
VERIFY_TOKEN = config.VERIFY_TOKEN

# -------------------------------------------------------------------
# OCR INIT
# -------------------------------------------------------------------
_paddle_ocr = PaddleOCR(lang="en", use_textline_orientation=True)


# -------------------------------------------------------------------
# OCR FUNCTION
# -------------------------------------------------------------------
def extract_text_from_image(image_path: Path):
    img = cv2.imread(str(image_path))
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    result = _paddle_ocr.ocr(img_rgb, cls=True)

    lines = []
    if result and result[0]:
        for line in result[0]:
            text, score = line[1]
            if score >= 0.5:
                lines.append(text)

    paddle_text = "\n".join(lines).strip()

    if len(paddle_text) > 10:
        return paddle_text

    pil_img = Image.fromarray(img_rgb).convert("L")
    return pytesseract.image_to_string(pil_img, config="--oem 3 --psm 6")


# -------------------------------------------------------------------
# ⭐ SHARED OCR PIPELINE (BACKGROUND)
# -------------------------------------------------------------------
def process_image_stream_background(file_stream, reply_ctx=None):
    try:
        uid = str(uuid.uuid4())
        img_path = UPLOAD_DIR / f"{uid}.jpg"
        txt_path = UPLOAD_DIR / f"{uid}.txt"

        with img_path.open("wb") as f:
            shutil.copyfileobj(file_stream, f)

        text = extract_text_from_image(img_path)

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)

        # Forward to orchestrator
        try:
            with open(txt_path, "rb") as f:
                requests.post(
                    OTHER_BACKEND_URL,
                    data={"bill_id": uid},
                    files={"file": (txt_path.name, f, "text/plain")},
                    timeout=60
                )
        except Exception as e:
            print("Forwarding error:", e)

        # ⭐ SEND COMPLETION MESSAGE IF NEEDED
        if reply_ctx:

            if reply_ctx["type"] == "teams":

                fresh_token = get_teams_token()

                send_teams_message(
                    reply_ctx["service_url"],
                    reply_ctx["conversation_id"],
                    fresh_token,
                    "✅ Processing complete! Please check the dashboard."
                )
        
            if reply_ctx["type"] == "whatsapp":
                send_whatsapp_message(
                    reply_ctx["from_number"],
                    "✅ Processing complete! Please check the dashboard."
                )

    except Exception as e:
        print("Background processing error:", e)


# -------------------------------------------------------------------
# ⭐ WHATSAPP SEND
# -------------------------------------------------------------------
def send_whatsapp_message(to_number: str, message_text: str):
    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": message_text}
    }

    requests.post(url, headers=headers, json=payload)


# -------------------------------------------------------------------
# ⭐ TEAMS TOKEN + SEND
# -------------------------------------------------------------------
def get_teams_token():
    # url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    url = "https://login.microsoftonline.com/7284c057-4078-4170-92c0-1bcb11c55269/oauth2/v2.0/token"
    payload = {
        "grant_type": "client_credentials",
        "client_id": TEAMS_APP_ID,
        "client_secret": TEAMS_APP_PASSWORD,
        "scope": "https://api.botframework.com/.default"
    }

    r = requests.post(url, data=payload)

    print("Teams token response:", r.text)

    data = r.json()
    # url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

    if "access_token" not in data:
        raise Exception(f"Teams token failed: {data}")

    return data["access_token"]
  
def send_teams_message(
    service_url,
    conversation_id,
    token,
    message_text,
    bot_id,
    reply_to_id=None
):

    if "access_token" not in data:
        raise Exception(f"Teams token failed: {data}")

    return data["access_token"]


def send_teams_message(
        service_url,
        conversation_id,
        token,
        message_text,
        bot_id,
        reply_to_id=None
):
    url = f"{service_url}/v3/conversations/{conversation_id}/activities"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "type": "message",
        "from": {
            "id": bot_id  # ⭐ MUST be recipient.id from incoming activity
        },
        "text": message_text
    }

    if reply_to_id:
        payload["replyToId"] = reply_to_id


    r = requests.post(url, headers=headers, json=payload)
    print("Teams send response:", r.status_code, r.text)
   
# -------------------------------------------------------------------
# ⭐ WHATSAPP VERIFY
# -------------------------------------------------------------------
@app.get("/whatsapp/webhook")
async def verify_whatsapp_webhook(request: Request):
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params.get("hub.challenge"))

    return {"status": "verification failed"}


# -------------------------------------------------------------------
# FRONTEND 1 — WEB UI
# -------------------------------------------------------------------
@app.post("/upload")
async def handle_upload(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    background_tasks.add_task(process_image_stream_background, file.file)
    return {"status": "processing started"}


# -------------------------------------------------------------------
# ⭐ WHATSAPP WEBHOOK
# -------------------------------------------------------------------
@app.post("/whatsapp/webhook")
async def whatsapp_webhook(req: Request, background_tasks: BackgroundTasks):
    data = await req.json()

    try:
        message = data["entry"][0]["changes"][0]["value"]["messages"][0]

        if message["type"] != "image":
            return {"status": "ignored"}

        from_number = message["from"]

        send_whatsapp_message(
            from_number,
            "📄 Image received! Processing your bill..."
        )

        media_id = message["image"]["id"]
        headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}

        media_url = requests.get(
            f"https://graph.facebook.com/v21.0/{media_id}",
            headers=headers
        ).json()["url"]

        img = requests.get(media_url, headers=headers, stream=True)

        background_tasks.add_task(
            process_image_stream_background,
            img.raw,
            {
                "type": "whatsapp",
                "from_number": from_number
            }
        )

        return {"status": "accepted"}

    except Exception as e:
        print("WhatsApp webhook error:", e)
        return {"status": "error"}


# -------------------------------------------------------------------
# ⭐ TEAMS WEBHOOK
# -------------------------------------------------------------------
@app.post("/teams/webhook")
async def teams_webhook(req: Request, background_tasks: BackgroundTasks):
    try:
        data = await req.json()
        print("Incoming Teams activity:", data)

        if data.get("type") != "message":
            return {"status": "ignored"}

        attachments = data.get("attachments") or []
        if not attachments:
            return {"status": "no image"}

        # ⭐ Works for BOTH Web Chat + Teams
        image_url = (
                attachments[0].get("contentUrl")
                or attachments[0].get("content", {}).get("downloadUrl")
        )

        service_url = data["serviceUrl"]
        conversation_id = data["conversation"]["id"]
        activity_id = data["id"]
        bot_id = data["recipient"]["id"]

        # ⭐ ALWAYS get fresh token when sending
        token = get_teams_token()

        # ----------------------------------------------------
        # ✅ Immediate acknowledgement messages
        # ----------------------------------------------------
        # send_teams_message(
        #     service_url,
        #     conversation_id,
        #     token,
        #     "📄 Image received! Processing your bill...",
        #     bot_id,
        #     activity_id
        # )

        send_teams_message(
            service_url,
            conversation_id,
            token,
            "✅ Image submitted, please check the dashboard in some time to see the extracted data.",
            bot_id,
            activity_id
        )

        # ----------------------------------------------------
        # ⭐ Download image using bot token
        # ----------------------------------------------------
        headers = {
            "Authorization": f"Bearer {token}"
        }

        img_response = requests.get(image_url, headers=headers, stream=True)

        # ----------------------------------------------------
        # ⭐ Background OCR processing
        # ----------------------------------------------------
        background_tasks.add_task(
            process_image_stream_background,
            img_response.raw,
            {
                "type": "teams",
                "service_url": service_url,
                "conversation_id": conversation_id
            }
        )

        return {"status": "accepted"}

    except Exception as e:
        print("Teams webhook error:", e)
        return {"status": "error"}


 
# -------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

