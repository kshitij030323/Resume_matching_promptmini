"""Deliverable 3 - prompt chain for skill-gap analysis and recommendations.

    Step 1  Requirement alignment   (JD JSON + resume JSON)        -> AlignmentOutput
    Step 2  Gap prioritisation      (step-1 output + JD context)    -> GapAnalysisOutput
    Step 3  Recommendations         (step-2 gaps + candidate)       -> RecommendationOutput
    Step 4  Report synthesis        (steps 1-3)                     -> ReportSynthesis

Each step is a separate, schema-constrained Claude call whose *validated* output is the
input of the next step (a chain, not one giant prompt). This keeps every step small,
auditable (the full trace is returned to the UI) and lets each step be tested alone.

Without an API key the same four steps run offline with deterministic logic
(taxonomy + transferable-skill groups + MiniLM semantic evidence search), so the UI
and the report format are identical in both modes.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Callable, Optional

from . import config
from .engine import Engine, candidate_skill_set, is_tech_role, relevant_years
from .llm import LLMUnavailable, llm_available, structured_call
from .schemas import (
    AlignmentOutput,
    ChainStep,
    Gap,
    GapAnalysisOutput,
    JobSchema,
    Recommendation,
    RecommendationOutput,
    ReportSynthesis,
    RequirementAssessment,
    ResumeSchema,
    SkillGapReport,
    Strength,
)
from .skills_taxonomy import (
    ALT_SEP,
    canonicalize,
    category_of,
    find_skills,
    has_requirement,
    related_skills,
    requirement_parts,
)

# =============================================================================
# Prompts
# =============================================================================
STEP1_SYSTEM = """You are a senior technical recruiter doing a requirement-by-requirement
screen of one candidate against one job. You receive both as structured JSON.

For EVERY skill in the job's required_skills and preferred_skills (in that order), output one
assessment:
- status "met": the resume shows real use of the skill (in experience, projects or a
  credible skills entry). Synonyms count (k8s = Kubernetes, Postgres = PostgreSQL).
- status "partial": no direct evidence, but closely transferable skills exist (e.g. TensorFlow
  for PyTorch, GCP for AWS) or only shallow exposure (a course, a bootcamp, a one-line listing).
- status "missing": no evidence at all.
- evidence: a short quote or paraphrase from the resume that justifies the status; write
  "No evidence" when missing. Never invent evidence.
- transferable_from: candidate skills that partially cover the requirement (empty if none).
Then judge experience_fit ("below", "meets", "exceeds") against min_years_experience and
seniority, with a one-sentence experience_note."""

STEP2_SYSTEM = """You turn a requirement-alignment table into a prioritised gap analysis for a
hiring manager.
- strengths: the 3-6 most relevant met requirements, each with concrete evidence.
- gaps: one entry per requirement with status "partial" or "missing". Severity:
  critical = required and missing; moderate = required but only partial, OR preferred and
  central to the day-to-day responsibilities; minor = other preferred gaps.
  reason: why it matters for THIS role (one sentence). Keep transferable_from from the input.
- fit_score: integer 0-100. Roughly: required coverage dominates (~70%), preferred (~20%),
  experience fit (~10%). A candidate missing several required skills should not exceed 55.
- fit_rationale: 1-2 sentences explaining the score."""

STEP3_SYSTEM = """You are a career coach and engineering manager. Given a candidate's gaps for
a specific role, write an actionable development plan.
- One recommendation for every critical and moderate gap, and for the most useful minor gaps
  (at most 8 in total), ordered by priority.
- action: a concrete, specific step (what to build/learn/do), leveraging the candidate's
  transferable skills where possible.
