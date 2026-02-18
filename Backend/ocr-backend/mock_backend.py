from fastapi import FastAPI, Form, File, UploadFile
import uvicorn

app = FastAPI()

@app.post("/image")
async def receive_image_data(
    id: str = Form(...), 
    text_file: UploadFile = File(...)
):
    # Read the content of the forwarded .txt file
    content = await text_file.read()
    decoded_text = content.decode("utf-8")
    
    print("\n--- 📥 RECEIVED MULTIPART DATA ---")
    print(f"Unique ID: {id}")
    print(f"File Name: {text_file.filename}")
    print(f"Content Snippet: {decoded_text[:100]}...")
    print("----------------------------------\n")
    
    return {"status": "received", "id": id}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)