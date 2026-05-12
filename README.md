# VatOps AI — UK MTD Invoice Processor

AI-powered invoice processor for UK SMEs preparing for Making Tax Digital (MTD) ITSA compliance.

## What it does
- Extracts supplier, date, totals, VAT from any invoice format (PDF, image, text)
- Classifies UK VAT automatically (20%, 5%, 0%) per HMRC rules
- Fuzzy-matches invoices against bank CSV/Excel exports
- Full audit trail with approve/reject workflow
- Exports MTD CSV, Xero import, and exception reports

## Tech stack
- **Backend:** FastAPI + Python
- **AI:** Ollama + Mistral 7B (local) / Groq Llama3-70B (cloud)
- **OCR:** pdfplumber + PaddleOCR
- **Matching:** rapidfuzz
- **Storage:** SQLite

## Run locally
```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open `http://localhost:8000`

## Built by
Mafooq — [LinkedIn](https://linkedin.com/in/-mafooq)