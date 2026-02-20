import os

os.environ['FLAGS_enable_pir_api'] = '0'
os.environ['FLAGS_enable_new_executor'] = '0'
os.environ["FLAGS_use_mkldnn"] = "0"

import uuid
import shutil
import requests
import cv2
from pathlib import Path
from PIL import Image
from fastapi import FastAPI, File, UploadFile, Request, BackgroundTasks
from pydantic import BaseModel
# from paddleocr import PaddleOCR
# import pytesseract
import uvicorn
import config

app = FastAPI()

UPLOAD_DIR = Path.home() / "bill_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
print(f"✅ Storage initialized at: {UPLOAD_DIR}")

# -------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------
OTHER_BACKEND_URL = "http://localhost:8000/process"

# Teams
TEAMS_APP_ID = config.TEAMS_APP_ID
TEAMS_APP_PASSWORD = config.TEAMS_APP_PASSWORD
MICROSOFT_TENANT_ID = config.MICROSOFT_TENANT_ID

# WhatsApp (⚠ MUST BE PERMANENT TOKEN)
WHATSAPP_ACCESS_TOKEN = config.WHATSAPP_ACCESS_TOKEN
PHONE_NUMBER_ID = config.PHONE_NUMBER_ID
VERIFY_TOKEN = config.VERIFY_TOKEN

# -------------------------------------------------------------------
# OCR INIT
# -------------------------------------------------------------------
# _paddle_ocr = PaddleOCR(lang="en", use_textline_orientation=True)


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
# TEAMS SEND
# -------------------------------------------------------------------
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
        "from": {"id": bot_id},
        "text": message_text
    }

    if reply_to_id:
        payload["replyToId"] = reply_to_id

    r = requests.post(url, headers=headers, json=payload)
    print("Teams send response:", r.status_code, r.text)


# -------------------------------------------------------------------
# WHATSAPP SEND
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

    r = requests.post(url, headers=headers, json=payload)
    print("WhatsApp send response:", r.status_code, r.text)


# -------------------------------------------------------------------
# BACKGROUND PROCESSOR
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

        # Send completion message
        if reply_ctx:

            if reply_ctx["type"] == "teams":
                fresh_token = get_teams_token()
                send_teams_message(
                    reply_ctx["service_url"],
                    reply_ctx["conversation_id"],
                    fresh_token,
                    "✅ Processing complete! Please check the dashboard.",
                    reply_ctx["bot_id"],
                    reply_ctx.get("reply_to_id")
                )

            elif reply_ctx["type"] == "whatsapp":
                send_whatsapp_message(
                    reply_ctx["from_number"],
                    "✅ Processing complete! Please check the dashboard."
                )

    except Exception as e:
        print("Background processing error:", e)


# -------------------------------------------------------------------
# WHATSAPP VERIFY
# -------------------------------------------------------------------
@app.get("/whatsapp/webhook")
async def verify_whatsapp_webhook(request: Request):
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params.get("hub.challenge"))

    return {"status": "verification failed"}


