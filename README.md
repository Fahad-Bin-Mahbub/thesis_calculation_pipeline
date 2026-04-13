# Email Encryption Study Analysis Pipeline

A starter project for recomputing **paper-ready key/value results** from your survey and usability data.

Built with:
- **Next.js + TypeScript + React + Tailwind CSS** for the UI
- **FastAPI + Python** for the analysis pipeline

## What this project does

You upload:
1. the **survey workbook**
2. the **usability workbook**
3. an optional **task outcomes CSV** for exact TSR calculation
4. an optional **theme assignments CSV** for thematic-analysis counts

The app returns:
- a searchable **key → value** result list
- warnings about missing or non-reproducible values
- summary tables
- JSON that you can copy from when updating the paper manually

## Important limitation

Your uploaded usability workbook includes:
- NASA-TLX style ratings
- task timing
- qualitative responses

But it **does not appear to include raw per-subtask Pass / Partial / Fail values** used for exact TSR tables, and it **does not include final theme assignments** for the thematic analysis. Because of that, this project supports two extra lightweight inputs:

- `task_outcomes.csv` for exact TSR
- `theme_assignments.csv` for theme support counts

Without those two optional files, the project still computes:
- survey frequencies and percentages
- chi-square tests
- usability time means
- NASA-TLX scores
- excerpt extraction for thematic coding bootstrap

## Project structure

- `frontend/` – Next.js app
- `backend/` – FastAPI analysis service
- `backend/examples/` – starter config and CSV templates

## Quick start

### 1) Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 2) Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

Set this if your backend is not on port 8000:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## CLI usage

You can also run the pipeline without the UI.

### Analyze

```bash
cd backend
python -m app.cli analyze   --survey "/path/to/survey.xlsx"   --usability "/path/to/usability.xlsx"   --out "./exports/results.json"
```

Optional inputs:

```bash
python -m app.cli analyze   --survey "/path/to/survey.xlsx"   --usability "/path/to/usability.xlsx"   --task-outcomes "./examples/task_outcomes.template.csv"   --theme-assignments "./examples/theme_assignments.template.csv"   --config "./examples/sample_analysis_config.json"   --out "./exports/results.json"
```

### Bootstrap a theme assignment template from the usability workbook

```bash
cd backend
python -m app.cli bootstrap-theme-template   --usability "/path/to/usability.xlsx"   --out "./exports/theme_assignments.csv"
```

### Bootstrap a task outcomes template

```bash
cd backend
python -m app.cli bootstrap-task-template   --usability "/path/to/usability.xlsx"   --out "./exports/task_outcomes.csv"
```

## Expected CSV formats

### task_outcomes.csv

Columns:
- `participant_name`
- `tool` → `protonmail` or `securemyemail`
- `task` → `task1`, `task2`, `task3`
- `subtask` → `a`, `b`, `c`
- `status` → `pass`, `partial`, `failed`

### theme_assignments.csv

Columns:
- `excerpt_id`
- `theme_id` → one or more theme IDs separated by `|`
- `reviewer_notes` (optional)

Default theme IDs:
- `TH01_interface_complexity`
- `TH02_authentication_setup`
- `TH03_encryption_transparency`
- `TH04_trust_security`
- `TH05_learning_curve`

## Notes on reproducibility

The paper mentions manual quality control for the survey and interpretive thematic analysis. To handle that, this project supports a small config file:

- survey row exclusions
- usability row exclusions

See `backend/examples/sample_analysis_config.json`.

## Suggested workflow

1. Add new survey and usability responses to your workbooks.
2. Mark any excluded rows in the config file if needed.
3. Update `task_outcomes.csv` for the new participant.
4. Update `theme_assignments.csv` for the new excerpts you reviewed.
5. Run analysis.
6. Copy updated values from `results.json` into the paper.

## Output shape

The backend returns JSON like:

```json
{
  "generated_at": "...",
  "keys": {
    "survey.total_n": 118,
    "survey.awareness.yes_n": 64,
    "survey.awareness.yes_pct": 54.24,
    "usability.protonmail.time_mean_min": 26.33,
    "usability.protonmail.nasa_tlx": 33.61
  },
  "warnings": []
}
```
