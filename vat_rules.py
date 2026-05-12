from dataclasses import dataclass, field

UK_VAT_RATES = [20.0, 5.0, 0.0]

@dataclass
class VATResult:
    rate: float
    category: str
    is_valid: bool
    flags: list[str]
    certainty: str  # "confirmed", "inferred", "missing", "unknown"


def snap_vat_rate(total_amount: float, vat_amount: float, raw_rate: float) -> float:
    if total_amount > 0 and vat_amount > 0:
        net = total_amount - vat_amount
        if net > 0:
            calculated_rate = round((vat_amount / net) * 100, 2)
            for known_rate in UK_VAT_RATES:
                if abs(calculated_rate - known_rate) <= 2.0:
                    return known_rate

    for known_rate in UK_VAT_RATES:
        if abs(raw_rate - known_rate) <= 3.0:
            return known_rate

    return raw_rate


def classify_vat(
    total_amount: float,
    vat_amount: float,
    raw_rate: float,
    vat_field_confidence: float = 1.0
) -> VATResult:
    """
    Classify VAT treatment with explicit certainty levels.

    Certainty levels:
    - confirmed: VAT data present and internally consistent
    - inferred:  VAT absent but supplier/amount pattern suggests zero-rated
    - missing:   VAT absent and confidence is low — extraction likely failed
    - unknown:   Unrecognised rate or conflicting data
    """
    flags = []

    # ── Case 1: VAT data is absent AND confidence is low ─────────────────────
    # This is the key fix — low confidence + no VAT = missing, not zero-rated
    if vat_amount == 0 and raw_rate == 0 and vat_field_confidence < 0.5:
        return VATResult(
            rate=0.0,
            category="VAT not detected",
            is_valid=False,
            flags=[
                "VAT information was not found in this document. "
                "This may be a zero-rated or exempt supply, or VAT data may have failed to extract. "
                "Manual review required before approving."
            ],
            certainty="missing"
        )

    # ── Case 2: VAT explicitly zero with reasonable confidence ────────────────
    if vat_amount == 0 and raw_rate == 0 and vat_field_confidence >= 0.5:
        return VATResult(
            rate=0.0,
            category="Zero rated / Exempt",
            is_valid=True,
            flags=[
                "No VAT charged. Verify this is a legitimate zero-rated or exempt supply."
            ],
            certainty="inferred"
        )

    # ── Case 3: VAT data present — classify and validate ─────────────────────
    rate = snap_vat_rate(total_amount, vat_amount, raw_rate)

    if rate == 20.0:
        category = "Standard rated (20%)"
        certainty = "confirmed"
    elif rate == 5.0:
        category = "Reduced rated (5%)"
        certainty = "confirmed"
    elif rate == 0.0:
        category = "Zero rated / Exempt"
        certainty = "confirmed"
        if vat_amount > 0:
            flags.append("VAT amount present but rate is 0% — check if zero-rated or exempt")
    else:
        category = "Unknown rate"
        certainty = "unknown"
        flags.append(f"Unrecognised VAT rate: {raw_rate}% — manual review required")

    # Validate: does VAT amount match the rate?
    if total_amount > 0 and rate > 0:
        net = total_amount - vat_amount
        expected_vat = round(net * (rate / 100), 2)
        actual_vat = round(vat_amount, 2)
        if abs(expected_vat - actual_vat) > 0.10:
            flags.append(
                f"VAT mismatch: expected £{expected_vat:.2f} at {rate}%, "
                f"got £{actual_vat:.2f} — check totals"
            )
            certainty = "unknown"

    # Flag large invoices with no VAT
    if vat_amount == 0 and total_amount > 7083:  # ~£85k annual threshold / 12
        flags.append("Large invoice with no VAT — verify supplier VAT registration")

    return VATResult(
        rate=rate,
        category=category,
        is_valid=len(flags) == 0,
        flags=flags,
        certainty=certainty
    )