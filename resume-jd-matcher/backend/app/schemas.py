"""Fixed JSON schemas for the whole system (Deliverable 1 + 3).

Every resume and job description, whether extracted by Claude or by the offline
heuristic extractor, is validated against exactly these Pydantic models, so the
ranking module and the skill-gap chain always see the same shape.

The LLM-facing models avoid numeric constraints (ge/le) because structured
outputs only support a subset of JSON Schema; ranges are enforced afterwards in
`normalise_*` helpers instead.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# Shared enums
# --------------------------------------------------------------------------- #
SkillCategory = Literal[
    "programming_language",
    "framework_library",
    "ml_ai",
    "data",
    "cloud_devops",
    "database",
    "mobile_frontend",
    "tool",
    "methodology",
    "soft_skill",
    "domain",
    "other",
]
Proficiency = Literal["beginner", "intermediate", "advanced", "expert", "unknown"]
Seniority = Literal["intern", "junior", "mid", "senior", "lead", "principal", "unknown"]


# --------------------------------------------------------------------------- #
# Resume schema
# --------------------------------------------------------------------------- #
class SkillItem(BaseModel):
    name: str = Field(description="Canonical skill name, e.g. 'Kubernetes' not 'k8s'.")
    category: SkillCategory
    years: Optional[float] = Field(description="Years of hands-on use if inferable, else null.")
    proficiency: Proficiency


class ExperienceItem(BaseModel):
    title: str
    company: str
    start: Optional[str] = Field(description="Start date as YYYY-MM, or null.")
    end: Optional[str] = Field(description="End date as YYYY-MM, 'present', or null.")
    duration_years: Optional[float]
    highlights: list[str] = Field(description="Achievement bullets, rewritten concisely.")
    technologies: list[str] = Field(description="Canonical tools/skills used in this role.")


class EducationItem(BaseModel):
    degree: str
    field: Optional[str]
    institution: str
    year: Optional[int]


class ProjectItem(BaseModel):
    name: str
    description: str
    technologies: list[str]


class ResumeSchema(BaseModel):
    name: str
    email: Optional[str]
    phone: Optional[str]
    location: Optional[str]
    headline: str = Field(description="Current or target job title in a few words.")
    summary: str = Field(description="2-3 sentence professional summary.")
    total_years_experience: float
    seniority: Seniority
    skills: list[SkillItem]
    experience: list[ExperienceItem]
    education: list[EducationItem]
    certifications: list[str]
    projects: list[ProjectItem]


# --------------------------------------------------------------------------- #
# Job description schema
# --------------------------------------------------------------------------- #
class JobSchema(BaseModel):
    title: str
    company: Optional[str]
    location: Optional[str]
    employment_type: Optional[str]
    seniority: Seniority
    min_years_experience: Optional[float]
    summary: str
    required_skills: list[str] = Field(description="Canonical must-have skills.")
    preferred_skills: list[str] = Field(description="Canonical nice-to-have skills.")
    responsibilities: list[str]
    education_requirement: Optional[str]
    domain: Optional[str] = Field(description="Industry/domain such as 'fintech', or null.")


# --------------------------------------------------------------------------- #
# Skill-gap prompt chain (Deliverable 3) - one model per chain step
# --------------------------------------------------------------------------- #
class RequirementAssessment(BaseModel):
    skill: str
    importance: Literal["required", "preferred"]
    status: Literal["met", "partial", "missing"]
    evidence: str = Field(description="Short quote/paraphrase from the resume, or 'No evidence'.")
    transferable_from: list[str] = Field(description="Candidate skills that partially cover this one.")


class AlignmentOutput(BaseModel):
    """Step 1 - requirement-by-requirement alignment."""

    assessments: list[RequirementAssessment]
    experience_fit: Literal["below", "meets", "exceeds"]
    experience_note: str


class Strength(BaseModel):
    skill: str
    evidence: str


class Gap(BaseModel):
    skill: str
    importance: Literal["required", "preferred"]
    severity: Literal["critical", "moderate", "minor"]
    reason: str
    transferable_from: list[str]


class GapAnalysisOutput(BaseModel):
    """Step 2 - prioritised gaps, strengths and a fit score (0-100)."""

    strengths: list[Strength]
    gaps: list[Gap]
    fit_score: int
    fit_rationale: str


class Recommendation(BaseModel):
    skill: str
    action: str
    type: Literal["course", "project", "certification", "on_the_job", "reading"]
    resource_hint: str
    effort_weeks: float
    priority: Literal["high", "medium", "low"]


class RecommendationOutput(BaseModel):
    """Step 3 - learning plan + interview probes."""

    recommendations: list[Recommendation]
    interview_questions: list[str]


class ReportSynthesis(BaseModel):
    """Step 4 - executive summary for the hiring manager."""

    verdict: Literal["strong_match", "good_match", "partial_match", "weak_match"]
    headline: str
    executive_summary: str
    hiring_recommendation: str


class ChainStep(BaseModel):
    step: int
    name: str
    mode: Literal["llm", "offline"]
    model: Optional[str]
    latency_ms: int
    output: dict


class SkillGapReport(BaseModel):
    job_id: str
    resume_id: str
    candidate_name: str
    job_title: str
    fit_score: int
    verdict: Literal["strong_match", "good_match", "partial_match", "weak_match"]
    headline: str
    executive_summary: str
    hiring_recommendation: str
    experience_fit: Literal["below", "meets", "exceeds"]
    experience_note: str
    assessments: list[RequirementAssessment]
    strengths: list[Strength]
    gaps: list[Gap]
    recommendations: list[Recommendation]
    interview_questions: list[str]
    chain_trace: list[ChainStep]
    generated_at: str


# --------------------------------------------------------------------------- #
# Extraction metadata
# --------------------------------------------------------------------------- #
class ExtractionMeta(BaseModel):
    method: Literal["llm", "offline"]
    model: Optional[str]
    latency_ms: int
    repaired: bool = False
    warnings: list[str] = []
