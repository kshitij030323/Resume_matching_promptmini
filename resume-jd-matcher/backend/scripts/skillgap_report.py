"""Generate skill-gap reports for the shortlisted candidates of a job.

    python scripts/skillgap_report.py J01 --method hybrid --top 5 [--offline]

Writes reports/skillgap_<JOB>.json and a readable reports/skillgap_<JOB>.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.engine import Engine  # noqa: E402
from app.skillgap import run_chain  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("job_id")
    ap.add_argument("--method", default="hybrid")
    ap.add_argument("--representation", default="structured")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--offline", action="store_true", help="force the offline chain")
    args = ap.parse_args()

    engine = Engine()
    shortlist = engine.rank(args.job_id, args.method, args.representation, args.top)
    reports = [run_chain(engine, args.job_id, r["resume_id"], use_llm=not args.offline) for r in shortlist]

    (config.REPORTS_DIR / f"skillgap_{args.job_id}.json").write_text(
        json.dumps([r.model_dump() for r in reports], indent=2))

    job = engine.jobs[args.job_id].extracted
    L = [f"# Skill-gap reports - {job.title} ({args.job_id})\n",  # type: ignore[union-attr]
         f"Shortlist: top {args.top} by `{args.method}` ({args.representation}).\n"]
    for rank, (row, rep) in enumerate(zip(shortlist, reports), 1):
        modes = {s.mode for s in rep.chain_trace}
        L.append(f"## {rank}. {rep.candidate_name} ({rep.resume_id}) - fit {rep.fit_score}/100, "
                 f"{rep.verdict.replace('_', ' ')}  \n*chain mode: {', '.join(sorted(modes))}*\n")
        L.append(f"**{rep.headline}**\n\n{rep.executive_summary}\n")
        L.append("**Strengths:** " + "; ".join(f"{s.skill} ({s.evidence[:80]})" for s in rep.strengths) + "\n")
        if rep.gaps:
            L.append("| Gap | Importance | Severity | Transferable from |\n|---|---|---|---|")
            for g in rep.gaps:
                L.append(f"| {g.skill} | {g.importance} | {g.severity} | {', '.join(g.transferable_from) or '-'} |")
        L.append("\n**Plan:**")
        for r in rep.recommendations:
            L.append(f"- [{r.priority}] {r.skill}: {r.action} ({r.type}; {r.resource_hint}; ~{r.effort_weeks:g} wks)")
        L.append("\n**Interview focus:**")
        L.extend(f"- {q}" for q in rep.interview_questions)
        L.append(f"\n**Recommendation:** {rep.hiring_recommendation}\n")
    out = config.REPORTS_DIR / f"skillgap_{args.job_id}.md"
    out.write_text("\n".join(L))
    print("\n".join(L))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
