# MetroVigil AI — Legal Metrology Compliance Scanner (Prototype)

SIH Problem Statement 26034: Software System to check compliance of
Packaged Commodities under the Legal Metrology (Packaged Commodities)
Rules, 2011 by scanning products, images and labels.

## What this prototype does

1. **Upload** — upload a photo of a product label
2. **Extract** — preprocesses the image (OpenCV) and runs OCR (Tesseract) to pull out the raw text
3. **Validate** — checks the extracted text against mandatory declarations (MRP, net quantity, mfg date, manufacturer, consumer care, country of origin) using a rule engine defined in `data/rules.json`
4. **Report** — generates a downloadable PDF compliance report
5. **Dashboard** — every scan is saved to a local SQLite database and browsable/searchable in a second tab

## Project structure

```
metrology-app/
├── app.py                # Streamlit UI — entry point
├── core/
│   ├── preprocess.py      # image cleanup before OCR (OpenCV)
│   ├── ocr.py              # text extraction (Tesseract, swappable for Cloud Vision)
│   ├── rules.py            # compliance rule engine
│   ├── report.py           # PDF report generation
│   └── storage.py          # SQLite scan repository
├── data/
│   ├── rules.json           # mandatory declaration definitions (edit this to add/change rules)
│   └── scans.db              # created automatically on first run
├── requirements.txt
└── README.md
```

## Setup

### 1. Install the Tesseract OCR binary (one-time, system-level)

- **Ubuntu/Debian**: `sudo apt-get install tesseract-ocr`
- **macOS**: `brew install tesseract`
- **Windows**: install from https://github.com/UB-Mannheim/tesseract/wiki and add it to your PATH

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the app

```bash
streamlit run app.py
```

It will open at `http://localhost:8501`.

## How to test it

Take a clear photo of any packaged product's label (a snack packet,
a shampoo bottle, anything with print on it) and upload it. The OCR
accuracy depends heavily on lighting and focus — flat, well-lit,
close-up shots work best. Try a few different products to see how
the compliance score changes.

## Extending this for the actual SIH submission

- **Better OCR**: swap Tesseract for Google Cloud Vision API in
  `core/ocr.py` (`_extract_with_cloud_vision`, already stubbed in) —
  much more accurate on glossy/curved packaging, at the cost of needing
  an API key.
- **Font-size / readability check**: `core/preprocess.py` has a starter
  function `estimate_text_heights_mm()` that measures character heights
  from contours — wire this into the rules engine as an additional
  compliance check once you've studied the exact font-size clauses in
  the Rules.
- **Role-based access**: add `streamlit-authenticator` for a login
  screen with officer/supervisor/admin roles.
- **Bulk/e-commerce scanning**: add a batch-upload mode and a scheduled
  scraper that feeds listing images through the same `core/` pipeline.
- **Move off Streamlit**: once the `core/` logic is solid, everything
  in this folder can be reused behind a FastAPI backend with a React
  frontend — none of `core/` needs to change, only `app.py` gets
  replaced by API routes + a separate frontend.

## Known limitations (be upfront about these to judges)

- Regex-based field matching is simple and will miss unusual phrasing
  or highly stylised fonts — a production system would need NLP-based
  field classification.
- Tesseract struggles with curved, glossy, or low-contrast labels more
  than commercial OCR services.
- The font-size/readability check is not yet wired into the compliance
  score — it's scaffolded in `preprocess.py` for you to complete.
