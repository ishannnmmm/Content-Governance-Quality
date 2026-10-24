#!/usr/bin/env python3
"""
api_server.py
━━━━━━━━━━━━━
FastAPI backend that exposes the KB evaluation pipeline to the React
frontend.

    extract questions → deduplicate into canonical questions with counts
    → retrieve candidate articles → rerank → judge → classify failure
    → rank by frequency

It implements exactly the four operations the frontend expects:

    POST   /api/transcripts          → uploadTranscript(file)
    POST   /api/jobs                 → startPipeline(fileId)
    GET    /api/jobs/{job_id}/status → getPipelineStatus(jobId)
    GET    /api/jobs/{job_id}/results→ getAnalysisResults(jobId)

Design notes
────────────
• The pipeline is long-running, so POST /api/jobs returns immediately
  with a job_id and the work continues on a background thread. The
  frontend polls the status endpoint.

• Progress is reported as real step transitions, not a fake timer. Each
  of the 8 steps flips pending → running → completed as it actually
  happens. `progress` is derived from completed step weights, so it
  moves in honest jumps rather than pretending to be smooth.

• Customer text shown in the UI is PII-scrubbed with pii_scrubber before
  it leaves the server, and every LLM call goes through llm_client,
  which scrubs too.

Run it:
    pip install fastapi "uvicorn[standard]" python-multipart
    export GROQ_API_KEY="gsk_..."
    python api_server.py
    # → http://localhost:8000  (frontend dev server proxies to this)
"""

import os
import re
import shutil
import sys
import threading
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

