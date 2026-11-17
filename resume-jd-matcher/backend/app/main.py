"""FastAPI application - see ../API.md for the contract.

Run:  python -m uvicorn app.main:app --port 8010      (from backend/)
"""

from __future__ import annotations

import io
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Literal, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .engine import DENSE_METHODS, METHOD_INFO, Engine
from .evaluation import evaluate, grades, ndcg_at_k, save_job_grades
from .extraction import extract_job, extract_resume
from .llm import LLMUnavailable, active_provider, clear_gemini, llm_available, llm_status, set_gemini
from .skillgap import run_chain

log = logging.getLogger("matcher")
app = FastAPI(title="Resume & JD Matching System", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_engine: Optional[Engine] = None


def engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = Engine()
    return _engine


@app.on_event("startup")
def _warm() -> None:
    engine()


# ----------------------------------------------------------------------------- models
class ExtractRequest(BaseModel):
    kind: Literal["resume", "job"]
    text: str
    save: bool = False
    use_llm: bool = True


class RankRequest(BaseModel):
    job_id: str
    method: str = "hybrid"
    representation: Literal["structured", "raw"] = "structured"
    top_k: Optional[int] = None


class LabelsUpdate(BaseModel):
    grades: dict[str, int]


class SkillGapRequest(BaseModel):
    job_id: str
    resume_id: str
    use_llm: bool = True


class LlmSettingsUpdate(BaseModel):
    gemini_api_key: Optional[str] = None   # omitted = keep the current key
    gemini_model: Optional[str] = None
    remember: bool = True                  # also save to backend/storage/llm_settings.json


class ShortlistRequest(BaseModel):
    job_id: str
    method: str = "hybrid"
    representation: Literal["structured", "raw"] = "structured"
    top_n: int = 5
    use_llm: bool = True


# ----------------------------------------------------------------------------- health
@app.get("/api/health")
def health():
    e = engine()
    return {
        "status": "ok",
        "llm": llm_status(),
        "counts": {"resumes": len(e.resumes), "jobs": len(e.jobs)},
        "vector_db": "chromadb",
        "methods_ready": list(METHOD_INFO),
        "dense_methods_in_vector_db": list(DENSE_METHODS),
        "extraction_methods": {
            "llm": sum(d.meta.method == "llm" for d in list(e.resumes.values()) + list(e.jobs.values())),
            "offline": sum(d.meta.method == "offline" for d in list(e.resumes.values()) + list(e.jobs.values())),
        },
    }


# ----------------------------------------------------------------------------- LLM settings
@app.get("/api/llm")
def get_llm():
    """Provider status plus the Gemini models the configured key can use. Never returns a key."""
    return llm_status(include_models=True)


@app.put("/api/llm")
def put_llm(body: LlmSettingsUpdate):
    try:
        return set_gemini(body.gemini_api_key, body.gemini_model, body.remember)
    except LLMUnavailable as exc:
        raise HTTPException(400, str(exc)) from exc


@app.delete("/api/llm/gemini")
def delete_gemini_key():
    return clear_gemini()


# ----------------------------------------------------------------------------- jobs / resumes
@app.get("/api/jobs")
def list_jobs():
    out = []
    for d in engine().jobs.values():
        j = d.extracted
        out.append({"id": d.id, "title": j.title, "company": j.company, "location": j.location,  # type: ignore[union-attr]
                    "seniority": j.seniority, "min_years_experience": j.min_years_experience,  # type: ignore[union-attr]
                    "required_skills": j.required_skills, "preferred_skills": j.preferred_skills,  # type: ignore[union-attr]
                    "summary": j.summary})  # type: ignore[union-attr]
    return out


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    d = engine().jobs.get(job_id)
    if not d:
        raise HTTPException(404, f"Job {job_id} not found")
    return {"id": d.id, "raw_text": d.raw_text, "extracted": d.extracted.model_dump(), "meta": d.meta.model_dump()}


@app.get("/api/resumes")
def list_resumes():
    out = []
    for d in engine().resumes.values():
        r = d.extracted
        top = sorted(r.skills, key=lambda s: -(s.years or 0))  # type: ignore[union-attr]
        out.append({"id": d.id, "name": r.name, "headline": r.headline, "location": r.location,  # type: ignore[union-attr]
                    "total_years_experience": r.total_years_experience, "seniority": r.seniority,  # type: ignore[union-attr]
                    "top_skills": [s.name for s in top[:6]]})
    return out


@app.get("/api/resumes/{resume_id}")
def get_resume(resume_id: str):
    d = engine().resumes.get(resume_id)
    if not d:
        raise HTTPException(404, f"Resume {resume_id} not found")
    return {"id": d.id, "raw_text": d.raw_text, "extracted": d.extracted.model_dump(), "meta": d.meta.model_dump()}


# ----------------------------------------------------------------------------- extraction
def _do_extract(kind: str, text: str, save: bool, use_llm: bool) -> dict:
    if len(text.strip()) < 40:
        raise HTTPException(422, "Text is too short to extract from (need at least ~40 characters).")
    fn = extract_resume if kind == "resume" else extract_job
    extracted, meta = fn(text, use_llm=use_llm)
    doc_id = engine().add_document(kind, text, extracted, meta) if save else None
    return {"id": doc_id, "kind": kind, "extracted": extracted.model_dump(), "meta": meta.model_dump()}


@app.post("/api/extract")
def extract(req: ExtractRequest):
    return _do_extract(req.kind, req.text, req.save, req.use_llm)


def _file_to_text(name: str, data: bytes) -> str:
    lower = name.lower()
    if lower.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    if lower.endswith(".docx"):
        import docx

        d = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in d.paragraphs)
    return data.decode("utf-8", errors="replace")


