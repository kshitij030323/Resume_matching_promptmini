"""Corpus + vector-database engine (Deliverable 2 core).

* Loads resumes / JDs from ``data/``, extracts them once (cached on disk by content hash).
* Builds two text *representations* per document:
    - ``raw``        the original text,
    - ``structured`` a canonical profile rendered from the extracted JSON.
* Embeds every resume with every dense method and stores it in a ChromaDB collection
  ``resumes__<method>__<representation>`` (cosine HNSW). A JD is embedded on the fly
  and used as the query vector.
* Ranks candidates per JD with static / contextual / lexical / hybrid methods.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from . import config
from .embeddings import BM25, GloveMean, GloveSIF, make_bge, make_minilm
from .extraction import OFFLINE_PARSER_VERSION, extract_job, extract_resume
from .schemas import ExtractionMeta, JobSchema, ResumeSchema
from .skills_taxonomy import canonicalize, has_requirement, related_skills

REPRESENTATIONS = ("structured", "raw")
DENSE_METHODS = ("glove_mean", "glove_sif", "minilm", "bge_small")
HYBRID_BASE = "bge_small"          # contextual model underneath the hybrid ranker (fixed a priori)
HYBRID_WEIGHTS = {"similarity": 0.6, "required": 0.3, "preferred": 0.1, "experience_penalty": 0.15}

METHOD_INFO = {
    "glove_mean": ("GloVe-100 (mean)", "static"),
    "glove_sif": ("GloVe-100 (SIF)", "static"),
    "minilm": ("MiniLM-L6 (contextual)", "contextual"),
    "bge_small": ("BGE-small (contextual)", "contextual"),
    "hybrid": ("Hybrid: BGE + skill coverage", "hybrid"),
    "rerank": ("Two-stage rerank (experimental)", "hybrid"),
    "bm25": ("BM25 (lexical)", "lexical"),
}
RERANK_DEPTH = 15   # stage-1 shortlist size re-scored by the structured gap analysis (fixed a priori)


@dataclass
class Doc:
    id: str
    kind: str  # resume | job
    path: Path
    raw_text: str
    extracted: ResumeSchema | JobSchema
    meta: ExtractionMeta


# =============================================================================
# Text representations
# =============================================================================
def resume_profile_text(r: ResumeSchema) -> str:
    parts = [f"{r.headline}.", r.summary,
             f"{r.total_years_experience:g} years of experience, {r.seniority} level.",
             "Skills: " + ", ".join(s.name for s in r.skills) + "."]
    for e in r.experience:
        tech = f" Technologies: {', '.join(e.technologies)}." if e.technologies else ""
        parts.append(f"{e.title} at {e.company}. " + " ".join(e.highlights) + tech)
    for p in r.projects:
        parts.append(f"Project {p.name}: {p.description}")
    if r.certifications:
        parts.append("Certifications: " + "; ".join(r.certifications) + ".")
    for ed in r.education:
        parts.append(f"{ed.degree}{' in ' + ed.field if ed.field else ''}, {ed.institution}.")
    return "\n".join(p for p in parts if p and p.strip())


def job_query_text(j: JobSchema) -> str:
    parts = [f"{j.title}.", j.summary]
    if j.min_years_experience is not None:
        parts.append(f"{j.min_years_experience:g}+ years of experience, {j.seniority} level.")
    parts.append("Required skills: " + ", ".join(j.required_skills) + ".")
    if j.preferred_skills:
        parts.append("Preferred skills: " + ", ".join(j.preferred_skills) + ".")
    parts.extend(j.responsibilities)
    return "\n".join(p for p in parts if p and p.strip())


_TECH_ROLE_RE = re.compile(
    r"\b(engineer|developer|scientist|analyst|sre|devops|programmer|architect|administrator|"
    r"researcher|data|machine learning|ml|software|platform|reliability|analytics|bi|"
    r"cto|technical lead|tech lead|mobile|frontend|front-end|backend|back-end|full[- ]stack)\b", re.I)
_NON_TECH_ROLE_RE = re.compile(
    r"\b(support|customer|sales|store|retail|cashier|teacher|tutor|bootcamp|student|trainee|intern|internship)\b", re.I)


def _ym(s: Optional[str]) -> Optional[int]:
    from datetime import date

    if not s:
        return None
    if s == "present":
        t = date.today()
        return t.year * 12 + t.month
    m = re.match(r"(\d{4})-(\d{2})", s)
    return int(m.group(1)) * 12 + int(m.group(2)) if m else None


def is_tech_role(title: str) -> bool:
    return bool(_TECH_ROLE_RE.search(title)) and not _NON_TECH_ROLE_RE.search(title)


def relevant_years(r: ResumeSchema) -> float:
    """Years in technical roles (overlaps merged). A store manager with a two-month
    bootcamp has ~0 relevant years even though total_years_experience is large."""
    spans = []
    for e in r.experience:
        if not is_tech_role(e.title):
            continue
        a, b = _ym(e.start), _ym(e.end)
        if a is not None and b is not None and b >= a:
            spans.append((a, b))
        elif e.duration_years:
            spans.append((0, int(e.duration_years * 12)))
    spans.sort()
    total, cur = 0, None
    for a, b in spans:
        if cur is None or a > cur[1]:
            if cur:
                total += cur[1] - cur[0]
            cur = [a, b]
        else:
            cur[1] = max(cur[1], b)
    if cur:
        total += cur[1] - cur[0]
    if not r.experience:  # no parsable roles: fall back to the stated total
        return r.total_years_experience
    return round(total / 12, 1)


def candidate_skill_set(r: ResumeSchema) -> set[str]:
    s = {canonicalize(x.name) for x in r.skills}
    for e in r.experience:
        s.update(canonicalize(t) for t in e.technologies)
    for p in r.projects:
        s.update(canonicalize(t) for t in p.technologies)
    return {x for x in s if x}


def skill_overlap(job: JobSchema, resume: ResumeSchema) -> dict:
    """Required/preferred coverage. An alternatives requirement ("A / B") is met by any part."""
    have = candidate_skill_set(resume)
    req = job.required_skills
    pref = job.preferred_skills
    matched_req = [s for s in req if has_requirement(s, have)]
    missing_req = [s for s in req if not has_requirement(s, have)]
    matched_pref = [s for s in pref if has_requirement(s, have)]
    partial_req = [s for s in missing_req if related_skills(s, have)]
    partial_pref = [s for s in pref if not has_requirement(s, have) and related_skills(s, have)]
    return {
        "matched_required": matched_req,
        "missing_required": missing_req,
        "matched_preferred": matched_pref,
        "coverage": round(len(matched_req) / len(req), 3) if req else 1.0,
        # soft coverage (half credit for transferable skills) is what the hybrid ranker uses
        "_soft_required": (len(matched_req) + 0.5 * len(partial_req)) / len(req) if req else 1.0,
        "_soft_preferred": (len(matched_pref) + 0.5 * len(partial_pref)) / len(pref) if pref else 1.0,
    }


# =============================================================================
# Engine
# =============================================================================
class Engine:
    def __init__(self, use_llm_for_missing: bool = False):
        self.lock = threading.RLock()
        self.use_llm_for_missing = use_llm_for_missing
        self.resumes: dict[str, Doc] = {}
        self.jobs: dict[str, Doc] = {}
        self._load_corpus()
        self._init_models()
        self._init_vector_db()

    # ------------------------------------------------------------------ corpus
    @staticmethod
    def _doc_id(path: Path) -> str:
        return path.stem.split("_")[0]

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]

    def _cache_path(self, kind: str, doc_id: str) -> Path:
        return config.EXTRACT_CACHE_DIR / f"{kind}_{doc_id}.json"

    def _extract_cached(self, kind: str, doc_id: str, text: str, force_llm: bool = False):
        cp = self._cache_path(kind, doc_id)
        h = self._hash(text)
        if cp.exists() and not force_llm:
            data = json.loads(cp.read_text())
            fresh = data.get("meta", {}).get("method") == "llm" or data.get("parser_version") == OFFLINE_PARSER_VERSION
            if data.get("hash") == h and fresh:
                model = ResumeSchema if kind == "resume" else JobSchema
                return model.model_validate(data["extracted"]), ExtractionMeta.model_validate(data["meta"])
        fn = extract_resume if kind == "resume" else extract_job
        extracted, meta = fn(text, use_llm=self.use_llm_for_missing or force_llm)
        cp.write_text(json.dumps({"hash": h, "parser_version": OFFLINE_PARSER_VERSION,
                                  "extracted": extracted.model_dump(), "meta": meta.model_dump()}, indent=2))
        return extracted, meta

    def _load_corpus(self) -> None:
        for kind, folder, store in (("resume", config.RESUME_DIR, self.resumes),
                                    ("job", config.JOB_DIR, self.jobs)):
            for path in sorted(folder.glob("*.txt")):
                text = path.read_text(encoding="utf-8")
                doc_id = self._doc_id(path)
                extracted, meta = self._extract_cached(kind, doc_id, text)
                store[doc_id] = Doc(doc_id, kind, path, text, extracted, meta)

    def reextract_all(self, use_llm: bool = True) -> dict:
        """Re-run extraction for the whole corpus (e.g. with Claude) and rebuild indexes."""
        counts = {"llm": 0, "offline": 0}
        with self.lock:
            for store in (self.resumes, self.jobs):
                for d in store.values():
                    d.extracted, d.meta = self._extract_cached(d.kind, d.id, d.raw_text, force_llm=use_llm)
                    counts[d.meta.method] += 1
            self._init_vector_db(force=True)
        return counts

    def text_for(self, doc: Doc, rep: str) -> str:
        if rep == "raw":
            return doc.raw_text
        if doc.kind == "resume":
            return resume_profile_text(doc.extracted)  # type: ignore[arg-type]
        return job_query_text(doc.extracted)  # type: ignore[arg-type]

    # ------------------------------------------------------------------ models
    def _init_models(self) -> None:
        minilm, bge = make_minilm(), make_bge()
        self.dense: dict[tuple[str, str], object] = {}
        for rep in REPRESENTATIONS:
            sif = GloveSIF()
            sif.fit([self.text_for(d, rep) for d in list(self.resumes.values()) + list(self.jobs.values())])
            self.dense[("glove_mean", rep)] = GloveMean()
            self.dense[("glove_sif", rep)] = sif
            self.dense[("minilm", rep)] = minilm
            self.dense[("bge_small", rep)] = bge
        self.minilm = minilm
        self.bm25 = {rep: BM25() for rep in REPRESENTATIONS}
        for rep in REPRESENTATIONS:
            for d in self.resumes.values():
                self.bm25[rep].add(d.id, self.text_for(d, rep))
        self._job_vec_cache: dict[tuple[str, str, str], np.ndarray] = {}

    def method_infos(self) -> list[dict]:
        out = []
        for key, (label, family) in METHOD_INFO.items():
            if key in DENSE_METHODS:
                desc = self.dense[(key, "structured")].info.description  # type: ignore[attr-defined]
            elif key == "bm25":
                desc = BM25.info.description
            elif key == "rerank":
                desc = (f"Retrieve the top {RERANK_DEPTH} with the hybrid ranker, then re-order them by the "
                        "fit score of the (offline) skill-gap analysis - evidence-weighted requirement "
                        "coverage plus years in technical roles - so seniority and demonstrated skills count.")
            else:
                desc = (f"{HYBRID_WEIGHTS['similarity']:.0%} BGE-small cosine (min-max scaled per job) + "
                        f"{HYBRID_WEIGHTS['required']:.0%} required-skill coverage + "
                        f"{HYBRID_WEIGHTS['preferred']:.0%} preferred-skill coverage from the extracted "
                        f"JSON, minus a penalty when years in technical roles fall short of the JD's minimum.")
            out.append({"key": key, "label": label, "family": family, "description": desc})
        return out

    # ------------------------------------------------------------------ vector db
    def _corpus_signature(self, rep: str) -> str:
        h = hashlib.sha1()
        for d in sorted(self.resumes.values(), key=lambda x: x.id):
            h.update(d.id.encode())
            h.update(self._hash(self.text_for(d, rep)).encode())
        return h.hexdigest()[:16]

    def _init_vector_db(self, force: bool = False) -> None:
        import chromadb

        self.chroma = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
        self.collections = {}
        for rep in REPRESENTATIONS:
            sig = self._corpus_signature(rep)
            for method in DENSE_METHODS:
                name = f"resumes__{method}__{rep}"
                col = self.chroma.get_or_create_collection(
                    name, configuration={"hnsw": {"space": "cosine"}},
                    metadata={"method": method, "representation": rep}, embedding_function=None)
                stale = (col.metadata or {}).get("corpus_sig") != sig or col.count() != len(self.resumes)
                # SIF depends on a corpus-fitted component, so always re-index it on start-up.
                # Re-index IN PLACE (upsert + delete stale ids) - never drop the collection,
                # so another process sharing the same ChromaDB (API server + scripts) keeps
                # a valid handle.
                if force or stale or method == "glove_sif":
                    gone = set(col.get(include=[])["ids"]) - set(self.resumes)
                    if gone:
                        col.delete(ids=sorted(gone))
                    self._index(col, method, rep, list(self.resumes.values()))
                    col.modify(metadata={"method": method, "representation": rep, "corpus_sig": sig})
                self.collections[(method, rep)] = col
        self._job_vec_cache = {}

    def _index(self, col, method: str, rep: str, docs: list[Doc]) -> None:
        if not docs:
            return
        emb = self.dense[(method, rep)]
        X = emb.embed([self.text_for(d, rep) for d in docs])  # type: ignore[attr-defined]
        col.upsert(
            ids=[d.id for d in docs],
            embeddings=X.tolist(),
            documents=[self.text_for(d, rep)[:2000] for d in docs],
            metadatas=[{"name": d.extracted.name, "headline": d.extracted.headline} for d in docs],  # type: ignore[union-attr]
        )

    def add_document(self, kind: str, text: str, extracted, meta: ExtractionMeta) -> str:
        """Persist a new resume/JD to the corpus and index it everywhere."""
        with self.lock:
            store = self.resumes if kind == "resume" else self.jobs
            prefix = "R" if kind == "resume" else "J"
            nums = [int(re.sub(r"\D", "", k) or 0) for k in store]
            doc_id = f"{prefix}{(max(nums) + 1 if nums else 1):02d}"
            name = extracted.name if kind == "resume" else extracted.title
            slug = re.sub(r"[^a-z0-9]+", "_", (name or "doc").lower()).strip("_")[:40]
            folder = config.RESUME_DIR if kind == "resume" else config.JOB_DIR
            path = folder / f"{doc_id}_{slug}.txt"
            path.write_text(text, encoding="utf-8")
            self._cache_path(kind, doc_id).write_text(json.dumps(
                {"hash": self._hash(text), "parser_version": OFFLINE_PARSER_VERSION,
                 "extracted": extracted.model_dump(), "meta": meta.model_dump()}, indent=2))
            doc = Doc(doc_id, kind, path, text, extracted, meta)
            store[doc_id] = doc
            if kind == "resume":
                for rep in REPRESENTATIONS:
                    self.bm25[rep].add(doc_id, self.text_for(doc, rep))
                    for method in DENSE_METHODS:
                        col = self.collections[(method, rep)]
                        self._index(col, method, rep, [doc])
                        col.modify(metadata={**(col.metadata or {}), "corpus_sig": self._corpus_signature(rep)})
            return doc_id

    # ------------------------------------------------------------------ ranking
    def _job_vec(self, method: str, rep: str, job: Doc) -> np.ndarray:
        key = (method, rep, job.id)
        if key not in self._job_vec_cache:
            emb = self.dense[(method, rep)]
            self._job_vec_cache[key] = emb.embed([self.text_for(job, rep)], is_query=True)[0]  # type: ignore[attr-defined]
        return self._job_vec_cache[key]

    def dense_similarities(self, method: str, rep: str, job: Doc) -> dict[str, float]:
        col = self.collections[(method, rep)]
        q = self._job_vec(method, rep, job)
        res = col.query(query_embeddings=[q.tolist()], n_results=max(1, col.count()),
                        include=["distances"])
        return {rid: round(1.0 - float(dist), 6) for rid, dist in zip(res["ids"][0], res["distances"][0])}

    def fit_score(self, job_id: str, resume_id: str) -> int:
        """Offline gap-analysis fit score (steps 1-2 of the chain), cached per pair."""
        from .skillgap import OfflineChain  # local import: skillgap imports engine

        cache = self.__dict__.setdefault("_fit_cache", {})
        key = (job_id, resume_id, self._hash(self.resumes[resume_id].raw_text), self._hash(self.jobs[job_id].raw_text))
        if key not in cache:
            chain = OfflineChain(self)
            job, res = self.jobs[job_id], self.resumes[resume_id]
            s1 = chain.step1(job.extracted, res.extracted, res.raw_text)  # type: ignore[arg-type]
            cache[key] = chain.step2(job.extracted, s1).fit_score  # type: ignore[arg-type]
        return cache[key]

    def rank(self, job_id: str, method: str, rep: str = "structured", top_k: Optional[int] = None) -> list[dict]:
        if job_id not in self.jobs:
            raise KeyError(f"Unknown job {job_id}")
        if method not in METHOD_INFO:
            raise KeyError(f"Unknown method {method}")
        if rep not in REPRESENTATIONS:
            raise KeyError(f"Unknown representation {rep}")
        job = self.jobs[job_id]
        jx: JobSchema = job.extracted  # type: ignore[assignment]
        overlaps = {rid: skill_overlap(jx, d.extracted) for rid, d in self.resumes.items()}  # type: ignore[arg-type]

        if method == "rerank":
            stage1 = self.rank(job_id, "hybrid", rep)
            head, tail = stage1[:RERANK_DEPTH], stage1[RERANK_DEPTH:]
            for row in head:
                row["score"] = round(self.fit_score(job_id, row["resume_id"]) / 100 + 0.001 * row["score"], 4)
            head.sort(key=lambda r: (-r["score"], r["resume_id"]))
            for row in tail:  # keep stage-1 order below the re-ranked shortlist
                row["score"] = round(row["score"] - 1.0, 4)
            out = head + tail
            for i, row in enumerate(out, start=1):
                row["rank"] = i
            return out[: top_k or len(out)]

        if method in DENSE_METHODS:
            sims = self.dense_similarities(method, rep, job)
            scores = dict(sims)
        elif method == "bm25":
            sims = self.bm25[rep].scores(self.text_for(job, rep))
            mx = max(sims.values()) or 1.0
            scores = {k: v / mx for k, v in sims.items()}
        else:  # hybrid
            sims = self.dense_similarities(HYBRID_BASE, rep, job)
            lo, hi = min(sims.values()), max(sims.values())
            w = HYBRID_WEIGHTS
            scores = {}
            for rid, s in sims.items():
                r: ResumeSchema = self.resumes[rid].extracted  # type: ignore[assignment]
                ov = overlaps[rid]
                need = jx.min_years_experience or 0
                shortfall = max(0.0, (need - relevant_years(r)) / need) if need else 0.0
                scores[rid] = (w["similarity"] * ((s - lo) / (hi - lo) if hi > lo else 1.0)
                               + w["required"] * ov["_soft_required"]
                               + w["preferred"] * ov["_soft_preferred"]
                               - w["experience_penalty"] * min(1.0, shortfall))

        order = sorted(scores, key=lambda k: (-scores[k], k))
        out = []
        for i, rid in enumerate(order[: top_k or len(order)], start=1):
            d = self.resumes[rid]
            ov = {k: v for k, v in overlaps[rid].items() if not k.startswith("_")}
            out.append({
                "rank": i, "resume_id": rid, "name": d.extracted.name,  # type: ignore[union-attr]
                "headline": d.extracted.headline,  # type: ignore[union-attr]
                "score": round(float(scores[rid]), 4), "similarity": round(float(sims[rid]), 4),
                "skills": ov,
            })
        return out
