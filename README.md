# BidLens — AI Sourcing Copilot

A local Streamlit prototype for procurement analysts. The product journey is **prepare request → validate supplier responses → compare and simulate sourcing scenarios**.

## What is implemented

- Three connected screens, with a shared sourcing request and supplier-response dataset.
- Requirement readiness checks and an optional LLM-assisted requirement review.
- Five fictional source documents in Excel, PDF, scanned PNG, email and Word formats.
- Deterministic extraction from each bundled document format; the scan uses Tesseract OCR when it can recover sufficient rows, otherwise the app uses a packaged synthetic OCR reference transcript and discloses that fallback.
- A 30-item, five-supplier gold-standard dataset to test extracted values. Missing quotes remain missing; an ambiguous scan price remains unresolved.
- Source excerpts and document locators for extracted quote fields, plus download links to the original synthetic documents.
- A local SQLite database for request state, reviewed values and scenario history.
- Currency and price-basis normalization using a visible illustrative USD/INR rate.
- A constrained whole-line allocation optimizer, plus a separate user-defined quantity-split simulator across two suppliers, subject to quote availability, delivery and freight-data constraints.
- A rule-based analyst query layer. If an OpenAI API key is configured, the LLM may interpret requirements, interpret a source excerpt as a *suggestion*, and route natural-language questions to deterministic tools. The LLM does not perform the final cost calculations.
- Clarification email drafts that can be downloaded; no email is sent.

## Important boundaries

- Every supplier, price and source document is fictional.
- This is a demonstration, not a production purchasing system.
- The optimizer assigns whole line items to suppliers. A separate split simulator lets the analyst test a chosen percentage split across two suppliers, but does not optimize partial quantities. Supplier capacity, minimum order quantities, tax calculation, historical supplier performance and unconfirmed discounts are not modeled.
- Unknown freight can be excluded from scenarios. Taxes and other charges absent from source documents are excluded and disclosed as limitations.
- The USD/INR rate is an illustrative assumption, not a live FX quote.
- The optional LLM integration requires a separate OpenAI API key and may incur API charges. A ChatGPT subscription does not automatically provide API credits. When enabled, the app sends the relevant requirement or selected source excerpt/question to the configured LLM provider. Do not use confidential supplier information unless authorized.
- The scanned-image fallback transcript is packaged to make the synthetic demo reproducible on machines without a working OCR binary. The UI labels this fallback.

## Run on Windows

Open Command Prompt in this folder, then run:

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The first run creates `data/bidlens.db`. It persists local edits and scenarios. Delete that file only if you intentionally want to reset the local demo database; it will be recreated from the bundled source documents.

## Optional LLM setup

Set `OPENAI_API_KEY` in your local environment before starting Streamlit, or configure it in `.streamlit/secrets.toml` (keep that file out of Git). Optionally set `BIDLENS_MODEL`. Without an API key, the app uses the deterministic local fallback for requirement checks and question routing.

## Tests

```bat
python -m unittest discover -s tests -v
```

The tests compare extracted quote fields against `data/gold_standard_quotes.csv`, check missing/ambiguous handling, validate normalization, and run a constrained allocation scenario.

## Project structure

- `app.py` — Streamlit UI
- `bidlens_engine.py` — extraction, validation, persistence, normalization, scenario optimizer and analyst tools
- `generate_demo_data.py` — reproducible synthetic source-document generator
- `data/source_documents/` — five fictional supplier documents and the OCR reference transcript
- `data/rfx_items.csv` — 30 requested line items
- `data/gold_standard_quotes.csv` — expected values for extraction tests
- `tests/test_engine.py` — automated checks

## GitHub safety

Create a **new, separate repository** for BidLens. Do not modify the existing portfolio repository. Never commit API keys, private supplier documents, or the local SQLite database.