@app.post("/api/extract/file")
async def extract_file(file: UploadFile = File(...), kind: str = Form("resume"), save: str = Form("false"),
                       use_llm: str = Form("true")):
    if kind not in ("resume", "job"):
        raise HTTPException(422, "kind must be 'resume' or 'job'")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 10 MB)")
    try:
        text = _file_to_text(file.filename or "upload.txt", data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, f"Could not read file: {exc}") from exc
    out = _do_extract(kind, text, save.lower() == "true", use_llm.lower() == "true")
    out["raw_text"] = text
    return out


# ----------------------------------------------------------------------------- ranking
@app.get("/api/methods")
def methods():
    return engine().method_infos()


@app.post("/api/rank")
def rank(req: RankRequest):
    e = engine()
    try:
        results = e.rank(req.job_id, req.method, req.representation, None)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    g = grades().get(req.job_id, {})
    for r in results:
        r["human_grade"] = g.get(r["resume_id"])
    ndcg = round(ndcg_at_k([r["resume_id"] for r in results], g, 5), 4) if g else None
    return {"job_id": req.job_id, "method": req.method, "representation": req.representation,
            "results": results[: req.top_k] if req.top_k else results, "ndcg_at_5": ndcg}


# ----------------------------------------------------------------------------- evaluation
@app.get("/api/evaluation")
def evaluation(k: int = 5, include_rankings: bool = False):
    if k < 1 or k > 30:
        raise HTTPException(422, "k must be between 1 and 30")
    return evaluate(engine(), k=k, include_rankings=include_rankings)


@app.get("/api/labels")
def get_labels():
    return grades()


@app.put("/api/labels/{job_id}")
def put_labels(job_id: str, body: LabelsUpdate):
    if job_id not in engine().jobs:
        raise HTTPException(404, f"Job {job_id} not found")
    unknown = [r for r in body.grades if r not in engine().resumes]
    if unknown:
        raise HTTPException(422, f"Unknown resume ids: {unknown}")
    try:
        cur = save_job_grades(job_id, body.grades)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"job_id": job_id, "grades": cur}


# ----------------------------------------------------------------------------- skill gap
@app.post("/api/skillgap")
def skillgap(req: SkillGapRequest):
    try:
        return run_chain(engine(), req.job_id, req.resume_id, use_llm=req.use_llm).model_dump()
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/shortlist")
def shortlist(req: ShortlistRequest):
    e = engine()
    try:
        ranked = e.rank(req.job_id, req.method, req.representation, max(1, min(req.top_n, 10)))
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    ids = [r["resume_id"] for r in ranked]
    # Gemini's free tier allows ~10 requests/minute, so fan out less there.
    workers = (2 if active_provider() == "gemini" else 4) if (req.use_llm and llm_available()) else 1
    with ThreadPoolExecutor(max_workers=workers) as pool:
        reports = list(pool.map(lambda rid: run_chain(e, req.job_id, rid, use_llm=req.use_llm).model_dump(), ids))
    return {"job_id": req.job_id, "method": req.method, "reports": reports}


# ----------------------------------------------------------------------------- web UI
if config.WEB_DIST_DIR.exists():
    assets = config.WEB_DIST_DIR / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "Not found")
        candidate = config.WEB_DIST_DIR / full_path
        if full_path and candidate.is_file() and config.WEB_DIST_DIR in candidate.resolve().parents:
            return FileResponse(candidate)
        return FileResponse(config.WEB_DIST_DIR / "index.html")
