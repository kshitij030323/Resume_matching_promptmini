# REST API contract

Base URL: `http://<host>:8010` (FastAPI; the backend also serves the built web UI at `/`). All bodies are JSON unless noted.
Object shapes for `ResumeSchema`, `JobSchema`, `SkillGapReport`, etc. are defined in
`backend/app/schemas.py` (Pydantic) — that file is the source of truth.

## Health

`GET /api/health`
```json
{
  "status": "ok",
  "llm": { "enabled": false, "provider": "anthropic", "model": "claude-opus-5-5" },
  "counts": { "resumes": 30, "jobs": 6 },
  "vector_db": "chromadb",
  "methods_ready": ["glove_mean", "glove_sif", "minilm", "bge_small", "hybrid", "bm25"]
}
```
`llm.enabled` is false when no Anthropic credentials are configured; the system then
uses the offline extractor and the offline skill-gap chain (UI should show a badge:
"Claude" vs "Offline").

## Jobs

`GET /api/jobs` → `JobSummary[]`
```json
[{ "id": "J01", "title": "Senior Machine Learning Engineer", "company": "Acme",
   "location": "Remote", "seniority": "senior", "min_years_experience": 5,
   "required_skills": ["Python", "PyTorch"], "preferred_skills": ["Kubernetes"],
   "summary": "..." }]
```

`GET /api/jobs/{id}` →
```json
{ "id": "J01", "raw_text": "...", "extracted": JobSchema, "meta": ExtractionMeta }
```

## Resumes / candidates

`GET /api/resumes` → `ResumeSummary[]`
```json
[{ "id": "R01", "name": "Asha Rao", "headline": "ML Engineer", "location": "Pune",
   "total_years_experience": 6.5, "seniority": "senior",
   "top_skills": ["Python", "PyTorch", "NLP", "AWS", "Docker"] }]
```

`GET /api/resumes/{id}` →
```json
{ "id": "R01", "raw_text": "...", "extracted": ResumeSchema, "meta": ExtractionMeta }
```

## Extraction (Deliverable 1)

`POST /api/extract`
```json
{ "kind": "resume" | "job", "text": "...", "save": false, "use_llm": true }
```
→
```json
{ "id": "R31" | null, "kind": "resume", "extracted": ResumeSchema | JobSchema,
  "meta": { "method": "llm" | "offline", "model": "claude-opus-5-5" | null,
            "latency_ms": 812, "repaired": false, "warnings": [] } }
```
`id` is non-null only when `save: true` (the document is added to the corpus and indexed).

`POST /api/extract/file` — `multipart/form-data` with fields `file` (PDF, DOCX or TXT),
`kind` (`resume` | `job`), `save` (`true`/`false`). Same response as above plus
`"raw_text"`.

## Ranking (Deliverable 2)

`GET /api/methods` →
```json
[{ "key": "glove_mean", "label": "GloVe (mean)", "family": "static",
   "description": "..." }]
```
`family` ∈ `static | contextual | hybrid | lexical`.

`POST /api/rank`
```json
{ "job_id": "J01", "method": "minilm", "representation": "structured", "top_k": 10 }
```
`representation` ∈ `structured | raw` (default `structured`).
→
```json
{ "job_id": "J01", "method": "minilm", "representation": "structured",
  "results": [
    { "rank": 1, "resume_id": "R07", "name": "...", "headline": "...",
      "score": 0.83, "similarity": 0.79,
      "skills": { "matched_required": ["Python"], "missing_required": ["Kubernetes"],
                  "matched_preferred": [], "coverage": 0.75 },
      "human_grade": 3 }
  ],
  "ndcg_at_5": 0.91 }
```
`human_grade` is the 0–3 human relevance label for (job, resume), or null.

## Evaluation (NDCG@5 vs human rankings)

`GET /api/evaluation?k=5` →
```json
{ "k": 5,
  "jobs": [{ "id": "J01", "title": "..." }],
  "results": [
    { "method": "minilm", "label": "MiniLM-L6 (contextual)", "family": "contextual",
      "representation": "structured",
      "mean_ndcg": 0.88, "mean_ndcg_10": 0.86, "mean_precision": 0.8,
      "per_job": { "J01": 0.93, "J02": 0.81 } }
  ],
  "best": { "method": "hybrid", "representation": "structured", "mean_ndcg": 0.93 },
  "static_vs_contextual": { "static_best": 0.71, "contextual_best": 0.88, "delta": 0.17 } }
```

`GET /api/labels` → `{ "J01": { "R01": 3, "R02": 0, ... }, ... }`

`PUT /api/labels/{job_id}` body `{ "grades": { "R01": 3, "R02": 1 } }` →
`{ "job_id": "J01", "grades": {...} }`  (evaluation recomputes using the new labels)

Grade scale: 3 = strong fit, 2 = good fit, 1 = weak/adjacent, 0 = not relevant.

## Skill-gap prompt chain (Deliverable 3)

`POST /api/skillgap`
```json
{ "job_id": "J01", "resume_id": "R07", "use_llm": true }
```
→ `SkillGapReport` (see schemas.py). Notable fields:
`fit_score` (0–100), `verdict` (`strong_match|good_match|partial_match|weak_match`),
`headline`, `executive_summary`, `hiring_recommendation`, `experience_fit`,
`strengths[] {skill, evidence}`,
`gaps[] {skill, importance, severity: critical|moderate|minor, reason, transferable_from[]}`,
`recommendations[] {skill, action, type, resource_hint, effort_weeks, priority}`,
`interview_questions[]`,
`assessments[] {skill, importance, status: met|partial|missing, evidence, transferable_from[]}`,
`chain_trace[] {step, name, mode: llm|offline, model, latency_ms, output}` (4 steps:
Requirement alignment → Gap prioritisation → Recommendations → Report synthesis).

`POST /api/shortlist`
```json
{ "job_id": "J01", "method": "hybrid", "top_n": 5, "use_llm": true }
```
→ `{ "job_id": "J01", "method": "hybrid", "reports": SkillGapReport[] }`

Errors: non-2xx with `{ "detail": "message" }`.
