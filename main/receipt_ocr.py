import re
from datetime import date
from decimal import Decimal, InvalidOperation

from django.utils import timezone


DATE_PATTERNS = [
    re.compile(r"\b(?P<month>\d{1,2})[/-](?P<day>\d{1,2})[/-](?P<year>\d{2,4})\b"),
    re.compile(r"\b(?P<year>\d{4})[/-](?P<month>\d{1,2})[/-](?P<day>\d{1,2})\b"),
]

AMOUNT_LABEL_PATTERNS = [
    re.compile(r"(?:grand\s+total|total\s+due|amount\s+paid|total)\s*[:#]?\s*\$?\s*(?P<amount>\d{1,6}(?:,\d{3})*\.\d{2})", re.I),
    re.compile(r"\$\s*(?P<amount>\d{1,6}(?:,\d{3})*\.\d{2})"),
]

VENDOR_SKIP_WORDS = {
    "receipt",
    "invoice",
    "statement",
    "date",
    "total",
    "amount",
    "cash",
    "visa",
    "mastercard",
}


def normalize_ocr_text(text):
    return "\n".join(line.strip() for line in str(text or "").splitlines() if line.strip())


def parse_receipt_text(text):
    clean_text = normalize_ocr_text(text)
    return {
        "vendor": guess_vendor(clean_text),
        "receipt_date": guess_receipt_date(clean_text),
        "amount": guess_total_amount(clean_text),
    }


def guess_vendor(text):
    for line in text.splitlines()[:8]:
        normalized = re.sub(r"[^A-Za-z0-9 &'.-]", "", line).strip()
        if not normalized:
            continue
        if normalized.lower() in VENDOR_SKIP_WORDS:
            continue
        if re.search(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", normalized):
            continue
        if re.search(r"\d{3}[-.\s]\d{3}[-.\s]\d{4}", normalized):
            continue
        return normalized[:255]
    return ""


def guess_receipt_date(text):
    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        year = int(match.group("year"))
        if year < 100:
            year += 2000
        try:
            return date(year, int(match.group("month")), int(match.group("day")))
        except ValueError:
            continue
    return None


def guess_total_amount(text):
    candidates = []
    for pattern in AMOUNT_LABEL_PATTERNS:
        for match in pattern.finditer(text):
            try:
                candidates.append(Decimal(match.group("amount").replace(",", "")).quantize(Decimal("0.01")))
            except (InvalidOperation, AttributeError):
                continue
    if not candidates:
        return None
    return max(candidates)


def extract_embedded_text(receipt_file):
    name = (receipt_file.name or "").lower()
    if not name.endswith((".txt", ".csv", ".pdf")):
        return ""

    receipt_file.open("rb")
    try:
        data = receipt_file.read(250000)
    finally:
        receipt_file.close()

    text = data.decode("utf-8", errors="ignore")
    if name.endswith(".pdf"):
        # This catches text-based PDFs. Scanned PDFs and photos still require a real OCR provider.
        text = re.sub(r"[^A-Za-z0-9$.,:/#@&%+()'\"\-\s]", " ", text)
    return normalize_ocr_text(text)


def process_receipt_ocr(receipt):
    extracted_text = extract_embedded_text(receipt.receipt_file)
    update_fields = [
        "ocr_status",
        "ocr_text",
        "ocr_error",
        "ocr_processed_at",
        "ocr_suggested_vendor",
        "ocr_suggested_date",
        "ocr_suggested_amount",
    ]

    receipt.ocr_processed_at = timezone.now()

    if not extracted_text:
        receipt.ocr_status = "needs_ocr_provider"
        receipt.ocr_text = ""
        receipt.ocr_error = (
            "This file appears to be a scanned image or image-only PDF. "
            "Connect an OCR provider to extract text automatically."
        )
        receipt.save(update_fields=update_fields)
        return receipt

    suggestions = parse_receipt_text(extracted_text)
    receipt.ocr_status = "extracted"
    receipt.ocr_text = extracted_text
    receipt.ocr_error = ""
    receipt.ocr_suggested_vendor = suggestions["vendor"] or ""
    receipt.ocr_suggested_date = suggestions["receipt_date"]
    receipt.ocr_suggested_amount = suggestions["amount"]

    auto_fields = []
    if receipt.ocr_suggested_vendor and not receipt.vendor:
        receipt.vendor = receipt.ocr_suggested_vendor
        auto_fields.append("vendor")
    if receipt.ocr_suggested_date and not receipt.receipt_date:
        receipt.receipt_date = receipt.ocr_suggested_date
        auto_fields.append("receipt_date")
    if receipt.ocr_suggested_amount and receipt.amount == Decimal("0.00"):
        receipt.amount = receipt.ocr_suggested_amount
        auto_fields.append("amount")

    receipt.save(update_fields=update_fields + auto_fields)
    return receipt
