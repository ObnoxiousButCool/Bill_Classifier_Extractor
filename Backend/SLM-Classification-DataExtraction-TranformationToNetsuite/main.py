"""
Main FastAPI application - UPDATED WITH NETSUITE API GUIDANCE

CRITICAL: When sending to NetSuite, extract ONLY netsuite_json:
    payload_to_netsuite = bill_response["netsuite_json"]

DO NOT send:
- bill_id
- bill_type
- extracted_json
- created_at
- updated_at
- netsuite_json (wrapper)

Only send the INNER netsuite_json object to NetSuite API.
"""
import asyncio
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List

from core.database import get_db, init_db
from models.bill import Bill
from schemas.response import BillResponse, BillListResponse
from services.classifier import classify_document
from services.extractor import extract_generic_json
from services.transformer import transform_to_netsuite
from services.tally_transformer import transform_to_tally

# Setup logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("orchestrator")

# Thread pool for running sync LLM calls concurrently
_executor = ThreadPoolExecutor(max_workers=4)

app = FastAPI(
    title="NetSuite Document Processing Orchestrator",
    description="Process bills with LLM classification and dual JSON extraction",
    version="1.0.0"
)


@app.on_event("startup")
def startup_event():
    init_db()
    logger.info("✓ Database initialized")


async def run_in_thread(func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, func, *args)


@app.middleware("http")
async def log_request_time(request: Request, call_next):
    """Global timer for every incoming request."""
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = time.perf_counter() - start_time
    response.headers["X-Process-Time"] = f"{process_time:.4f}s"
    logger.info(f"REQ {request.method} {request.url.path} | Completed in {process_time:.4f}s")
    return response


@app.get("/", response_model=BillListResponse)
def get_all_bills(db: Session = Depends(get_db)):
    bills = db.query(Bill).all()
    return BillListResponse(
        bills=[BillResponse.model_validate(bill) for bill in bills],
        count=len(bills)
    )


@app.post("/process", response_model=BillResponse, status_code=201)
async def process_bill(
        bill_id: str = Form(..., description="Unique bill identifier"),
        file: UploadFile = File(..., description="Text file containing bill content"),
        db: Session = Depends(get_db)
):
    """
    Process a bill and return structured data.

    IMPORTANT: The response contains:
    - extracted_json: Generic extraction (internal use)
    - netsuite_json: NetSuite-compatible payload

    To send to NetSuite API:
        payload = response["netsuite_json"]
        # DO NOT include bill_id, extracted_json, etc.
    """
    overall_start = time.perf_counter()

    if not file.filename.endswith('.txt'):
        raise HTTPException(status_code=400, detail="Invalid file format.")

    try:
        content_bytes = await file.read()
        text_content = content_bytes.decode('utf-8')
        if not text_content.strip():
            raise HTTPException(status_code=400, detail="File is empty.")

        # --- PARALLEL LLM SECTION ---
        parallel_start = time.perf_counter()
        logger.info(f"ID: {bill_id} | Dispatching parallel LLM tasks...")

        classification_task = run_in_thread(classify_document, text_content)
        extraction_task = run_in_thread(extract_generic_json, text_content)

        classification, generic_json = await asyncio.gather(
            classification_task,
            extraction_task
        )

        parallel_end = time.perf_counter() - parallel_start
        logger.info(f"ID: {bill_id} | Parallel LLM tasks finished in {parallel_end:.2f}s")

        # --- SEQUENTIAL TRANSFORMATION ---
        bill_type = classification["bill_type"]
        bill_subtype = classification["bill_subtype"]
        transform_start = time.perf_counter()
        tally_xml = transform_to_tally(generic_json,bill_type,"default_employee")
        netsuite_json = transform_to_netsuite(generic_json, bill_type, bill_subtype)
        transform_end = time.perf_counter() - transform_start
        logger.info(f"ID: {bill_id} | Transformation finished in {transform_end:.4f}s")

        # --- DATABASE PERSISTENCE ---
        # ✅ CRITICAL: model_dump() should exclude bill_subtype via Pydantic config
        # Verify with: netsuite_json.model_dump(exclude={'bill_subtype'})
        bill_record = Bill(
            bill_id=bill_id,
            bill_type=bill_type,
            bill_subtype=bill_subtype,
            extracted_json=generic_json.model_dump(),
            netsuite_json=netsuite_json.model_dump(),
            tally_xml=tally_xml
        )

        db.add(bill_record)
        db.commit()
        db.refresh(bill_record)

        total_time = time.perf_counter() - overall_start
        logger.info(f"ID: {bill_id} | SUCCESS | Total Pipeline Time: {total_time:.2f}s")

        return BillResponse.model_validate(bill_record)

    except IntegrityError:
        db.rollback()
        logger.error(f"ID: {bill_id} | Conflict: Bill ID already exists")
        raise HTTPException(status_code=409, detail="Bill ID already exists.")
    except Exception as e:
        db.rollback()
        logger.error(f"ID: {bill_id} | FAILED | Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@app.post("/send-to-netsuite/{bill_id}")
async def send_to_netsuite(
        bill_id: str,
        db: Session = Depends(get_db)
):
    """
    Example endpoint showing how to send to NetSuite API.

    CRITICAL: Extract ONLY the netsuite_json field, not the entire record.
    """
    # Fetch bill from database
    bill = db.query(Bill).filter(Bill.bill_id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    # ✅ CORRECT: Extract only netsuite_json
    payload_to_netsuite = bill.netsuite_json

    # ❌ WRONG: Do not send the entire bill object
    # payload_to_netsuite = bill.__dict__

    # TODO: Replace with actual NetSuite API call
    # response = requests.post(
    #     "https://your-account.suitetalk.api.netsuite.com/services/rest/record/v1/expense",
    #     headers={
    #         "Authorization": f"Bearer {netsuite_token}",
    #         "Content-Type": "application/json"
    #     },
    #     json=payload_to_netsuite  # ✅ Send ONLY netsuite_json
    # )

    return {
        "message": "Ready to send to NetSuite",
        "payload": payload_to_netsuite,  # Show what would be sent
        "note": "This payload contains ONLY NetSuite-compatible fields"
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)