# Resume & Job-Description Matching System

Mini-project 4 (PEGAI "Jackfruit" problem statements): extract structured information from
resumes and job descriptions, rank candidates per job with embedding search, and generate a
skill-gap report for each shortlisted candidate. It ships with a browser UI (React + Vite).

| Deliverable | Where |
|---|---|
| 1. Structured-output extraction into a fixed JSON schema | `backend/app/schemas.py`, `backend/app/extraction.py`, `backend/app/llm.py` |
| 2. Ranking: static (GloVe) vs contextual (MiniLM, BGE) embeddings in a vector DB (ChromaDB), NDCG@5 vs human rankings | `backend/app/embeddings.py`, `backend/app/engine.py`, `backend/app/evaluation.py`, `backend/reports/evaluation.md` |
| 3. Prompt chain: skill-gap analysis and recommendations per shortlisted candidate | `backend/app/skillgap.py`, `backend/reports/skillgap_*.md` |
| Web interface | `web/` (React + TypeScript), served by the backend at `/` |

---

## Quick start

```bash
cd resume-jd-matcher
./run.sh                      # first run creates backend/.venv and installs web deps
# open http://127.0.0.1:8010
```

To use Claude for extraction and the skill-gap chain (recommended), export a key first.
Without one, everything still works in **offline mode**: a heuristic extractor and a
deterministic version of the same 4-step chain. The UI shows a *Claude* or *Offline* badge.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
./run.sh
# optional: re-extract the bundled corpus with Claude (cached afterwards)
cd backend && ./.venv/bin/python scripts/extract_corpus.py --llm
```

Development mode (hot reload):

```bash
# terminal 1 - API on :8010
cd backend && ./.venv/bin/python -m uvicorn app.main:app --port 8010 --reload
# terminal 2 - UI on :5173 (proxies /api to :8010)
cd web && npm install && npm run dev
```

Reproduce the reports and tests:

```bash
cd backend
./.venv/bin/python scripts/evaluate.py                 # -> reports/evaluation.md/.json, ndcg_at_5.png
./.venv/bin/python scripts/skillgap_report.py J01      # -> reports/skillgap_J01.md/.json
./.venv/bin/python scripts/extract_corpus.py           # -> reports/extracted_corpus.json
./.venv/bin/python -m pytest -q tests
```

Configuration (environment variables): `ANTHROPIC_API_KEY`, `LLM_MODEL` (default
`claude-opus-5-5`), `EXTRACTION_EFFORT` (default `low`), `CHAIN_EFFORT` (default `medium`),
`DISABLE_LLM=1` (force offline mode), `PORT` (default 8010).

---

## Architecture

```
            resume / JD text (.txt, .pdf, .docx, pasted)
                              │
                ┌─────────────▼─────────────┐
   Deliverable 1│  Extraction                │  Claude structured outputs (Pydantic schema)
                │  ResumeSchema / JobSchema  │  ── or ── offline section parser + skill taxonomy
                │  + normalise/repair layer  │  canonical skills (k8s→Kubernetes), validation
                └─────────────┬─────────────┘
                              │ fixed JSON
            ┌─────────────────┼────────────────────────┐
            │ representations: "structured" profile text | "raw" text
            ▼                                          ▼
   ┌──────────────────────┐                ┌───────────────────────────┐
   │ Static embeddings    │                │ Contextual embeddings      │
   │ GloVe-100 mean / SIF │                │ MiniLM-L6, BGE-small       │
   └─────────┬────────────┘                └─────────────┬─────────────┘
             └──────────────► ChromaDB (cosine HNSW) ◄────┘   one collection per
                              resumes__<method>__<repr>       method × representation
                                        │  JD vector = query
   Deliverable 2                        ▼
   Ranking: dense cosine │ BM25 baseline │ Hybrid = BGE + skill coverage − years shortfall
   Evaluation: NDCG@5 / NDCG@10 / P@5 vs graded human labels (0–3), sign-flip test
                                        │ shortlist (top-N)
   Deliverable 3                        ▼
   Prompt chain:  1 Requirement alignment → 2 Gap prioritisation → 3 Recommendations → 4 Report synthesis
                  (each step = one schema-constrained Claude call fed by the previous step's
                   validated JSON; identical offline implementation when no API key)
