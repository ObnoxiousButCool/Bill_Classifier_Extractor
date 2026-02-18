# NetSuite Document Processing Orchestrator

A production-ready FastAPI service that processes text documents through an LLM pipeline, classifies them, extracts data into two specific JSON formats, and persists everything to a MySQL database.

## Features

- **FastAPI REST API** with two main endpoints
- **LLM-powered classification** (Invoice Bill vs Expense Bill)
- **Dual JSON extraction**:
  - Generic format (forms + tables + financial anchors)
  - NetSuite API-compatible format
- **Data transformation engine** with:
  - Currency normalization
  - Fuzzy anchor matching (SUBTOTAL, TAX, TOTAL)
  - Line item detection with merge logic
  - Validation guardrails
- **MySQL persistence** with SQLAlchemy ORM

## Project Structure

```
netsuitev2/
├── main.py                 # FastAPI app entry point
├── requirements.txt        # Python dependencies
├── .env.example           # Environment variable template
├── models/
│   └── bill.py            # SQLAlchemy database models
├── schemas/
│   ├── generic.py         # Generic JSON schema
│   ├── netsuite.py        # NetSuite JSON schema
│   └── response.py        # API response schemas
├── services/
│   ├── llm_service.py     # LLM wrapper
│   ├── classifier.py      # Document classification
│   ├── extractor.py       # Generic JSON extraction
│   └── transformer.py     # NetSuite transformation
├── core/
│   ├── config.py          # Settings & environment config
│   └── database.py        # Database connection
└── utils/
    ├── parsers.py         # Currency, date, fuzzy matching
    └── validators.py      # Validation guardrails
```

## Setup

### 1. Install Dependencies

```bash
cd /Users/shlokakulkarni/netsuitev2
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file based on `.env.example`:

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```env
# Database Configuration
DATABASE_URL=mysql+pymysql://root:your_password@localhost:3306/netsuitev2_db

# LLM Configuration (Ollama)
LLM_API_KEY=ollama
LLM_MODEL=llama3.1:8b
LLM_BASE_URL=http://localhost:11434/v1

# Application Settings
DEBUG=true
```

### 3. Set Up MySQL Database

```sql
CREATE DATABASE netsuitev2_db;
```

The tables will be created automatically on first run.

### 4. Run the Server

```bash
uvicorn main:app --reload
python -m uvicorn main:app --reload
```

Server will start at http://localhost:8000

## API Endpoints

### GET /

Fetch all processed bill records.

**Response:**
```json
{
  "bills": [
    {
      "bill_id": "TEST001",
      "bill_type": "Expense Bill",
      "extracted_json": {...},
      "netsuite_json": {...},
      "created_at": "2024-02-04T10:30:00",
      "updated_at": null
    }
  ],
  "count": 1
}
```

### POST /process

Process a new bill.

**Request:**
- Form field `bill_id`: Unique identifier (string)
- File upload `file`: .txt file containing bill text

**Example:**
```bash
curl -X POST http://localhost:8000/process \
  -F "bill_id=TEST001" \
  -F "file=@invoice.txt"
```

**Response:** Same as individual bill object above.

### GET /health

Health check endpoint.

## Data Formats

### Generic JSON Format

```json
{
  "forms": {
    "vendor": "ABC Company Inc.",
    "invoice_number": "INV-12345",
    "date": "2024-02-01"
  },
  "tables": [
    {"col1": "2", "col2": "Widget A", "col3": "$50.00"},
    {"col1": "1", "col2": "Widget B", "col3": "$75.00"}
  ],
  "anchors": {
    "subtotal": 125.0,
    "tax": 12.5,
    "total": 137.5
  }
}
```

### NetSuite JSON Format

```json
{
  "tranDate": "2024-02-01",
  "entity": {"id": 9999},
  "memo": "Business Expenses",
  "expense": {
    "items": [
      {"category": {"id": 662}, "amount": 50.0, "memo": "Widget A"},
      {"category": {"id": 662}, "amount": 75.0, "memo": "Widget B"}
    ]
  }
}
```

## LLM Provider Options

The system supports multiple LLM providers:

**Ollama (default - local):**
```env
LLM_API_KEY=ollama
LLM_MODEL=llama3.1:8b
LLM_BASE_URL=http://localhost:11434/v1
```

**OpenAI:**
```env
LLM_API_KEY=sk-...
LLM_MODEL=gpt-3.5-turbo
# LLM_BASE_URL=  # Leave unset for OpenAI
```

## Error Handling

- **400**: Invalid file format or empty file
- **409**: Duplicate bill_id
- **422**: Validation error (invalid classification, extraction failure)
- **500**: LLM API failure or unexpected errors

## Notes

- Default NetSuite values: `entity.id=9999`, `category.id=662`, `memo="Business Expenses"`
- Date extraction falls back to current date if no date found
- Validation guardrails create fallback "General Expense" items for unparseable data
- All currency values are normalized (symbols removed, converted to float)
