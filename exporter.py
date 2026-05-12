import pandas as pd
import io
from datetime import datetime


def records_to_dataframe(records: list[dict]) -> pd.DataFrame:
    """Convert a list of approved invoice records to a clean DataFrame."""
    if not records:
        return pd.DataFrame()

    rows = []
    for r in records:
        rows.append({
            "Supplier": r.get("supplier_name", ""),
            "Invoice Number": r.get("invoice_number", ""),
            "Invoice Date": r.get("invoice_date", ""),
            "Total (£)": r.get("total_amount", 0.0),
            "VAT Amount (£)": r.get("vat_amount", 0.0),
            "VAT Rate (%)": r.get("vat_rate", 0.0),
            "VAT Category": r.get("vat_category", ""),
            "Currency": r.get("currency", "GBP"),
            "Flags": r.get("vat_flags", ""),
            "Confidence": r.get("confidence", 0.0),
        })

    return pd.DataFrame(rows)


def to_csv_bytes(records: list[dict]) -> bytes:
    """Export approved records as CSV bytes for Streamlit download."""
    df = records_to_dataframe(records)
    return df.to_csv(index=False).encode("utf-8")


def to_xero_csv_bytes(records: list[dict]) -> bytes:
    """
    Export in Xero Bills import format.
    Based on Xero's standard CSV import template columns.
    """
    if not records:
        return b""

    rows = []
    for r in records:
        rows.append({
            "ContactName": r.get("supplier_name", ""),
            "InvoiceNumber": r.get("invoice_number", ""),
            "InvoiceDate": r.get("invoice_date", ""),
            "DueDate": "",
            "Description": "; ".join(r.get("line_items", [])) or "Invoice",
            "Quantity": 1,
            "UnitAmount": round(
                float(r.get("total_amount", 0)) - float(r.get("vat_amount", 0)), 2
            ),
            "TaxType": _xero_tax_type(r.get("vat_rate", 0)),
            "AccountCode": "429",  # Default purchases account
            "Currency": r.get("currency", "GBP"),
        })

    df = pd.DataFrame(rows)
    return df.to_csv(index=False).encode("utf-8")


def _xero_tax_type(vat_rate: float) -> str:
    """Map VAT rate to Xero tax type string."""
    mapping = {
        20.0: "TAX001",   # Standard rated (20%)
        5.0: "TAX002",    # Reduced rated (5%)
        0.0: "NONE",      # Zero rated / exempt
    }
    return mapping.get(float(vat_rate), "NONE")


def generate_exception_report(records: list[dict]) -> bytes:
    """Export only flagged/exception records as CSV."""
    flagged = [r for r in records if r.get("vat_flags") and r["vat_flags"] != "[]"]
    if not flagged:
        return b"No exceptions found"
    return to_csv_bytes(flagged)