# Make the pipeline modules importable (they live one level up by default).
PIPELINE_DIR = Path(os.environ.get("PIPELINE_DIR", Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(PIPELINE_DIR))

from pii_scrubber import scrub  # noqa: E402
from utterance_quality import (  # noqa: E402
    collect_speaker_names,
    strip_menu_clicks,
    strip_system_messages,
)

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────

DATA_ROOT = Path(os.environ.get("DATA_ROOT", Path(__file__).resolve().parent / "data"))
UPLOAD_DIR = DATA_ROOT / "uploads"
JOBS_DIR = DATA_ROOT / "jobs"

# Reference files the coverage audit needs. Override via env vars.
KB_FILE = os.environ.get("KB_FILE", str(PIPELINE_DIR / "kb_articles.csv"))
BOT_FLOW_FILE = os.environ.get("BOT_FLOW_FILE", str(PIPELINE_DIR / "bot_flows_tgr.csv"))

# Optional: questions written from article titles, with the article each
# came from. Without it retrieval gaps cannot be measured (see metrics.py).
LABELLED_SET_FILE = os.environ.get("LABELLED_SET_FILE", "")


ALLOWED_SUFFIXES = {".csv", ".json", ".txt"}

for d in (UPLOAD_DIR, JOBS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────────────────────
# STEP DEFINITIONS — these mirror the frontend's 8 steps exactly
# ─────────────────────────────────────────────────────────────

STEPS: List[Dict[str, Any]] = [
    {"key": "upload",    "label": "Upload transcripts",        "weight": 2},
    {"key": "validate",  "label": "Validate data",             "weight": 3},
    {"key": "clean",     "label": "Extract questions",         "weight": 8},
    {"key": "dedupe",    "label": "Group similar questions",   "weight": 12},
    {"key": "index",     "label": "Index knowledge base",      "weight": 15},
    {"key": "retrieve",  "label": "Match against articles",    "weight": 20},
    {"key": "judge",     "label": "Assess coverage",           "weight": 35},
    {"key": "prepare",   "label": "Prepare results",           "weight": 5},
]
TOTAL_WEIGHT = sum(s["weight"] for s in STEPS)

# ─────────────────────────────────────────────────────────────
# IN-MEMORY JOB REGISTRY
# ─────────────────────────────────────────────────────────────
# Fine for a single-process internal tool. If this ever needs to survive
# a restart or run multiple workers, swap this dict for Redis or a table
# — nothing else in this file assumes it's in memory.

_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()

_files: Dict[str, Dict[str, Any]] = {}


def _new_job(file_id: str) -> str:
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "file_id": file_id,
            "state": "running",
            "started_at": datetime.now(timezone.utc),
            "step_status": {s["key"]: "pending" for s in STEPS},
            "step_detail": {},
            "error": None,
            "result": None,
        }
    return job_id


def _set_step(job_id: str, key: str, status: str) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job:
            job["step_status"][key] = status


def _set_detail(job_id: str, key: str, detail: str) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job:
            job["step_detail"][key] = detail


def _fail_job(job_id: str, message: str) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["state"] = "failed"
        job["error"] = message
        for key, status in job["step_status"].items():
            if status == "running":
                job["step_status"][key] = "failed"


# ─────────────────────────────────────────────────────────────
# RESULT ASSEMBLY — evaluation records → the JSON the frontend expects
# ─────────────────────────────────────────────────────────────

MAX_VARIANTS = 25


def build_frontend_payload(
    job_id: str, evaluation: Dict[str, Any], speaker_names: Optional[set] = None
) -> Dict[str, Any]:
    """
    Reshape the evaluation records into the question-shaped AnalysisResult
    the React app is typed against. Questions arrive ranked by frequency.

    Everything customer-written that reaches the UI is scrubbed here.
    """
    from metrics import run_aggregates

    names = speaker_names or set()
    questions: List[Dict[str, Any]] = []

    for q in evaluation["questions"]:
        routing = q.get("routing")
        questions.append({
            "id": q["id"],
            "canonical": scrub(q["canonical"], extra_names=names),
            "frequency": q["frequency"],
            "variants": [scrub(v, extra_names=names) for v in q["variants"][:MAX_VARIANTS]],
            "failureType": q["failureType"],
            "verdict": q["verdict"],
            "reason": q.get("reason"),
            "requiredContent": q.get("requiredContent"),
            "retrieved": q["retrieved"],
            "routing": (
                {"flow": routing["flow"], "verdict": routing["verdict"], "reason": routing.get("reason")}
                if routing else None
            ),
            "outcomes": q["outcomes"],
        })

    return {
        "jobId": job_id,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "summary": run_aggregates(questions, evaluation["retrievalMeasured"]),
        "questions": questions,
    }


# ─────────────────────────────────────────────────────────────
# THE PIPELINE RUNNER (background thread)
# ─────────────────────────────────────────────────────────────

def run_pipeline_job(job_id: str, input_path: Path, out_dir: Path) -> None:
    """Execute the pipeline step by step, updating job state as it goes."""
    try:
        out_dir.mkdir(parents=True, exist_ok=True)

        # ── Step 1: upload (already done by the time we're here) ──
        _set_step(job_id, "upload", "completed")

        # ── Step 2: validate ──────────────────────────────────
        _set_step(job_id, "validate", "running")
        df_raw = pd.read_csv(input_path, encoding="utf-8-sig", nrows=5)
        df_raw.columns = df_raw.columns.str.strip()
        if "utterance" not in {c.lower() for c in df_raw.columns}:
            raise ValueError(
                "This file needs an 'utterance' column holding the transcript text. "
                f"Found: {', '.join(df_raw.columns)}"
            )
        if not Path(KB_FILE).exists():
            raise FileNotFoundError(
                f"The KB article reference file is missing: {KB_FILE}. "
                "Set KB_FILE before starting the server."
            )
        if not os.environ.get("GROQ_API_KEY"):
            raise RuntimeError(
                "GROQ_API_KEY is not set. Coverage is decided by an LLM judge, "
                "so the evaluation cannot run without it."
            )
        _set_step(job_id, "validate", "completed")

        # ── Step 3: extract questions ─────────────────────────
        _set_step(job_id, "clean", "running")
        from preprocess_transcripts import preprocess

        utterances_csv = out_dir / "customer_utterances.csv"
        preprocess(
            input_path=str(input_path),
            output_path=str(utterances_csv),
            utterance_col="utterance",
            escalation_col="chatOfferAccepted",
        )

        # Bot menu clicks ("Make Payment", "Billing and Reinstatement
        # Questions") are logged identically to typed messages. They are
        # navigation, not questions — strip them before anything is judged.
        extracted = pd.read_csv(utterances_csv)
        before = len(extracted)
        print("🧹  Cleaning non-question content...")

        # Chat lifecycle notices, attachment lines and live-agent turns are
        # logged like customer messages. Remove them before anything else.
        extracted = strip_system_messages(extracted, text_col="utterance")

        filtered, menu_labels = strip_menu_clicks(extracted, text_col="utterance")
        print(f"  {len(filtered):,} typed questions remain of {before:,} extracted rows")

        # Speaker names from the raw transcripts become a scrub denylist,
        # so bare and lowercased first names never reach the LLM or the UI.
        try:
            raw_df = pd.read_csv(input_path, encoding="utf-8-sig")
            speaker_names = collect_speaker_names(raw_df["utterance"])
        except Exception:
            speaker_names = set()
        from improved_coverage_analysis import scrub_denylist

        speaker_names = scrub_denylist(speaker_names, KB_FILE)

        if len(filtered) == 0:
            raise ValueError(
                "No typed questions remain after removing menu clicks and system "
                "messages. The transcripts are entirely menu navigation."
            )

        filtered.to_csv(utterances_csv, index=False)
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job:
                job["menu_labels"] = menu_labels
                job["speaker_names"] = speaker_names
                job["rows_removed"] = int(before - len(filtered))
        _set_step(job_id, "clean", "completed")

        # ── Steps 4-7: embed, group, index, retrieve, judge ───
        import improved_coverage_analysis as s2
        import improved_utterance_analysis as s1

        _set_step(job_id, "dedupe", "running")
        s1_cfg = {**s1.CFG, "INPUT_FILE": str(utterances_csv), "OUTPUT_DIR": str(out_dir)}
        questions = s1.load_data(s1_cfg)
        embeddings = s1.embed(questions, s1_cfg)

        evaluation = s2.run_evaluation(
            questions,
            embeddings,
            kb_file=KB_FILE,
            flow_file=BOT_FLOW_FILE,
            out_dir=str(out_dir),
            names=speaker_names,
            labelled_file=LABELLED_SET_FILE or None,
            on_step=lambda key, status: _set_step(job_id, key, status),
            on_judge_progress=lambda done, total: _set_detail(job_id, "judge", f"{done}/{total}"),
        )

        # ── Step 8: shape the payload for the frontend ────────
        _set_step(job_id, "prepare", "running")
        payload = build_frontend_payload(job_id, evaluation, speaker_names)
        _set_step(job_id, "prepare", "completed")

        with _jobs_lock:
            job = _jobs.get(job_id)
            if job:
                job["result"] = payload
                job["state"] = "completed"

    except Exception as exc:  # noqa: BLE001 — surface any failure to the UI
        traceback.print_exc()
        _fail_job(job_id, str(exc))


# ─────────────────────────────────────────────────────────────
# FASTAPI APP
# ─────────────────────────────────────────────────────────────

app = FastAPI(title="Chat Insights API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "groqKeyConfigured": bool(os.environ.get("GROQ_API_KEY")),
        "kbFileFound": Path(KB_FILE).exists(),
        "botFlowFileFound": Path(BOT_FLOW_FILE).exists(),
        "labelledSetFound": bool(LABELLED_SET_FILE) and Path(LABELLED_SET_FILE).exists(),
    }


@app.post("/api/transcripts")
async def upload_transcript(file: UploadFile = File(...)) -> Dict[str, Any]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"{suffix or 'That file type'} isn't supported. Upload a CSV, JSON, or TXT file.",
        )

    file_id = str(uuid.uuid4())
    dest = UPLOAD_DIR / f"{file_id}{suffix}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    size = dest.stat().st_size
    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="That file is empty.")

    _files[file_id] = {"path": dest, "name": file.filename, "size": size}

    return {
        "id": file_id,
        "name": file.filename,
        "size": size,
        "type": file.content_type or "application/octet-stream",
    }


