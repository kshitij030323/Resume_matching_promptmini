"""NDCG@k evaluation of every ranking method against human relevance grades.

Graded relevance (0-3) with the standard exponential gain:

    DCG@k  = sum_{i=1..k} (2^{rel_i} - 1) / log2(i + 1)
    NDCG@k = DCG@k / IDCG@k

IDCG uses the *human* ideal ordering of all labelled candidates for that job.
Candidates without a label count as relevance 0.

We also report NDCG@10, Precision@k (grade >= 2 counts as relevant) and an exact
paired sign-flip permutation test between the best static and best contextual method
(per-job NDCG differences; with J jobs there are 2^J sign assignments).
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import shutil
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from . import config
from .engine import DENSE_METHODS, METHOD_INFO, REPRESENTATIONS, Engine


# --------------------------------------------------------------------------- labels
def load_labels() -> dict:
    if not config.LABELS_PATH.exists():
        return {"grades": {}}
    return json.loads(config.LABELS_PATH.read_text())


def grades(labels: Optional[dict] = None) -> dict[str, dict[str, int]]:
    labels = labels or load_labels()
    return {j: {r: int(g) for r, g in gs.items()} for j, gs in labels.get("grades", {}).items()}


def save_job_grades(job_id: str, new: dict[str, int]) -> dict[str, int]:
    labels = load_labels()
    backup = config.LABELS_PATH.with_name("human_rankings.original.json")
    if config.LABELS_PATH.exists() and not backup.exists():
        shutil.copy(config.LABELS_PATH, backup)
    cur = labels.setdefault("grades", {}).setdefault(job_id, {})
    for rid, g in new.items():
        g = int(g)
        if not 0 <= g <= 3:
            raise ValueError(f"grade for {rid} must be 0-3")
        cur[rid] = g
    labels["last_edited"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    config.LABELS_PATH.write_text(json.dumps(labels, indent=2))
    return cur


# --------------------------------------------------------------------------- metrics
def dcg(rels: list[int]) -> float:
    return sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rels))


def ndcg_at_k(ranked_ids: list[str], job_grades: dict[str, int], k: int) -> float:
    rels = [job_grades.get(r, 0) for r in ranked_ids[:k]]
    ideal = sorted(job_grades.values(), reverse=True)[:k]
    idcg = dcg(ideal)
    return dcg(rels) / idcg if idcg > 0 else 0.0


def precision_at_k(ranked_ids: list[str], job_grades: dict[str, int], k: int, threshold: int = 2) -> float:
    top = ranked_ids[:k]
    return sum(job_grades.get(r, 0) >= threshold for r in top) / max(1, len(top))


def sign_flip_test(diffs: list[float]) -> float:
    """Exact two-sided paired permutation (sign-flip) test p-value for mean(diffs) != 0."""
    d = np.asarray(diffs, dtype=float)
    if len(d) == 0 or np.allclose(d, 0):
        return 1.0
    obs = abs(d.mean())
    count = total = 0
    for signs in itertools.product((1, -1), repeat=len(d)):
        total += 1
        if abs((d * np.asarray(signs)).mean()) >= obs - 1e-12:
            count += 1
    return count / total


# --------------------------------------------------------------------------- runner
_cache: dict[str, dict] = {}


def evaluate(engine: Engine, k: int = 5, include_rankings: bool = False) -> dict:
    g = grades()
    key = hashlib.sha1(json.dumps([g, k, include_rankings, sorted(engine.resumes), sorted(engine.jobs)],
                                  sort_keys=True).encode()).hexdigest()
    if key in _cache:
        return _cache[key]

    job_ids = [j for j in sorted(engine.jobs) if j in g and g[j]]
    results = []
    rankings: dict[str, dict] = {}
    for method, (label, family) in METHOD_INFO.items():
        for rep in REPRESENTATIONS:
            per_job, per_job10, prec = {}, {}, {}
            for j in job_ids:
                ranked = [r["resume_id"] for r in engine.rank(j, method, rep)]
                per_job[j] = round(ndcg_at_k(ranked, g[j], k), 4)
                per_job10[j] = round(ndcg_at_k(ranked, g[j], 10), 4)
                prec[j] = round(precision_at_k(ranked, g[j], k), 4)
                if include_rankings:
                    rankings.setdefault(f"{method}|{rep}", {})[j] = [
                        {"resume_id": r, "grade": g[j].get(r, 0)} for r in ranked[:k]]
            results.append({
                "method": method, "label": label, "family": family, "representation": rep,
                "mean_ndcg": round(float(np.mean(list(per_job.values()))), 4) if per_job else 0.0,
                "mean_ndcg_10": round(float(np.mean(list(per_job10.values()))), 4) if per_job10 else 0.0,
                "mean_precision": round(float(np.mean(list(prec.values()))), 4) if prec else 0.0,
                "per_job": per_job,
            })
    results.sort(key=lambda r: -r["mean_ndcg"])

    def best(fam: str, rep: Optional[str] = None):
        cands = [r for r in results if r["family"] == fam and (rep is None or r["representation"] == rep)]
        return max(cands, key=lambda r: r["mean_ndcg"]) if cands else None

    s_best, c_best = best("static"), best("contextual")
    comparison = None
    if s_best and c_best:
        diffs = [c_best["per_job"][j] - s_best["per_job"][j] for j in job_ids]
        comparison = {
            "static_best": s_best["mean_ndcg"], "static_method": s_best["method"],
            "static_representation": s_best["representation"],
            "contextual_best": c_best["mean_ndcg"], "contextual_method": c_best["method"],
            "contextual_representation": c_best["representation"],
            "delta": round(c_best["mean_ndcg"] - s_best["mean_ndcg"], 4),
            "jobs_contextual_wins": sum(d > 0 for d in diffs),
            "jobs_ties": sum(abs(d) < 1e-9 for d in diffs),
            "p_value_sign_flip": round(sign_flip_test(diffs), 4),
        }
    # Same comparison restricted to each representation (fair like-for-like).
    by_rep = {}
    for rep in REPRESENTATIONS:
        s, c = best("static", rep), best("contextual", rep)
        if s and c:
            d = [c["per_job"][j] - s["per_job"][j] for j in job_ids]
            by_rep[rep] = {"static_best": s["mean_ndcg"], "static_method": s["method"],
                           "contextual_best": c["mean_ndcg"], "contextual_method": c["method"],
                           "delta": round(c["mean_ndcg"] - s["mean_ndcg"], 4),
                           "jobs_contextual_wins": sum(x > 1e-9 for x in d),
                           "p_value_sign_flip": round(sign_flip_test(d), 4)}

    top = results[0] if results else None
    out = {
        "k": k,
        "n_candidates": len(engine.resumes),
        "jobs": [{"id": j, "title": engine.jobs[j].extracted.title} for j in job_ids],  # type: ignore[union-attr]
        "results": results,
        "best": {"method": top["method"], "representation": top["representation"],
                 "mean_ndcg": top["mean_ndcg"]} if top else None,
        "static_vs_contextual": comparison,
        "static_vs_contextual_by_representation": by_rep,
        "dense_methods_in_vector_db": list(DENSE_METHODS),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if include_rankings:
        out["top_k_rankings"] = rankings
    _cache.clear()
    _cache[key] = out
    return out
