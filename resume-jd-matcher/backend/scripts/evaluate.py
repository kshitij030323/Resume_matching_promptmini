"""Run the full ranking evaluation and write reports/evaluation.{json,md} + a chart.

    python scripts/evaluate.py            (from backend/)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.embeddings import load_glove, tokenize  # noqa: E402
from app.engine import Engine  # noqa: E402
from app.evaluation import evaluate, grades, load_labels  # noqa: E402
from app.skills_taxonomy import SKILLS  # noqa: E402


def glove_oov(engine: Engine) -> dict:
    kv = load_glove()
    rates = []
    for d in engine.resumes.values():
        toks = tokenize(d.raw_text)
        rates.append(sum(t not in kv.key_to_index for t in toks) / max(1, len(toks)))
    missing_skills = []
    for canon in SKILLS:
        toks = tokenize(canon)
        if toks and any(t not in kv.key_to_index for t in toks):
            missing_skills.append(canon)
    return {"mean_token_oov_rate": round(sum(rates) / len(rates), 4),
            "taxonomy_skills_not_in_glove": missing_skills}


def main() -> None:
    engine = Engine()
    ev5 = evaluate(engine, k=5, include_rankings=True)
    ev10 = evaluate(engine, k=10)
    oov = glove_oov(engine)
    labels = load_labels()
    g = grades(labels)

    out = {"ndcg_at_5": ev5, "ndcg_at_10_summary": ev10["results"], "glove_oov": oov}
    (config.REPORTS_DIR / "evaluation.json").write_text(json.dumps(out, indent=2))

    jobs = ev5["jobs"]
    L = []
    L.append("# Ranking evaluation - NDCG@5 against human rankings\n")
    L.append(f"Candidates: **{ev5['n_candidates']}**, job descriptions: **{len(jobs)}**, "
             f"human-graded pairs: **{sum(len(v) for v in g.values())}** (grades 0-3, gain 2^rel-1).\n")
    L.append(f"Label source: {labels.get('annotation_note', 'see data/human_rankings.json')}\n")
    ext = {m: sum(d.meta.method == m for d in engine.resumes.values()) for m in ('llm', 'offline')}
    L.append(f"Resume extraction used: {ext['llm']} via the LLM, {ext['offline']} via the offline parser.\n")

    L.append("\n## Leaderboard\n")
    L.append("| # | Method | Family | Representation | NDCG@5 | NDCG@10 | P@5 (grade>=2) |")
    L.append("|---|---|---|---|---|---|---|")
    for i, r in enumerate(ev5["results"], 1):
        L.append(f"| {i} | {r['label']} | {r['family']} | {r['representation']} | "
                 f"**{r['mean_ndcg']:.3f}** | {r['mean_ndcg_10']:.3f} | {r['mean_precision']:.2f} |")

    c = ev5["static_vs_contextual"]
    if c:
        L.append("\n## Static vs contextual embeddings\n")
        L.append(f"- Best static: **{c['static_method']}** ({c['static_representation']}) - NDCG@5 = {c['static_best']:.3f}")
        L.append(f"- Best contextual: **{c['contextual_method']}** ({c['contextual_representation']}) - NDCG@5 = {c['contextual_best']:.3f}")
        L.append(f"- Difference: **{c['delta']:+.3f}**; contextual better on {c['jobs_contextual_wins']}/{len(jobs)} jobs "
                 f"({c['jobs_ties']} ties); exact paired sign-flip test p = {c['p_value_sign_flip']:.3f} "
                 f"(with only {len(jobs)} queries the smallest attainable p is {2 / 2 ** len(jobs):.3f}).")
        for rep, v in ev5["static_vs_contextual_by_representation"].items():
            L.append(f"- Like-for-like on `{rep}` text: static {v['static_method']} {v['static_best']:.3f} vs "
                     f"contextual {v['contextual_method']} {v['contextual_best']:.3f} (delta {v['delta']:+.3f}; "
                     f"contextual better on {v['jobs_contextual_wins']}/{len(jobs)} jobs, p = {v['p_value_sign_flip']:.3f})")

    L.append("\n## Per-job NDCG@5 (structured representation)\n")
    L.append("| Method | " + " | ".join(f"{j['id']} {j['title'][:22]}" for j in jobs) + " | Mean |")
    L.append("|---|" + "---|" * (len(jobs) + 1))
    for r in [x for x in ev5["results"] if x["representation"] == "structured"]:
        L.append(f"| {r['label']} | " + " | ".join(f"{r['per_job'][j['id']]:.3f}" for j in jobs)
                 + f" | **{r['mean_ndcg']:.3f}** |")

    L.append("\n## Per-job NDCG@5 (raw representation)\n")
    L.append("| Method | " + " | ".join(f"{j['id']}" for j in jobs) + " | Mean |")
    L.append("|---|" + "---|" * (len(jobs) + 1))
    for r in [x for x in ev5["results"] if x["representation"] == "raw"]:
        L.append(f"| {r['label']} | " + " | ".join(f"{r['per_job'][j['id']]:.3f}" for j in jobs)
                 + f" | **{r['mean_ndcg']:.3f}** |")

    L.append("\n## Why static embeddings struggle here (GloVe OOV)\n")
    L.append(f"- Mean share of resume tokens missing from the GloVe-100 vocabulary: "
             f"{oov['mean_token_oov_rate']:.1%}.")
    L.append(f"- Taxonomy skills with at least one token not in GloVe ({len(oov['taxonomy_skills_not_in_glove'])}): "
             + ", ".join(oov["taxonomy_skills_not_in_glove"]))
    L.append("- Words that *are* in the vocabulary carry their 2014 general-English sense "
             "('spark', 'airflow', 'docker', 'rust', 'swift'), so averaging blurs role-specific meaning.")

    L.append("\n## Top-5 per method (job J01 example, structured)\n")
    j0 = jobs[0]["id"]
    for key, per_job in ev5["top_k_rankings"].items():
        method, rep = key.split("|")
        if rep != "structured":
            continue
        row = ", ".join(f"{x['resume_id']}({x['grade']})" for x in per_job[j0])
        L.append(f"- **{method}**: {row}")
    L.append("\nNumbers in brackets are the human grades of the retrieved candidates.\n")
    (config.REPORTS_DIR / "evaluation.md").write_text("\n".join(L))

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        res = ev5["results"]
        methods = list(dict.fromkeys(r["method"] for r in sorted(res, key=lambda r: r["family"])))
        labels_ = {r["method"]: r["label"] for r in res}
        colors = {"static": "#C2410C", "contextual": "#1D4ED8", "hybrid": "#7C3AED", "lexical": "#6B7280"}
        fam = {r["method"]: r["family"] for r in res}
        fig, ax = plt.subplots(figsize=(10, 4.8))
        w = 0.38
        for i, m in enumerate(methods):
            for j, rep in enumerate(("structured", "raw")):
                v = next(r["mean_ndcg"] for r in res if r["method"] == m and r["representation"] == rep)
                ax.bar(i + (j - 0.5) * w, v, w * 0.95, color=colors[fam[m]], alpha=1.0 if rep == "structured" else 0.45)
                ax.text(i + (j - 0.5) * w, v + 0.01, f"{v:.2f}", ha="center", fontsize=8)
        ax.set_xticks(range(len(methods)), [labels_[m] for m in methods], rotation=15, ha="right", fontsize=9)
        ax.set_ylim(0, 1.05)
        ax.set_ylabel("Mean NDCG@5")
        ax.set_title("NDCG@5 vs human rankings (solid = structured text, faded = raw text)")
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        fig.savefig(config.REPORTS_DIR / "ndcg_at_5.png", dpi=150)
    except Exception as exc:  # noqa: BLE001
        print("chart skipped:", exc)

    print("\n".join(L[:40]))
    print(f"\nWrote {config.REPORTS_DIR / 'evaluation.md'}")


if __name__ == "__main__":
    main()
