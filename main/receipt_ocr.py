import re
from datetime import date
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
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


def extract_provider_text(receipt_file):
    provider = getattr(settings, "RECEIPT_OCR_PROVIDER", "").strip().lower()
    if provider == "ocr_space":
        return extract_ocr_space_text(receipt_file)

    return "", "No receipt OCR provider is configured."


def extract_ocr_space_text(receipt_file):
    api_key = getattr(settings, "OCR_SPACE_API_KEY", "")
    if not api_key:
        return "", "OCR_SPACE_API_KEY is not configured."

    endpoint = getattr(settings, "OCR_SPACE_ENDPOINT", "https://api.ocr.space/parse/image")
    language = getattr(settings, "OCR_SPACE_LANGUAGE", "eng")
    file_name = receipt_file.name.rsplit("/", 1)[-1] or "receipt"

    receipt_file.open("rb")
    try:
        response = requests.post(
            endpoint,
            data={
                "apikey": api_key,
                "language": language,
                "isOverlayRequired": "false",
                "scale": "true",
                "OCREngine": "2",
            },
            files={"file": (file_name, receipt_file)},
            timeout=60,
        )
    finally:
        receipt_file.close()

    if response.status_code >= 400:
        return "", f"OCR provider returned HTTP {response.status_code}."

    try:
        payload = response.json()
    except ValueError:
        return "", "OCR provider returned an unreadable response."

    if payload.get("IsErroredOnProcessing"):
        error_message = payload.get("ErrorMessage") or payload.get("ErrorDetails") or "OCR provider could not process the file."
        if isinstance(error_message, list):
            error_message = " ".join(str(item) for item in error_message)
        return "", str(error_message)

    parsed_results = payload.get("ParsedResults") or []
    text = "\n".join(result.get("ParsedText", "") for result in parsed_results if result.get("ParsedText"))
    return normalize_ocr_text(text), ""


def process_receipt_ocr(receipt):
    extracted_text = extract_embedded_text(receipt.receipt_file)
    provider_error = ""
    if not extracted_text:
        extracted_text, provider_error = extract_provider_text(receipt.receipt_file)

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
        receipt.ocr_status = "needs_ocr_provider" if "not configured" in provider_error.lower() else "failed"
        receipt.ocr_text = ""
        receipt.ocr_error = (
            provider_error
            or "This file appears to be a scanned image or image-only PDF. Connect an OCR provider to extract text automatically."
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
