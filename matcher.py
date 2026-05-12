import pandas as pd
from rapidfuzz import fuzz
from dataclasses import dataclass
import os


@dataclass
class MatchResult:
    matched: bool
    bank_description: str
    bank_amount: float
    bank_date: str
    confidence: float
    match_reason: str


def load_bank_csv(uploaded_file) -> pd.DataFrame:
    """
    Load a bank statement CSV or Excel file.
    Handles metadata rows, split debit/credit columns, and comma-formatted amounts.
    """
    if hasattr(uploaded_file, "name"):
        filename = uploaded_file.name
    else:
        filename = str(uploaded_file)

    ext = os.path.splitext(filename)[1].lower()

    # Load raw without headers first to detect structure
    if ext in [".xlsx", ".xls"]:
        raw = pd.read_excel(uploaded_file, header=None)
    else:
        raw = pd.read_csv(uploaded_file, header=None, thousands=",")

    # Find the real header row — look for a row containing date/description-like words
    header_row = 0
    for i, row in raw.iterrows():
        row_lower = [str(v).lower().strip() for v in row.values]
        if any(k in row_lower for k in ["date", "description", "desc", "details", "narrative"]):
            header_row = i
            break

    # Re-read with correct header row
    if ext in [".xlsx", ".xls"]:
        # Reset file pointer if possible
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)
        df = pd.read_excel(uploaded_file, header=header_row)
    else:
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file, header=header_row, thousands=",")

    # Normalise column names
    df.columns = [str(c).strip().lower() for c in df.columns]

    # Drop completely empty rows
    df = df.dropna(how="all")

    # Find date column
    date_col = next((c for c in df.columns if "date" in c and "payment" not in c and "record" not in c and "closed" not in c), None)

    # Find description column
    desc_col = next((c for c in df.columns if any(
        k in c for k in ["description", "desc", "details", "narrative", "payee", "particulars"]
    )), None)

    # Find amount — single amount col first
    amount_col = next((c for c in df.columns if c in ["amount", "value", "sum"]), None)

    # Split debit/credit columns
    deposit_col = next((c for c in df.columns if any(
        k in c for k in ["deposit", "credit", "in"]
    )), None)
    withdrawal_col = next((c for c in df.columns if any(
        k in c for k in ["withdrawal", "withdrawl", "debit", "out"]
    )), None)

    if not date_col or not desc_col:
        raise ValueError(
            f"Could not detect required columns in bank CSV.\n"
            f"Found columns: {list(df.columns)}\n"
            f"Need: a date column and a description column."
        )

    # Build unified amount column
    if amount_col:
        df["amount"] = pd.to_numeric(df[amount_col], errors="coerce").abs()
    elif deposit_col and withdrawal_col:
        deposits = pd.to_numeric(df[deposit_col], errors="coerce").fillna(0)
        withdrawals = pd.to_numeric(df[withdrawal_col], errors="coerce").fillna(0)
        df["amount"] = deposits.where(deposits > 0, withdrawals)
    elif deposit_col:
        df["amount"] = pd.to_numeric(df[deposit_col], errors="coerce").fillna(0)
    elif withdrawal_col:
        df["amount"] = pd.to_numeric(df[withdrawal_col], errors="coerce").fillna(0)
    else:
        df["amount"] = 0.0

    result = df.rename(columns={
        date_col: "date",
        desc_col: "description",
    })[["date", "description", "amount"]].dropna(subset=["description"])

    # Drop rows where description is empty or NaN
    result = result[result["description"].astype(str).str.strip() != ""]
    result = result[result["description"].astype(str).str.lower() != "nan"]

    return result.reset_index(drop=True)

def find_match(
    supplier_name: str,
    total_amount: float,
    invoice_date: str,
    bank_df: pd.DataFrame,
    amount_tolerance: float = 0.02
) -> MatchResult:
    """
    Find the best matching bank transaction for an invoice.
    Uses fuzzy name matching + amount proximity.
    """
    if bank_df is None or bank_df.empty:
        return MatchResult(
            matched=False,
            bank_description="",
            bank_amount=0.0,
            bank_date="",
            confidence=0.0,
            match_reason="No bank data loaded"
        )

    best_score = 0.0
    best_row = None

    for _, row in bank_df.iterrows():
        # Fuzzy match on supplier name vs bank description
        name_score = fuzz.partial_ratio(
            supplier_name.lower(),
            str(row["description"]).lower()
        ) / 100

        # Amount match — within tolerance percentage
        try:
            bank_amount = abs(float(row["amount"]))
            amount_diff = abs(bank_amount - total_amount)
            amount_match = 1.0 if amount_diff <= (total_amount * amount_tolerance) else max(
                0.0, 1.0 - (amount_diff / total_amount)
            )
        except (ValueError, ZeroDivisionError):
            amount_match = 0.0
            bank_amount = 0.0

        # Combined score — name match weighted more heavily
        combined = (name_score * 0.65) + (amount_match * 0.35)

        if combined > best_score:
            best_score = combined
            best_row = row
            best_row_amount = bank_amount

    if best_row is None or best_score < 0.4:
        return MatchResult(
            matched=False,
            bank_description="",
            bank_amount=0.0,
            bank_date="",
            confidence=best_score,
            match_reason="No confident match found — no bank transaction closely matches this supplier name and amount"
        )

    # Build explainable reason
    name_score_pct = int(fuzz.partial_ratio(
        supplier_name.lower(),
        str(best_row["description"]).lower()
    ))
    amount_diff = abs(best_row_amount - total_amount)

    reason = (
        f"Name similarity: {name_score_pct}% match between '{supplier_name}' and '{best_row['description']}'. "
        f"Amount difference: £{amount_diff:.2f}. "
        f"Combined score: {int(best_score * 100)}%."
    )

    return MatchResult(
        matched=best_score >= 0.65,
        bank_description=str(best_row["description"]),
        bank_amount=best_row_amount,
        bank_date=str(best_row["date"]),
        confidence=round(best_score, 2),
        match_reason=reason
    )