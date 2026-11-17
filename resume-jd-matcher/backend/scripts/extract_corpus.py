"""(Re-)extract every resume and JD into the fixed JSON schema and export it.

    python scripts/extract_corpus.py            # offline parser (or cached results)
    python scripts/extract_corpus.py --llm      # re-extract everything with the configured LLM (Gemini or Claude)

Writes reports/extracted_corpus.json and, when --llm is used, compares the LLM and
offline skill sets per document (Jaccard) as a quick extraction-agreement check.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.engine import Engine  # noqa: E402
from app.extraction import normalise_job, normalise_resume, offline_extract_job, offline_extract_resume  # noqa: E402
from app.llm import llm_available  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="re-extract with the configured LLM (Gemini or Claude)")
    args = ap.parse_args()

    engine = Engine()
    if args.llm:
        if not llm_available():
            sys.exit("No LLM configured - set GEMINI_API_KEY (or ANTHROPIC_API_KEY), or save a key on the Settings page.")
        print("Re-extracting corpus with the configured LLM ...")
        print(engine.reextract_all(use_llm=True))

    corpus = {
        "resumes": {d.id: {"extracted": d.extracted.model_dump(), "meta": d.meta.model_dump()} for d in engine.resumes.values()},
        "jobs": {d.id: {"extracted": d.extracted.model_dump(), "meta": d.meta.model_dump()} for d in engine.jobs.values()},
    }
    (config.REPORTS_DIR / "extracted_corpus.json").write_text(json.dumps(corpus, indent=2))
    print(f"Wrote {config.REPORTS_DIR / 'extracted_corpus.json'}")

    if args.llm:
        rows = []
        for d in engine.resumes.values():
            off, _ = normalise_resume(offline_extract_resume(d.raw_text))
            a = {s.name.lower() for s in off.skills}
            b = {s.name.lower() for s in d.extracted.skills}  # type: ignore[union-attr]
            rows.append((d.id, len(a & b) / max(1, len(a | b))))
        for d in engine.jobs.values():
            off, _ = normalise_job(offline_extract_job(d.raw_text))
            a = {s.lower() for s in off.required_skills + off.preferred_skills}
            b = {s.lower() for s in d.extracted.required_skills + d.extracted.preferred_skills}  # type: ignore[union-attr]
            rows.append((d.id, len(a & b) / max(1, len(a | b))))
        print("\nSkill-set agreement (Jaccard) offline parser vs LLM:")
        for doc_id, jac in rows:
            print(f"  {doc_id}: {jac:.2f}")
        print(f"  mean: {sum(j for _, j in rows) / len(rows):.2f}")


if __name__ == "__main__":
    main()