- type: course | project | certification | on_the_job | reading.
- resource_hint: a well-known, real resource type or certification name (e.g. "CKAD
  certification", "official PyTorch tutorials"); do not fabricate URLs.
- effort_weeks: realistic part-time effort; less when transferable skills exist.
- priority: high for critical, medium for moderate, low for minor.
- interview_questions: 4-6 questions that probe the biggest gaps and verify the claimed
  strengths for this role."""

STEP4_SYSTEM = """You write the final summary of a candidate skill-gap report for a hiring
manager. Be factual, specific and fair; do not repeat every detail.
- verdict: strong_match (fit >= 80), good_match (65-79), partial_match (45-64), weak_match (< 45),
  consistent with the given fit score.
- headline: one line (<= 14 words) capturing the candidate's fit.
- executive_summary: 3-4 sentences covering strongest evidence, the most important gaps,
  and how quickly they could be closed.
- hiring_recommendation: one or two sentences: advance / advance with focus areas / hold /
  do not advance, and what to verify in interview."""


def _j(obj) -> str:
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump()
    return json.dumps(obj, indent=1, ensure_ascii=False)


def _job_ctx(job: JobSchema) -> dict:
    return {"title": job.title, "seniority": job.seniority, "min_years_experience": job.min_years_experience,
            "required_skills": job.required_skills, "preferred_skills": job.preferred_skills,
            "responsibilities": job.responsibilities, "domain": job.domain}


def _cand_ctx(r: ResumeSchema) -> dict:
    return {"name": r.name, "headline": r.headline, "total_years_experience": r.total_years_experience,
            "seniority": r.seniority, "skills": [s.name for s in r.skills],
            "recent_roles": [f"{e.title} at {e.company}" for e in r.experience[:3]]}


# =============================================================================
# LLM implementations of each step
# =============================================================================
def llm_step1(job: JobSchema, r: ResumeSchema):
    return structured_call(system=STEP1_SYSTEM, output_model=AlignmentOutput, effort=config.CHAIN_EFFORT,
                           user=f"<job>\n{_j(job)}\n</job>\n<candidate>\n{_j(r)}\n</candidate>")


def llm_step2(job: JobSchema, r: ResumeSchema, s1: AlignmentOutput):
    return structured_call(system=STEP2_SYSTEM, output_model=GapAnalysisOutput, effort=config.CHAIN_EFFORT,
                           user=f"<job_context>\n{_j(_job_ctx(job))}\n</job_context>\n"
                                f"<alignment>\n{_j(s1)}\n</alignment>")


def llm_step3(job: JobSchema, r: ResumeSchema, s2: GapAnalysisOutput):
    return structured_call(system=STEP3_SYSTEM, output_model=RecommendationOutput, effort=config.CHAIN_EFFORT,
                           user=f"<job_context>\n{_j(_job_ctx(job))}\n</job_context>\n"
                                f"<candidate>\n{_j(_cand_ctx(r))}\n</candidate>\n"
                                f"<gap_analysis>\n{_j(s2)}\n</gap_analysis>")


def llm_step4(job: JobSchema, r: ResumeSchema, s1, s2, s3):
    return structured_call(system=STEP4_SYSTEM, output_model=ReportSynthesis, effort=config.CHAIN_EFFORT,
                           user=f"<job_context>\n{_j(_job_ctx(job))}\n</job_context>\n"
                                f"<candidate>\n{_j(_cand_ctx(r))}\n</candidate>\n"
                                f"<experience_fit>{s1.experience_fit}: {s1.experience_note}</experience_fit>\n"
                                f"<gap_analysis>\n{_j(s2)}\n</gap_analysis>\n"
                                f"<recommendations>\n{_j(s3)}\n</recommendations>")


# =============================================================================
# Offline implementations of each step
# =============================================================================
class OfflineChain:
    def __init__(self, engine: Engine):
        self.engine = engine

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _sentences(r: ResumeSchema, raw: str) -> list[str]:
        sents = [h for e in r.experience for h in e.highlights]
        sents += [f"{p.name}: {p.description}" for p in r.projects]
        sents += [c for c in r.certifications]
        if r.summary:
            sents += re.split(r"(?<=[.!?])\s+", r.summary)
        return [s.strip() for s in sents if len(s.strip()) > 12] or [l for l in raw.splitlines() if len(l) > 20]

    @staticmethod
    def _evidence(skill: str, r: ResumeSchema, rel_years: float) -> tuple[str, str]:
        """Return (strength, evidence) where strength is strong | weak | none.

        strong: used in a technical role of >= 6 months, or in a project/role backed by
                at least a year of technical experience;
        weak:   only claimed in the skills list / summary, or only seen in a short or
                non-technical role (tutorial, bootcamp) - i.e. not demonstrated.
        """
        def mentions(text: str, weak_ok: bool) -> bool:
            return skill in {c for c, _ in find_skills(text, allow_weak=weak_ok)}

        weak_hit = None
        for weak_ok in (False, True):  # prefer unambiguous aliases for evidence quotes
            for e in r.experience:
                in_role = skill in e.technologies or any(mentions(h, weak_ok) for h in e.highlights) \
                    or mentions(e.title, weak_ok)
                if not in_role:
                    continue
                quote = next((h for h in e.highlights if mentions(h, weak_ok)), f"Used as {e.title} at {e.company}")
                if is_tech_role(e.title) and (e.duration_years or 0) >= 0.5:
                    return "strong", quote
                weak_hit = weak_hit or f"Only in a short or non-technical role ({e.title}): {quote}"
        for p in r.projects:
            if skill in p.technologies or mentions(p.description, True):
                if rel_years >= 1:
                    return "strong", f"Project {p.name}: {p.description}"
                weak_hit = weak_hit or f"Only in a personal project ({p.name})"
        if weak_hit:
            return "weak", weak_hit
        listed = next((s for s in r.skills if s.name == skill), None)
        if listed is not None:
            if rel_years >= 2:
                # an experienced engineer listing a core tool is credible even if no bullet names it
                return "strong", (f"Listed in skills (not named in role bullets; backed by "
                                  f"{rel_years:g} yrs of technical experience)")
            return "weak", "Claimed in skills list without supporting experience"
        return "weak", "Mentioned in the summary only"

    # -- step 1 ---------------------------------------------------------------
    def step1(self, job: JobSchema, r: ResumeSchema, raw: str) -> AlignmentOutput:
        have = candidate_skill_set(r)
        rel_years = relevant_years(r)
        sents = self._sentences(r, raw)
        reqs = [(s, "required") for s in job.required_skills] + [(s, "preferred") for s in job.preferred_skills]
        # Semantic evidence search for requirements with no lexical hit (MiniLM cosine).
        missing_lex = list(dict.fromkeys(s for s, _ in reqs if not has_requirement(s, have)))
        sem = self.engine.minilm.similarity_matrix(
            [s.replace(ALT_SEP, " or ") for s in missing_lex], sents) if missing_lex and sents else None
        assessments = []
        for skill, imp in reqs:
            hits = has_requirement(skill, have)
            if hits:
                # for "A / B" take the best-evidenced option the candidate has
                graded = [(self._evidence(h, r, rel_years), h) for h in hits]
                graded.sort(key=lambda x: x[0][0] != "strong")
                (strength, ev), canon = graded[0]
                status = "met" if strength == "strong" else "partial"
                if len(requirement_parts(skill)) > 1:
                    ev = f"[{canon}] {ev}"
                assessments.append(RequirementAssessment(
                    skill=skill, importance=imp, status=status, evidence=ev,
                    transferable_from=[] if status == "met" else related_skills(skill, have)))
                continue
            rel = related_skills(skill, have)
            best_sent, best_sim = None, 0.0
            if sem is not None:
                row = sem[missing_lex.index(skill)]
                idx = int(row.argmax())
                best_sent, best_sim = sents[idx], float(row[idx])
            if rel:
                ev = f"Transferable experience with {', '.join(rel[:3])}"
                assessments.append(RequirementAssessment(skill=skill, importance=imp, status="partial",
                                                         evidence=ev, transferable_from=rel[:4]))
            elif best_sent and best_sim >= (0.40 if all(category_of(x) == "soft_skill" for x in requirement_parts(skill)) else 0.55):
                assessments.append(RequirementAssessment(
                    skill=skill, importance=imp, status="partial",
                    evidence=f"Semantically related: \"{best_sent[:160]}\"", transferable_from=[]))
            else:
                assessments.append(RequirementAssessment(skill=skill, importance=imp, status="missing",
                                                         evidence="No evidence", transferable_from=[]))
        need = job.min_years_experience
        yrs = rel_years
        extra = (f" ({r.total_years_experience:g} yrs total incl. non-technical roles)"
                 if r.total_years_experience - yrs >= 1 else "")
        if need is None:
            fit, note = "meets", f"No minimum stated; {yrs:g} years in technical roles{extra}."
        elif yrs < need * 0.8:
            fit, note = "below", f"{yrs:g} years in technical roles vs {need:g}+ required{extra}."
        elif yrs > need * 1.6 and yrs - need >= 4:
            fit, note = "exceeds", f"{yrs:g} years in technical roles vs {need:g}+ required{extra}."
        else:
            fit, note = "meets", f"{yrs:g} years in technical roles vs {need:g}+ required{extra}."
        return AlignmentOutput(assessments=assessments, experience_fit=fit, experience_note=note)

    # -- step 2 ---------------------------------------------------------------
    def step2(self, job: JobSchema, s1: AlignmentOutput) -> GapAnalysisOutput:
        resp_text = " ".join(job.responsibilities)
        resp_skills = {c for c, _ in find_skills(resp_text)}
        strengths = [Strength(skill=a.skill, evidence=a.evidence) for a in s1.assessments
                     if a.status == "met"][:6]
        gaps = []
        for a in s1.assessments:
            if a.status == "met":
                continue
            if a.importance == "required":
                sev = "critical" if a.status == "missing" else "moderate"
                why = "Listed as a must-have for this role."
            else:
                central = any(p in resp_skills for p in requirement_parts(a.skill))
                sev = "moderate" if central and a.status == "missing" else "minor"
                why = ("Used in the role's day-to-day responsibilities." if central
                       else "Nice-to-have that would speed up onboarding.")
            if a.transferable_from:
                why += f" Partly offset by {', '.join(a.transferable_from[:3])}."
            gaps.append(Gap(skill=a.skill, importance=a.importance, severity=sev, reason=why,
                            transferable_from=a.transferable_from))
        order = {"critical": 0, "moderate": 1, "minor": 2}
        gaps.sort(key=lambda g: order[g.severity])

        def cov(imp):
            items = [a for a in s1.assessments if a.importance == imp]
            if not items:
                return 1.0
            return sum(1.0 if a.status == "met" else 0.5 if a.status == "partial" else 0.0 for a in items) / len(items)

        exp = {"below": 0.3, "meets": 1.0, "exceeds": 0.9}[s1.experience_fit]
        req_cov, pref_cov = cov("required"), cov("preferred")
        score = round(100 * (0.7 * req_cov + 0.2 * pref_cov + 0.1 * exp))
        n_crit = sum(g.severity == "critical" for g in gaps)
        if n_crit >= 3:
            score = min(score, 55)
        req_items = [a for a in s1.assessments if a.importance == "required"]
        met_share = (sum(a.status == "met" for a in req_items) / len(req_items)) if req_items else 1.0
        if met_share == 0:
            score = min(score, 35)      # nothing demonstrated - only claims or transferable skills
        elif met_share < 0.34:
            score = min(score, 50)
        rationale = (f"Covers {req_cov:.0%} of required and {pref_cov:.0%} of preferred skills "
                     f"(partial/undemonstrated at half credit); {met_share:.0%} of must-haves are "
                     f"demonstrated in technical roles; experience {s1.experience_fit} the bar.")
        return GapAnalysisOutput(strengths=strengths, gaps=gaps, fit_score=int(score), fit_rationale=rationale)

    # -- step 3 ---------------------------------------------------------------
    def step3(self, job: JobSchema, r: ResumeSchema, s2: GapAnalysisOutput) -> RecommendationOutput:
        recs = []
        for g in [x for x in s2.gaps if x.severity != "minor"] + [x for x in s2.gaps if x.severity == "minor"]:
            if len(recs) >= 8:
                break
            recs.append(_offline_recommendation(g, job))
        qs = []
        for g in s2.gaps[:3]:
            if g.transferable_from:
                qs.append(f"You haven't used {g.skill} directly - how would your {g.transferable_from[0]} "
                          f"experience carry over, and what would you need to learn first?")
            else:
                qs.append(f"This role relies on {g.skill}. What exposure have you had to it, and how "
                          f"would you ramp up in your first 60 days?")
        for s in s2.strengths[:3]:
            qs.append(f"Walk me through the most complex thing you built with {s.skill}: "
                      f"design choices, trade-offs and measurable results.")
        if job.min_years_experience and relevant_years(r) < job.min_years_experience:
            qs.append(f"The role targets {job.min_years_experience:g}+ years. Which of your projects "
                      f"best shows you operating at that level of ownership?")
        return RecommendationOutput(recommendations=recs, interview_questions=qs[:6])

    # -- step 4 ---------------------------------------------------------------
    def step4(self, job: JobSchema, r: ResumeSchema, s1: AlignmentOutput, s2: GapAnalysisOutput,
              s3: RecommendationOutput) -> ReportSynthesis:
        f = s2.fit_score
        verdict = "strong_match" if f >= 80 else "good_match" if f >= 65 else "partial_match" if f >= 45 else "weak_match"
        crit = [g.skill for g in s2.gaps if g.severity == "critical"]
        mod = [g.skill for g in s2.gaps if g.severity == "moderate"]
        top_str = ", ".join(s.skill for s in s2.strengths[:3]) or "few of the core requirements"
        weeks = sum(x.effort_weeks for x in s3.recommendations if x.priority in ("high", "medium"))
        label = verdict.replace("_", " ")
        headline = f"{label.capitalize()} for {job.title}: strong in {top_str}" if s2.strengths else \
            f"{label.capitalize()} for {job.title}"
        intro = (f"{r.name} ({r.headline}, {relevant_years(r):g} yrs in technical roles) "
                 + (f"shows clear evidence of {top_str}. " if s2.strengths else
                    "does not demonstrate any of the core requirements in technical work; matching skills are "
                    "only claimed in the skills list or covered by adjacent skills. "))
        if crit:
            gaps_txt = f"Critical gaps: {', '.join(crit[:4])}. "
        elif s2.strengths:
            gaps_txt = "No must-have skill is entirely missing. "
        else:
            gaps_txt = ""
        summary = (intro + gaps_txt
                   + (f"Partially covered: {', '.join(mod[:4])}{' and more' if len(mod) > 4 else ''}. " if mod else "")
                   + (f"The high/medium-priority plan totals roughly {weeks:g} weeks of part-time effort. " if weeks else "")
                   + f"Experience: {s1.experience_note}")
        if verdict == "strong_match":
            rec = "Advance to technical interviews; verify depth on the listed strengths."
        elif verdict == "good_match":
            rec = f"Advance with focus areas: probe {', '.join((crit + mod)[:2]) or 'the minor gaps'} in interview."
        elif verdict == "partial_match":
            rec = f"Hold or consider for a more junior/adjacent role unless {', '.join(crit[:2]) or 'the gaps'} can be closed quickly."
        else:
            rec = "Do not advance for this role; the core requirements are not evidenced."
        return ReportSynthesis(verdict=verdict, headline=headline[:120], executive_summary=summary,
                               hiring_recommendation=rec)


_RESOURCES: dict[str, tuple[str, str, str, float]] = {
    # skill: (action, type, resource_hint, base_weeks)
    "Kubernetes": ("Deploy a small multi-service app to a local kind/minikube cluster with Helm, probes and autoscaling", "certification", "CKAD (Certified Kubernetes Application Developer)", 6),
    "Docker": ("Containerise an existing project with a multi-stage Dockerfile and docker compose", "project", "Docker official 'Get started' guide", 2),
    "Terraform": ("Codify a VPC + compute + database stack in Terraform with remote state and modules", "certification", "HashiCorp Terraform Associate", 4),
    "AWS": ("Build and deploy a service using EC2/ECS, S3, IAM and CloudWatch", "certification", "AWS Solutions Architect - Associate", 6),
    "GCP": ("Deploy a service on Cloud Run with BigQuery and Pub/Sub", "certification", "Google Associate Cloud Engineer", 5),
    "Azure": ("Deploy a containerised app on AKS / App Service", "certification", "Microsoft Azure Fundamentals (AZ-900) then AZ-204", 5),
    "PyTorch": ("Re-implement a model you know in PyTorch, including a training loop and evaluation", "course", "Official PyTorch tutorials", 4),
    "TensorFlow": ("Port a small model to TensorFlow/Keras and serve it", "course", "TensorFlow Developer curriculum", 4),
    "LLMs": ("Build an LLM feature end-to-end: prompt design, structured outputs, evaluation set", "project", "Provider docs on prompt engineering and evals", 4),
    "RAG": ("Build a retrieval-augmented QA app with chunking, a vector index and an eval set", "project", "LangChain / LlamaIndex RAG tutorials", 3),
    "Transformers": ("Fine-tune a pre-trained transformer for a text-classification task", "course", "Hugging Face NLP course", 4),
    "NLP": ("Ship a text-classification or extraction pipeline with error analysis", "course", "Hugging Face NLP course", 5),
    "MLOps": ("Add experiment tracking, model registry and CI-based deployment to an ML project", "project", "MLflow docs / Made With ML", 4),
    "SQL": ("Solve 40+ analytical SQL problems with window functions and CTEs", "course", "Mode SQL tutorial / LeetCode SQL 50", 3),
    "Python": ("Build and test a small CLI/data tool in idiomatic, typed Python", "course", "Official Python tutorial + pytest docs", 4),
    "Go": ("Write a REST service in Go with tests, context handling and graceful shutdown", "project", "'Tour of Go' + 'Let's Go' book", 5),
    "Apache Spark": ("Process a multi-GB public dataset with PySpark DataFrames and tune partitions", "course", "Databricks Spark fundamentals", 4),
    "Apache Airflow": ("Orchestrate an ETL with an Airflow DAG: retries, sensors, backfills", "project", "Astronomer Airflow fundamentals", 3),
    "Apache Kafka": ("Build a producer/consumer pipeline with schema registry and consumer groups", "course", "Confluent Kafka fundamentals", 3),
    "dbt": ("Model a small warehouse with dbt: staging, marts, tests and docs", "course", "dbt Fundamentals (dbt Labs)", 2),
    "Tableau": ("Recreate a business dashboard with filters, LOD calcs and a story", "course", "Tableau Desktop Specialist", 3),
    "Power BI": ("Build a Power BI report with a star-schema model and DAX measures", "certification", "Microsoft PL-300 (Power BI Data Analyst)", 4),
    "React Native": ("Ship a small React Native app with navigation, offline storage and a store build", "project", "React Native docs + Expo tutorial", 5),
    "TypeScript": ("Migrate a JavaScript project to strict TypeScript", "course", "TypeScript Handbook", 2),
    "iOS": ("Take a React Native/Swift app through TestFlight to an App Store release", "on_the_job", "Apple App Store Connect documentation", 2),
    "Android": ("Publish an app to the Play Console internal track with signing and CI", "on_the_job", "Android developers - publish your app", 2),
    "CI/CD": ("Set up a pipeline with tests, linting, build and automated deploy (e.g. GitHub Actions)", "project", "GitHub Actions documentation", 2),
    "Prometheus": ("Instrument a service with Prometheus metrics, Grafana dashboards and alerts", "project", "Prometheus 'Getting started' + Grafana tutorials", 2),
    "Observability": ("Define SLIs/SLOs for a service and add metrics, logs, traces and alerting", "reading", "Google SRE Workbook (SLO chapters)", 3),
    "SRE": ("Run an incident-response game day and write a blameless postmortem", "reading", "Google 'Site Reliability Engineering' book", 3),
    "Statistics": ("Analyse an A/B test end to end: power, significance, confidence intervals", "course", "Khan Academy statistics / 'Trustworthy Online Controlled Experiments'", 4),
    "A/B Testing": ("Design and analyse an experiment including power analysis and guardrails", "reading", "'Trustworthy Online Controlled Experiments' (Kohavi et al.)", 3),
    "Data Warehousing": ("Design a star schema for a business process and load it", "reading", "'The Data Warehouse Toolkit' (Kimball)", 4),
    "Stakeholder Management": ("Own a reporting request end to end with a business stakeholder", "on_the_job", "Shadow a senior analyst / PM", 4),
    "Communication": ("Present an analysis to a non-technical audience and collect feedback", "on_the_job", "Internal demo days / Toastmasters", 3),
    "Leadership": ("Lead a small project or mentor a junior engineer for a quarter", "on_the_job", "'The Manager's Path' (Fournier)", 8),
    "Microservices": ("Split a monolith feature into a service with its own API, data and contracts", "project", "'Building Microservices' (Newman)", 5),
    "System Design": ("Write design docs for 3 classic systems and review trade-offs", "reading", "'Designing Data-Intensive Applications'", 6),
    "PostgreSQL": ("Model, index and tune queries on a realistic schema (EXPLAIN ANALYZE)", "course", "PostgreSQL official tutorial", 3),
}

_CATEGORY_DEFAULT = {
    "programming_language": ("project", "official language tutorial", 4),
    "framework_library": ("project", "official framework documentation", 3),
    "ml_ai": ("course", "a reputable ML course plus a portfolio project", 4),
    "data": ("course", "vendor fundamentals course", 3),
    "cloud_devops": ("certification", "the vendor's associate-level certification", 4),
    "database": ("course", "official database documentation", 3),
    "mobile_frontend": ("project", "official docs and a shipped sample app", 4),
    "tool": ("course", "official documentation", 1),
    "methodology": ("on_the_job", "team practice with a mentor", 3),
    "soft_skill": ("on_the_job", "stretch assignment with a mentor", 6),
    "domain": ("reading", "domain primers and customer conversations", 4),
    "other": ("course", "a structured online course", 3),
}


def _related_pair(a: str, b: str) -> bool:
    return bool(related_skills(a, {b}))


def _offline_recommendation(g: Gap, job: JobSchema) -> Recommendation:
    parts = requirement_parts(g.skill)
    # for "A / B / C" pick the option the candidate is closest to (or one we have a plan for)
    canon = next((p for p in parts if any(_related_pair(p, t) for t in g.transferable_from)), None) \
        or next((p for p in parts if p in _RESOURCES), parts[0] if parts else canonicalize(g.skill))
    if canon in _RESOURCES:
        action, typ, hint, weeks = _RESOURCES[canon]
    else:
        typ, hint, weeks = _CATEGORY_DEFAULT.get(category_of(canon), _CATEGORY_DEFAULT["other"])
        action = f"Build a small project that uses {g.skill} the way a {job.title} would"
    if g.transferable_from:
        weeks = max(1.0, weeks / 2)
        action += f" - leverage existing {', '.join(g.transferable_from[:2])} experience"
    if g.severity == "minor":
        weeks = max(1.0, weeks / 2)
    priority = {"critical": "high", "moderate": "medium", "minor": "low"}[g.severity]
    if len(parts) > 1:
        action = f"(any one of {', '.join(parts)}) " + action
    return Recommendation(skill=g.skill, action=action, type=typ, resource_hint=hint,  # type: ignore[arg-type]
                          effort_weeks=float(weeks), priority=priority)  # type: ignore[arg-type]


# =============================================================================
# Chain runner
# =============================================================================
def _timed(fn: Callable, *args):
    t0 = time.perf_counter()
    out = fn(*args)
    return out, int((time.perf_counter() - t0) * 1000)


def run_chain(engine: Engine, job_id: str, resume_id: str, use_llm: bool = True) -> SkillGapReport:
    if job_id not in engine.jobs:
        raise KeyError(f"Unknown job {job_id}")
    if resume_id not in engine.resumes:
        raise KeyError(f"Unknown resume {resume_id}")
    job: JobSchema = engine.jobs[job_id].extracted  # type: ignore[assignment]
    r: ResumeSchema = engine.resumes[resume_id].extracted  # type: ignore[assignment]
    raw = engine.resumes[resume_id].raw_text
    off = OfflineChain(engine)
    trace: list[ChainStep] = []
    mode_llm = use_llm and llm_available()

    def step(n: int, name: str, llm_fn: Callable, off_fn: Callable, llm_args: tuple, off_args: tuple):
        nonlocal mode_llm
        if mode_llm:
            try:
                (out, meta), _ = _timed(llm_fn, *llm_args)
                trace.append(ChainStep(step=n, name=name, mode="llm", model=meta["model"],
                                       latency_ms=meta["latency_ms"], output=out.model_dump()))
                return out
            except LLMUnavailable as exc:
                mode_llm = False  # degrade the rest of the chain gracefully
                name = f"{name} (offline fallback: {str(exc)[:80]})"
        out, ms = _timed(off_fn, *off_args)
        trace.append(ChainStep(step=n, name=name, mode="offline", model=None, latency_ms=ms,
                               output=out.model_dump()))
        return out

    s1 = step(1, "Requirement alignment", llm_step1, off.step1, (job, r), (job, r, raw))
    s2 = step(2, "Gap prioritisation", llm_step2, off.step2, (job, r, s1), (job, s1))
    s3 = step(3, "Recommendations", llm_step3, off.step3, (job, r, s2), (job, r, s2))
    s4 = step(4, "Report synthesis", llm_step4, off.step4, (job, r, s1, s2, s3), (job, r, s1, s2, s3))

    return SkillGapReport(
        job_id=job_id, resume_id=resume_id, candidate_name=r.name, job_title=job.title,
        fit_score=max(0, min(100, int(s2.fit_score))), verdict=s4.verdict, headline=s4.headline,
        executive_summary=s4.executive_summary, hiring_recommendation=s4.hiring_recommendation,
        experience_fit=s1.experience_fit, experience_note=s1.experience_note,
        assessments=s1.assessments, strengths=s2.strengths, gaps=s2.gaps,
        recommendations=s3.recommendations, interview_questions=s3.interview_questions,
        chain_trace=trace, generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
