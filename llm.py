import ollama
import json
from pydantic import BaseModel, Field


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


def extract_invoice_data(text: str) -> tuple[InvoiceData, bool]:
    """
    Send extracted text to Mistral, get back structured invoice data.
    Returns (InvoiceData, success_boolean)
    """
    try:
        response = ollama.chat(
            model="mistral",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Extract invoice data from this text:\n\n{text}"}
            ],
            options={"temperature": 0}
        )

        raw = response["message"]["content"].strip()

        # Clean up common LLM formatting issues
        if "```" in raw:
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else parts[0]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        data = json.loads(raw)

        # Fix: if confidence is a dict (LLM confused it with field_confidence), extract or default
        if isinstance(data.get("confidence"), dict):
            # LLM put field scores in confidence — move them to field_confidence
            if not data.get("field_confidence"):
                data["field_confidence"] = data["confidence"]
            data["confidence"] = sum(data["field_confidence"].values()) / len(data["field_confidence"])

        # Fix: if field_confidence is missing, build it from overall confidence
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

        # Ensure confidence is always a plain float
        data["confidence"] = float(data.get("confidence", 0.8))

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