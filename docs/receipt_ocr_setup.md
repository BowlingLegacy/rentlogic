# Receipt OCR Setup

Rental Ledger Pro can store receipt images and PDFs immediately. Text-based PDFs and text-like files are parsed locally. Scanned photos and image-only PDFs require an OCR provider.

## Current Provider Hook

The app supports a configurable `ocr_space` provider hook.

Set these Render environment variables on the Rental Ledger Pro web service:

```text
RECEIPT_OCR_PROVIDER=ocr_space
OCR_SPACE_API_KEY=your-api-key
OCR_SPACE_ENDPOINT=https://api.ocr.space/parse/image
OCR_SPACE_LANGUAGE=eng
```

`OCR_SPACE_ENDPOINT` and `OCR_SPACE_LANGUAGE` are optional because the app has defaults.

## Workflow

1. Owner uploads a receipt, invoice, scanned image, or PDF.
2. The system stores the original file.
3. The system first checks whether readable text is embedded in the file.
4. If embedded text is not found and `RECEIPT_OCR_PROVIDER=ocr_space`, the file is sent to the OCR provider.
5. Extracted text is saved on the receipt record.
6. Vendor, receipt date, and total amount are suggested and filled when the matching field is blank.
7. The receipt remains in review until a user approves it into the ledger.

## Fallback Behavior

If no OCR provider is configured, scanned images and image-only PDFs are still stored. The receipt queue shows `Needs OCR Provider`, so the file can be reviewed manually and processed again later after the provider is connected.

## Provider Swap

The OCR provider logic lives in `main/receipt_ocr.py`. A future Google Vision, AWS Textract, Azure Document Intelligence, or OpenAI Vision provider can be added there without changing the receipt upload or approval workflow.