# -------------------------------------------------------------------
# WHATSAPP WEBHOOK
# -------------------------------------------------------------------
@app.post("/whatsapp/webhook")
async def whatsapp_webhook(req: Request, background_tasks: BackgroundTasks):
    try:
        data = await req.json()
        print("Incoming WhatsApp:", data)

        value = data["entry"][0]["changes"][0]["value"]

        # Ignore status updates
        if "messages" not in value:
            return {"status": "no message event"}

        message = value["messages"][0]

        if message.get("type") != "image":
            return {"status": "ignored (not image)"}

        from_number = message["from"]

        send_whatsapp_message(
            from_number,
            "📄 Image received! Processing your bill..."
        )

        # Use direct URL from webhook
        media_url = message["image"].get("url")
        if not media_url:
            raise Exception("No media URL in webhook payload")

        headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}
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
# TEAMS WEBHOOK
# -------------------------------------------------------------------
@app.post("/teams/webhook")
async def teams_webhook(req: Request):
    try:
        data = await req.json()
        print("Incoming Teams activity:", data)

        if data.get("type") != "message":
            return {"status": "ignored"}

        attachments = data.get("attachments") or []
        if not attachments:
            return {"status": "no attachment"}

        service_url = data["serviceUrl"]
        conversation_id = data["conversation"]["id"]
        activity_id = data["id"]
        bot_id = data["recipient"]["id"]

        token = get_teams_token()

        file_streams = []

        for attachment in attachments:
            content_url = attachment.get("contentUrl")
            if not content_url:
                continue

            headers = {"Authorization": f"Bearer {token}"}
            img_response = requests.get(content_url, headers=headers)

            if img_response.status_code == 200:
                file_streams.append(img_response.content)

        if not file_streams:
            send_teams_message(
                service_url,
                conversation_id,
                token,
                "Could not download attachments.",
                bot_id,
                activity_id
            )
            return {"status": "failed"}

        teams_user_name = data["from"]["name"]

        result = submit_bills_to_techno(file_streams, teams_user_name)


        submission_id = result.get("submissionId")

        upload_message = result.get("message", "File uploaded successfully")

        send_teams_message(
            service_url,
            conversation_id,
            token,
            f"{upload_message}",
            bot_id,
            activity_id
        )

        if submission_id:
            import time
            time.sleep(10)

            summary_result = update_submission_summary(submission_id)

            summary_message = summary_result.get("message", "Processing completed.")

            send_teams_message(
                service_url,
                conversation_id,
                token,
                f"{summary_message}",
                bot_id,
                activity_id
            )
        return {"status": "success"}

    except Exception as e:
        print("Teams webhook error:", e)
        return {"status": "error"}

def get_teams_token():
    url = f"https://login.microsoftonline.com/{MICROSOFT_TENANT_ID}/oauth2/v2.0/token"

    payload = {
        "grant_type": "client_credentials",
        "client_id": TEAMS_APP_ID,
        "client_secret": TEAMS_APP_PASSWORD,
        "scope": "https://api.botframework.com/.default"
    }

    r = requests.post(url, data=payload)
    data = r.json()

    if "access_token" not in data:
        raise Exception(f"Teams token failed: {data}")

    return data["access_token"]


# -------------------------------------------------------------------
# WEB UI UPLOAD
# -------------------------------------------------------------------
@app.post("/upload")
async def handle_upload(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    background_tasks.add_task(process_image_stream_background, file.file)
    return {"status": "processing started"}

# -------------------------------------------------------------------
# WHATSAPP MANUAL SEND MODEL (POC)
# -------------------------------------------------------------------
class WhatsAppManualSend(BaseModel):
    phone_number: str
    message: str

# -------------------------------------------------------------------
# MANUAL WHATSAPP SEND API (POC ONLY)
# -------------------------------------------------------------------
@app.post("/send-whatsapp-text")
async def send_whatsapp_text(payload: WhatsAppManualSend):
    try:
        print("Manual WhatsApp send request:", payload)

        # Use your existing function (NO CHANGES)
        send_whatsapp_message(
            payload.phone_number,
            payload.message
        )

        return {
            "status": "success",
            "sent_to": payload.phone_number,
            "message": payload.message
        }

    except Exception as e:
        print("Manual WhatsApp send error:", e)
        return {
            "status": "error",
            "details": str(e)
        }

def submit_bills_to_techno(file_streams, username):
    url = f"{config.TECHNO_BASE_URL}/api/files/SubmitBills"

    files = []
    data = {
        "CompanyId": config.TECHNO_COMPANY_ID,
        "UserName": username
    }

    for i, file_bytes in enumerate(file_streams):
        files.append(
            (
                "Files",
                (f"bill_{i}.jpg", file_bytes, "application/octet-stream")
            )
        )

    headers = {
        "accept": "*/*"
    }

    response = requests.post(url, headers=headers, data=data, files=files)

    print("SubmitBills response:", response.status_code, response.text)

    if response.status_code != 200:
        raise Exception(f"SubmitBills failed: {response.text}")

    return response.json()

def update_submission_summary(submission_id):
    url = f"{config.TECHNO_BASE_URL}/api/files/UpdateSubmitedBillsSummary"

    params = {
        "submissionId": submission_id,
        "token": config.TECHNO_TOKEN
    }

    headers = {
        "accept": "*/*"
    }

    response = requests.post(url, headers=headers, params=params)

    print("UpdateSummary response:", response.status_code, response.text)

    if response.status_code != 200:
        raise Exception(f"UpdateSummary failed: {response.text}")

    return response.json()



# -------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)