@app.post("/api/jobs")
def start_pipeline(body: Dict[str, str]) -> Dict[str, str]:
    file_id = body.get("fileId")
    if not file_id or file_id not in _files:
        raise HTTPException(status_code=404, detail="That upload could not be found. Please upload the file again.")

    job_id = _new_job(file_id)
    out_dir = JOBS_DIR / job_id

    thread = threading.Thread(
        target=run_pipeline_job,
        args=(job_id, _files[file_id]["path"], out_dir),
        daemon=True,
    )
    thread.start()

    return {"jobId": job_id}


@app.get("/api/jobs/{job_id}/status")
def get_pipeline_status(job_id: str) -> Dict[str, Any]:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="This job could not be found. It may have expired.")
        step_status = dict(job["step_status"])
        step_detail = dict(job["step_detail"])
        state = job["state"]
        started_at = job["started_at"]
        error = job["error"]

    steps = [
        {"key": s["key"], "label": s["label"], "status": step_status[s["key"]]}
        for s in STEPS
    ]

    completed_weight = sum(s["weight"] for s in STEPS if step_status[s["key"]] == "completed")
    progress = round(completed_weight / TOTAL_WEIGHT * 100)

    running = next((s for s in STEPS if step_status[s["key"]] == "running"), None)

    return {
        "jobId": job_id,
        "steps": steps,
        "progress": progress,
        "elapsedSeconds": int((datetime.now(timezone.utc) - started_at).total_seconds()),
        "currentStepLabel": (
            f"{running['label']} ({step_detail[running['key']]})"
            if running and running["key"] in step_detail
            else running["label"] if running else None
        ),
        "state": state,
        "error": error,
    }


@app.get("/api/jobs/{job_id}/results")
def get_analysis_results(job_id: str) -> Dict[str, Any]:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="This job could not be found. It may have expired.")
        if job["state"] == "failed":
            raise HTTPException(status_code=500, detail=job["error"] or "The analysis failed.")
        if job["state"] != "completed" or job["result"] is None:
            raise HTTPException(status_code=409, detail="This analysis is still running.")
        return job["result"]


if __name__ == "__main__":
    import uvicorn

    if not os.environ.get("GROQ_API_KEY"):
        print("⚠️  GROQ_API_KEY not set — jobs will fail at validation; the judge needs it.")

    uvicorn.run(app, host="0.0.0.0", port=8001)