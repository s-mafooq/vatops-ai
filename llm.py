import os
import json
from pydantic import BaseModel, Field

# ── Mode detection ────────────────────────────────────────────────────────────
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
USE_GEMINI = bool(GOOGLE_API_KEY)

if USE_GEMINI:
    import google.generativeai as genai
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash-latest")
    print("LLM mode: Gemini 2.0 Flash (cloud)")
else:
    import ollama
    print("LLM mode: Mistral (local Ollama)")


# ── Pydantic models ───────────────────────────────────────────────────────────
class FieldConfidence(BaseModel):
    supplier_name: float = Field(default=0.0)
    invoice_number: float = Field(default=0.0)
    invoice_date: float = Field(default=0.0)
    total_amount: float = Field(default=0.0)
    vat_amount: float = Field(default=0.0)
    vat_rate: float = Field(default=0.0)


class InvoiceData(BaseModel):
    supplier_name: str = Field(default="")
    invoice_number: str = Field(default="")
    invoice_date: str = Field(default="")
    total_amount: float = Field(default=0.0)
    vat_amount: float = Field(default=0.0)
    vat_rate: float = Field(default=0.0)
    currency: str = Field(default="GBP")
    line_items: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0)
    field_confidence: FieldConfidence = Field(default_factory=FieldConfidence)
    reasoning: str = Field(default="")
    notes: str = Field(default="")


# ── Prompt ────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a UK accounting assistant specialising in invoice data extraction.
Extract invoice data and return ONLY valid JSON with no extra text, no markdown, no code blocks.

Return exactly this structure:
{
  "supplier_name": "string",
  "invoice_number": "string or empty if not found",
  "invoice_date": "DD/MM/YYYY format or empty if not found",
  "total_amount": number or 0 if not found,
  "vat_amount": number or 0 if genuinely absent (zero-rated/exempt is valid),
  "vat_rate": number as percentage e.g. 20 for 20% or 0 if absent,
  "currency": "GBP",
  "line_items": ["item description - £amount"],
  "confidence": number between 0 and 1 (overall confidence),
  "field_confidence": {
    "supplier_name": 0.0 to 1.0,
    "invoice_number": 0.0 to 1.0,
    "invoice_date": 0.0 to 1.0,
    "total_amount": 0.0 to 1.0,
    "vat_amount": 0.0 to 1.0,
    "vat_rate": 0.0 to 1.0
  },
  "reasoning": "Brief explanation of what you found, what was unclear, and why confidence scores are what they are",
  "notes": "Any specific issues, missing fields, or anomalies"
}

UK VAT rules:
- Standard rate: 20%
- Reduced rate: 5%
- Zero-rated and exempt invoices legitimately have £0 VAT — this is NOT an error
- If VAT is missing entirely, set vat_amount to 0 and vat_rate to 0, do not fabricate values

Field confidence scoring guide:
- 1.0: Field is clearly present and unambiguous
- 0.8: Field is present but formatting is unusual
- 0.6: Field is inferred or partially legible
- 0.4: Field is guessed from context
- 0.0: Field is absent or completely unreadable

Never guess amounts. If a total is unclear, set it to 0 and score total_amount confidence as 0.0."""


# ── Extraction ────────────────────────────────────────────────────────────────
def extract_invoice_data(text: str) -> tuple[InvoiceData, bool]:
    try:
        if USE_GEMINI:
            raw = _call_gemini(text)
        else:
            raw = _call_ollama(text)

        raw = _clean_raw(raw)
        data = json.loads(raw)
        data = _fix_confidence(data)

        invoice = InvoiceData(**data)
        return invoice, True

    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
        return InvoiceData(
            notes=f"Failed to parse LLM response: {str(e)}",
            reasoning="Extraction failed — could not parse model output"
        ), False

    except Exception as e:
        print(f"LLM error: {e}")
        return InvoiceData(
            notes=f"LLM error: {str(e)}",
            reasoning="Extraction failed — unexpected error"
        ), False


def _call_gemini(text: str) -> str:
    prompt = f"{SYSTEM_PROMPT}\n\nExtract invoice data from this text:\n\n{text}"
    response = model.generate_content(prompt)
    return response.text.strip()


def _call_ollama(text: str) -> str:
    response = ollama.chat(
        model="mistral",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract invoice data from this text:\n\n{text}"}
        ],
        options={"temperature": 0}
    )
    return response["message"]["content"].strip()


def _clean_raw(raw: str) -> str:
    if "```" in raw:
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else parts[0]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _fix_confidence(data: dict) -> dict:
    # If LLM confused confidence with field_confidence
    if isinstance(data.get("confidence"), dict):
        if not data.get("field_confidence"):
            data["field_confidence"] = data["confidence"]
        data["confidence"] = sum(data["field_confidence"].values()) / len(data["field_confidence"])

    # If field_confidence is missing entirely
    if not data.get("field_confidence"):
        overall = float(data.get("confidence", 0.8))
        data["field_confidence"] = {
            "supplier_name": overall,
            "invoice_number": overall,
            "invoice_date": overall,
            "total_amount": overall,
            "vat_amount": overall,
            "vat_rate": overall,
        }

    data["confidence"] = float(data.get("confidence", 0.8))
    return data