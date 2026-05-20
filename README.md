# pdf2xls-generator

Parses a training routine PDF, uploads the data to Google Sheets with full formatting (borders, colors, frozen columns, weekly tints), and publishes events to the shared SQLite queue so `routine-analyzer` can run automatically.

## Usage

```bash
python3 pdf_to_xlsx.py <pdf_file> \
  --sheets-id <spreadsheet_id> \
  --credentials <credentials.json> \
  [--force]    # delete and recreate the tab if it already exists
  [--no-xlsx]  # skip writing the local .xlsx file
```

**Example:**
```bash
python3 pdf_to_xlsx.py 2026_05_11_103916.pdf \
  --sheets-id 1z4N0o6C1zBx7U_Y-G0h6dkqstgyz5dDCQp7MsAVf2WE \
  --credentials rutinas-entrenamiento-496600-cfbbb2bb0b5c.json \
  --no-xlsx --force
```

## Event flow

When `--sheets-id` is passed the script fires three events in order:

1. **`run:global`** + **`run:monthly`** — published *before* the upload so `routine-analyzer` can analyze the existing history first.
2. PDF data is uploaded to Google Sheets.
3. **`run:new-routine`** — published *after* the upload so `routine-analyzer` can evaluate the new routine against the recorded goal.

`routine-analyzer` picks up these events by running `python3 analyze.py` (no `--mode` flag).

## Project structure

```
pdf_to_xlsx.py       ← entry point (CLI)
helpers/
  pdf_parser/        ← extracts exercises from the PDF
  exercise/          ← exercise name formatting, layout, tab name
  sheets/            ← Google Sheets writing and formatting
  xlsx/              ← local .xlsx writing
  events/            ← SQLite event publisher
```

## Dependencies

Install with:

```bash
pip install -r requirements.txt
```

This includes `training-shared` (shared event constants), installed directly from GitHub.

## How to get Google Sheets credentials

The script uses a **Google Service Account** — a special Google account for applications (not a person).

### 1. Create a Google Cloud project

1. Go to [https://console.cloud.google.com](https://console.cloud.google.com)
2. Click **"New Project"**, give it a name (e.g. `rutinas-entrenamiento`), and click **Create**

### 2. Enable the APIs

1. In your project, go to **APIs & Services → Library**
2. Search for **"Google Sheets API"** and click **Enable**
3. Search for **"Google Drive API"** and click **Enable** too

### 3. Create a Service Account

1. Go to **APIs & Services → Credentials**
2. Click **"Create Credentials" → "Service Account"**
3. Give it a name (e.g. `rutinas-bot`), click **Create and Continue**, then **Done**

### 4. Download the JSON key

1. Click on the service account you just created
2. Go to the **"Keys"** tab
3. Click **"Add Key" → "Create new key" → JSON**
4. A `.json` file will download — this is your credentials file
5. Place it in this project folder (it's excluded from git via `.gitignore`)

### 5. Share the spreadsheet with the service account

1. Open the `.json` file and copy the `client_email` field (looks like `rutinas-bot@your-project.iam.gserviceaccount.com`)
2. Open your Google Sheets spreadsheet
3. Click **Share**, paste that email, and give it **Editor** access

That's it — the script will now be able to read and write to that spreadsheet.
