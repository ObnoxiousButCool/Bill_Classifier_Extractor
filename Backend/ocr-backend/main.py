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
from paddleocr import PaddleOCR
import pytesseract
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

# WhatsApp (⚠ MUST BE PERMANENT TOKEN)
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
def extract_text_from_image(image_path: Path, confidence_threshold: float = 0.5) -> str:
    img = cv2.imread(str(image_path))
    if img is None: return ""
    h, w, _ = img.shape

    result = _paddle_ocr.ocr(img, cls=True)

    # Clean up memory
    del img
    gc.collect()

    if not result or not result[0]: return ""

    extracted_items = []
    for line in result[0]:
        box = line[0]
        text = line[1][0]
        score = line[1][1]

        if score >= confidence_threshold:
            # We use the average Y to find the row, but keep X precise
            y_center = sum([p[1] for p in box]) / 4
            x_min = min([p[0] for p in box])
            extracted_items.append({'y': y_center, 'x': x_min, 'text': text})

    # 1. Sort primarily by Y, secondarily by X
    extracted_items.sort(key=lambda x: (x['y'], x['x']))

    # 2. Group into rows with a strict but fair tolerance
    rows = []
    if extracted_items:
        current_row = [extracted_items[0]]
        # A 12-15 pixel tolerance is usually the "sweet spot" for 4GB RAM CPU OCR
        row_tolerance = 12

        for i in range(1, len(extracted_items)):
            if abs(extracted_items[i]['y'] - current_row[-1]['y']) <= row_tolerance:
                current_row.append(extracted_items[i])
            else:
                # Before finishing a row, sort it by X (left to right)
                current_row.sort(key=lambda x: x['x'])
                rows.append(current_row)
                current_row = [extracted_items[i]]
        current_row.sort(key=lambda x: x['x'])
        rows.append(current_row)

    # 3. Spatial Rendering
    # Using a step of 8-9 pixels per character prevents text from overlapping
    char_step = 9
    max_chars = int(w / char_step) + 15
    final_output = []

    for row in rows:
        line_canvas = [" "] * max_chars
        for item in row:
            char_pos = int(item['x'] / char_step)
            if char_pos < max_chars:
                text_val = item['text']
                for i, char in enumerate(text_val):
                    if char_pos + i < max_chars:
                        # Only place character if the space is empty to avoid jumbling
                        if line_canvas[char_pos + i] == " ":
                            line_canvas[char_pos + i] = char

        final_output.append("".join(line_canvas).rstrip())

    return "\n".join(final_output)


# -------------------------------------------------------------------
# TEAMS TOKEN
# -------------------------------------------------------------------
def get_teams_token():
    url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

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
async def teams_webhook(req: Request, background_tasks: BackgroundTasks):
    try:
        data = await req.json()
        print("Incoming Teams activity:", data)

        if data.get("type") != "message":
            return {"status": "ignored"}

        attachments = data.get("attachments") or []
        if not attachments:
            return {"status": "no image"}

        image_url = (
            attachments[0].get("contentUrl")
            or attachments[0].get("content", {}).get("downloadUrl")
        )

        if not image_url:
            return {"status": "no image url"}

        service_url = data["serviceUrl"]
        conversation_id = data["conversation"]["id"]
        activity_id = data["id"]
        bot_id = data["recipient"]["id"]

        token = get_teams_token()

        # Immediate acknowledgment
        send_teams_message(
            service_url,
            conversation_id,
            token,
            "📄 Image received! Processing your bill...",
            bot_id,
            activity_id
        )

        headers = {"Authorization": f"Bearer {token}"}
        img_response = requests.get(image_url, headers=headers, stream=True)

        background_tasks.add_task(
            process_image_stream_background,
            img_response.raw,
            {
                "type": "teams",
                "service_url": service_url,
                "conversation_id": conversation_id,
                "bot_id": bot_id,
                "reply_to_id": activity_id
            }
        )

        return {"status": "accepted"}

    except Exception as e:
        print("Teams webhook error:", e)
        return {"status": "error"}


# -------------------------------------------------------------------
# WEB UI UPLOAD
# -------------------------------------------------------------------
@app.post("/upload")
async def handle_upload(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    background_tasks.add_task(process_image_stream_background, file.file)
    return {"status": "processing started"}


# -------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)