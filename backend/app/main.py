from __future__ import annotations

import json
import tempfile
import traceback
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .models import AnalysisResponse, BootstrapTemplateResponse
from .services.common import load_json_file, load_optional_json
from .services.pipeline import analyze_bundle
from .services.thematic import prepare_excerpt_records
from .services.usability import bootstrap_task_template


app = FastAPI(title="Email Encryption Study Analysis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Ensure CORS headers are present even on unhandled 500 errors.

    Without this, uvicorn's default 500 response bypasses the CORS
    middleware, causing the browser to report a CORS policy violation
    instead of the actual server error.
    """
    traceback.print_exc()
    origin = request.headers.get("origin", "*")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "*",
            "Access-Control-Allow-Headers": "*",
        },
    )


def _save_upload(temp_dir: Path, upload: UploadFile) -> str:
    destination = temp_dir / upload.filename
    destination.write_bytes(upload.file.read())
    return str(destination)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/theme-codebook")
def theme_codebook() -> dict:
    path = Path(__file__).resolve().parent / "config" / "theme_codebook.json"
    return {"items": load_json_file(path)}


@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze(
    survey_file: UploadFile = File(...),
    usability_file: UploadFile = File(...),
    task_outcomes_file: Optional[UploadFile] = File(default=None),
    theme_assignments_file: Optional[UploadFile] = File(default=None),
    analysis_config: Optional[str] = Form(default=None),
) -> AnalysisResponse:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        survey_path = _save_upload(tmp_dir, survey_file)
        usability_path = _save_upload(tmp_dir, usability_file)
        task_outcomes_path = _save_upload(tmp_dir, task_outcomes_file) if task_outcomes_file else None
        theme_assignments_path = _save_upload(tmp_dir, theme_assignments_file) if theme_assignments_file else None
        config = load_optional_json(analysis_config)
        result = analyze_bundle(
            survey_path=survey_path,
            usability_path=usability_path,
            config=config,
            task_outcomes_path=task_outcomes_path,
            theme_assignments_path=theme_assignments_path,
        )
        return AnalysisResponse(**result)


@app.post("/api/bootstrap/theme-template", response_model=BootstrapTemplateResponse)
async def bootstrap_theme_template(
    usability_file: UploadFile = File(...),
    theme_assignments_file: Optional[UploadFile] = File(default=None),
) -> BootstrapTemplateResponse:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        usability_path = _save_upload(tmp_dir, usability_file)
        theme_assignments_path = _save_upload(tmp_dir, theme_assignments_file) if theme_assignments_file else None
        records = prepare_excerpt_records(
            usability_path,
            theme_assignments_path=theme_assignments_path,
        )
        return BootstrapTemplateResponse(
            generated_at=result_time(),
            records=records,
        )


@app.post("/api/bootstrap/task-template", response_model=BootstrapTemplateResponse)
async def bootstrap_task_template_endpoint(
    usability_file: UploadFile = File(...),
) -> BootstrapTemplateResponse:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        usability_path = _save_upload(tmp_dir, usability_file)
        records = bootstrap_task_template(usability_path)
        return BootstrapTemplateResponse(
            generated_at=result_time(),
            records=records,
        )


def result_time() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