```

### Deliverable 1: structured extraction

* **Fixed schema**: `ResumeSchema` (contact, headline, summary, total years, seniority,
  skills with category/years/proficiency, experience with dates/highlights/technologies,
  education, certifications, projects) and `JobSchema` (title, company, location, seniority,
  min years, required vs preferred skills, responsibilities, education, domain).
* **LLM path**: `client.beta.messages.parse(..., output_format=ResumeSchema)` with Claude
  Opus 5.5. Structured outputs constrain the response to the JSON schema. We re-validate with
  Pydantic, and if validation fails we re-ask once with the error appended (automatic repair).
  The server-side refusal fallback (`fallbacks="default"`) is enabled.
* **Offline path**: section detection (with many header aliases), date-range parsing
  (`Jan 2019 – Present`, `03/2020 – 08/2022`, `2017 - 2019`, ...), merged-interval experience
  years, an alias-aware skill taxonomy of ~150 canonical skills (longest-match, word
  boundaries, case-sensitive `Go`/`R`), and estimated skill years and proficiency per role.
* **Normalisation layer (both paths)**: canonical skill names, de-duplication, clamped numbers.
  JD alternatives such as "Tableau, Power BI or Looker" become one requirement
  `"Tableau / Power BI / Looker"` that is satisfied by any member.

### Deliverable 2: ranking and evaluation

| Method | Family | Notes |
|---|---|---|
| `glove_mean` | static | mean of GloVe-100 (Wikipedia + Gigaword) vectors, stop-words removed |
| `glove_sif` | static | SIF weighting a/(a+p(w)) + first principal component removed |
| `minilm` | contextual | `all-MiniLM-L6-v2`, sentence-packed chunks within its 256-token window |
| `bge_small` | contextual | `BAAI/bge-small-en-v1.5`, chunks within 512 tokens |
| `hybrid` | hybrid | 0.6 × BGE cosine (min-max per job) + 0.3 × required coverage + 0.1 × preferred coverage − 0.15 × shortfall in technical-role years |
| `bm25` | lexical | Okapi BM25 reference baseline (not a vector method) |

All four dense methods store resume vectors in **ChromaDB** collections (cosine HNSW). Each
JD is embedded as the query. Every method runs on two text representations: the raw
resume, and a *structured* profile rendered from the extracted JSON.

**Evaluation**: NDCG@k with graded gains (2^rel − 1) and IDCG from the human ordering,
plus NDCG@10, Precision@5 (grade ≥ 2), and an exact paired sign-flip permutation test
between the best static and best contextual method.

#### Results (50 candidates × 6 JDs, 300 graded pairs; offline extraction)

Full report: [`backend/reports/evaluation.md`](backend/reports/evaluation.md) (chart:
`backend/reports/ndcg_at_5.png`).

| Method | Family | NDCG@5 structured | NDCG@5 raw |
|---|---|---|---|
| MiniLM-L6 | contextual | **0.953** | 0.854 |
| BGE-small | contextual | 0.928 | **0.864** |
| GloVe-100 mean | static | 0.947 | 0.806 |
| GloVe-100 SIF | static | 0.908 | 0.815 |
| Hybrid (BGE + skill coverage) | hybrid | 0.921 | 0.869 |
| Two-stage rerank (experimental) | hybrid | 0.827 | 0.827 |
| BM25 | lexical | 0.955 | 0.921 |

What the numbers say:

1. **On raw resume text, contextual beats static**: 0.864 vs 0.815 NDCG@5. The gap is
   largest on the jargon-heavy roles: SRE 0.895 vs 0.625–0.644, Backend 0.976 vs 0.697–0.714.
   GloVe-100 has no vectors for `kubernetes`, `grafana`, `pytorch`, `mlflow`, `bigquery` and
   ~25 other modern skill names, and words like *spark*, *airflow* and *swift* keep their
   general-English meaning. On raw text GloVe-mean even ranks R07, a support rep who lists
   ML buzzwords, inside the top 5 for the ML role.
2. **Structured extraction closes most of that gap.** On the canonical profile text built
   from the JSON (`k8s`→Kubernetes, `RN`→React Native, alternatives grouped), every embedding
   method improves by 0.05–0.14 (BM25 by 0.03), and static vs contextual becomes nearly a tie (0.947 vs 0.953;
   contextual better on 5/6 jobs). Deliverable 1 is doing the vocabulary normalisation that
   contextual models otherwise provide.
3. **No embedding captures seniority or specialisation.** On the Senior ML/NLP role the
   contextual models score only 0.737–0.767: they rank a new graduate with the exact LLM stack (human
   grade 1) and a junior (grade 2) above senior engineers (grade 3), and miss a grade-3
   candidate who describes RAG as "semantic search with an LLM answer generator".
4. **BM25 on structured text is a strong baseline (0.955).** The canonicalised skill
   vocabulary makes exact term matching very effective. The experimental two-stage rerank,
   driven by the *offline* rule-based gap analysis, hurts (0.827): its partial credit for
   transferable skills is too generous to near-miss candidates. A Claude-based rerank is the
   natural next step but costs API calls.
5. **Significance**: with 6 queries no difference is statistically significant (exact
   sign-flip p ≥ 0.46; the smallest attainable p is 0.031). Treat the per-job tables as
   qualitative evidence. More JDs would be needed for a firm conclusion.

### Deliverable 3: skill-gap prompt chain

| Step | Input | Output schema |
|---|---|---|
| 1. Requirement alignment | JD JSON + resume JSON | per requirement: met / partial / missing + evidence quote + transferable skills; experience fit |
| 2. Gap prioritisation | step-1 output + JD context | strengths, gaps with severity (critical / moderate / minor), fit score 0–100 |
| 3. Recommendations | step-2 gaps + candidate profile | learning plan (action, type, resource, effort in weeks, priority) + interview questions |
| 4. Report synthesis | steps 1–3 | verdict, headline, executive summary, hiring recommendation |

Each step is its own schema-constrained Claude call whose validated output feeds the next
step. The UI shows the full chain trace (mode, model, latency, JSON per step).
`POST /api/shortlist` runs the chain for the top-N candidates of any ranking method.

Without an API key the same four steps run offline. Step 1 grades **evidence quality**: a
skill counts as *met* only if it was used in a technical role of at least 6 months (or is
listed by someone with at least 2 years of technical experience). Claims in a skills list
without supporting experience count as *partial*, and experience fit uses years in
*technical* roles. This is what stops keyword-stuffed resumes from scoring as strong
matches. A MiniLM similarity search finds semantic evidence for requirements that have no
lexical hit.

---

## Dataset and labels

`backend/data/` holds 6 job descriptions (Senior ML/NLP Engineer, Data Analyst, Backend
Engineer, React Native Developer, SRE/DevOps, Data Engineer) and 50 synthetic, fictional
resumes (R31–R50 are deliberate near-misses added to avoid a ceiling effect). They were written to include realistic hard cases: synonyms and abbreviations
(`k8s`, `RN`, `Postgres`, "transformer models"), resumes with thin Skills sections,
keyword-stuffed resumes, seniority mismatches, adjacent roles, career switchers, and
near-miss specialisations.

**About the "human rankings"**: `backend/data/human_rankings.json` contains a graded
relevance label (0–3) and a one-sentence rationale for every (job, resume) pair. These
labels were **written by an AI assistant acting as an annotator**, reading each resume
against each JD with the rubric. They were not produced by real humans. For a submission
that requires human judgments, have one or more people review and adjust them. The web UI's
**Evaluate → Annotate** screen lets you edit grades per job (the original file is backed up
to `human_rankings.original.json` on first edit), and NDCG is recomputed immediately. With
several annotators you can also report agreement (for example Cohen's κ) before averaging.

## Limitations

* The corpus is small (6 queries), so per-job NDCG differences are noisy. The sign-flip test
  makes the uncertainty explicit.
* The offline extractor is heuristic. Claude extraction is more robust to unusual layouts.
  `scripts/extract_corpus.py --llm` reports skill-set agreement between the two.
* GloVe-100 (2014) has no vectors for many modern tool names. That is part of the finding,
  not a bug.
* The hybrid weights were fixed a priori, not tuned on the labels, to avoid overfitting the
  evaluation set.

## Troubleshooting

* **Port 8010 busy**: `PORT=8020 ./run.sh`. For `npm run dev`, set `VITE_API_TARGET=http://127.0.0.1:8020`.
* **`npm install` permission error on `~/.npm`**: `npm install --cache /tmp/npm-cache`.
* **First start is slow** (~30 s): it loads GloVe and the two sentence-transformer models
  (downloaded once, ~350 MB total) and builds the ChromaDB collections in `backend/storage/`.
  Delete `backend/storage/` to rebuild everything from scratch.
* **UI changes not showing at :8010**: the backend serves the last `npm run build` from
  `web/dist`. Rebuild, or use `npm run dev` on :5173.

## Project layout

```
resume-jd-matcher/
├── run.sh                    one-command launcher
├── API.md                    REST contract
├── backend/
│   ├── app/                  schemas, extraction, llm, embeddings, engine (ChromaDB), evaluation, skillgap, main (FastAPI)
│   ├── data/                 jobs/*.txt, resumes/*.txt, human_rankings.json
│   ├── scripts/              evaluate.py, skillgap_report.py, extract_corpus.py
│   ├── reports/              generated evaluation + skill-gap reports
│   ├── tests/                pytest unit tests
│   └── storage/              generated: extraction cache, GloVe .kv, ChromaDB
└── web/                      React + TypeScript + Vite UI (src/pages, src/components)
```

## API

See [`API.md`](API.md). Main endpoints: `GET /api/jobs`, `GET /api/resumes`,
`POST /api/extract`, `POST /api/extract/file`, `POST /api/rank`, `GET /api/evaluation`,
`GET|PUT /api/labels`, `POST /api/skillgap`, `POST /api/shortlist`.
