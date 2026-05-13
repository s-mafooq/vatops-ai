import os
import json
from pydantic import BaseModel, Field

# ── Mode detection ─────────────────────────────────────────────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

if GROQ_API_KEY:
    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY)
    MODE = "groq"
    print("LLM mode: Groq Llama3 (cloud)")
elif GOOGLE_API_KEY:
    import google.generativeai as genai
    genai.configure(api_key=GOOGLE_API_KEY)
    gemini = genai.GenerativeModel("gemini-2.0-flash-lite")
    MODE = "gemini"
    print("LLM mode: Gemini (cloud)")
else:
    import ollama
    MODE = "ollama"
    print("LLM mode: Mistral (local Ollama)")


# ── Models ─────────────────────────────────────────────────────────────────
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


SYSTEM_PROMPT = """You are a UK accounting assistant specialising in invoice data extraction.
Extract invoice data and return ONLY valid JSON with no extra text, no markdown, no code blocks.

Return exactly this structure:
{
  "supplier_name": "string",
  "invoice_number": "string or empty if not found",
  "invoice_date": "DD/MM/YYYY format or empty if not found",
  "total_amount": number or 0 if not found,
  "vat_amount": number or 0 if genuinely absent,
  "vat_rate": number as percentage e.g. 20 for 20% or 0 if absent,
  "currency": "GBP",
  "line_items": ["item description - £amount"],
  "confidence": number between 0 and 1,
  "field_confidence": {
    "supplier_name": 0.0 to 1.0,
    "invoice_number": 0.0 to 1.0,
    "invoice_date": 0.0 to 1.0,
    "total_amount": 0.0 to 1.0,
    "vat_amount": 0.0 to 1.0,
    "vat_rate": 0.0 to 1.0
  },
  "reasoning": "Brief explanation of confidence scores",
  "notes": "Any issues or anomalies"
}

UK VAT: 20% standard, 5% reduced, 0% zero-rated. Never fabricate amounts."""


def extract_invoice_data(text: str) -> tuple[InvoiceData, bool]:
    try:
        if MODE == "groq":
            raw = _call_groq(text)
        elif MODE == "gemini":
            raw = _call_gemini(text)
        else:
            raw = _call_ollama(text)

        raw = _clean_raw(raw)
        data = json.loads(raw)
        data = _fix_confidence(data)
        return InvoiceData(**data), True

    except json.JSONDecodeError as e:
        return InvoiceData(notes=f"JSON parse error: {e}",
                          reasoning="Extraction failed"), False
    except Exception as e:
        return InvoiceData(notes=f"Error: {e}",
                          reasoning="Extraction failed"), False


def _call_groq(text: str) -> str:
    response = client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract invoice data:\n\n{text}"}
        ],
        temperature=0,
        max_tokens=1000,
    )
    return response.choices[0].message.content.strip()


def _call_gemini(text: str) -> str:
    prompt = f"{SYSTEM_PROMPT}\n\nExtract invoice data:\n\n{text}"
    response = gemini.generate_content(prompt)
    return response.text.strip()


def _call_ollama(text: str) -> str:
    response = ollama.chat(
        model="mistral",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract invoice data:\n\n{text}"}
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
    if isinstance(data.get("confidence"), dict):
        if not data.get("field_confidence"):
            data["field_confidence"] = data["confidence"]
        data["confidence"] = sum(data["field_confidence"].values()) / len(data["field_confidence"])
    if not data.get("field_confidence"):
        overall = float(data.get("confidence", 0.8))
        data["field_confidence"] = {k: overall for k in
            ["supplier_name","invoice_number","invoice_date","total_amount","vat_amount","vat_rate"]}
    data["confidence"] = float(data.get("confidence", 0.8))
    return data