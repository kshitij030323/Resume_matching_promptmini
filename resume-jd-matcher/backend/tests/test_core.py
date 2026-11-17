"""Unit tests for the metric, taxonomy and extraction layers (no network, no models)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.evaluation import dcg, ndcg_at_k, precision_at_k, sign_flip_test  # noqa: E402
from app.extraction import normalise_job, offline_extract_job, offline_extract_resume  # noqa: E402
from app.schemas import JobSchema, ResumeSchema  # noqa: E402
from app.skills_taxonomy import canonicalize, find_skills, related_skills  # noqa: E402


# ---------------------------------------------------------------- NDCG
def test_dcg_known_value():
    # rels 3,2,0 -> 7/1 + 3/log2(3) + 0
    assert math.isclose(dcg([3, 2, 0]), 7 + 3 / math.log2(3))


def test_ndcg_perfect_and_worst():
    g = {"a": 3, "b": 2, "c": 1, "d": 0, "e": 0, "f": 0}
    assert ndcg_at_k(["a", "b", "c", "d", "e"], g, 5) == 1.0
    assert ndcg_at_k(["d", "e", "f", "x", "y"], g, 5) == 0.0


def test_ndcg_uses_graded_ideal():
    g = {"a": 3, "b": 1}
    # swapping the two relevant docs must lower the score but keep it > 0
    swapped = ndcg_at_k(["b", "a"], g, 5)
    assert 0 < swapped < 1


def test_ndcg_unlabelled_counts_zero():
    assert ndcg_at_k(["zzz", "a"], {"a": 3}, 5) < 1.0


def test_precision():
    assert precision_at_k(["a", "b", "c", "d", "e"], {"a": 3, "b": 2, "c": 1}, 5) == 0.4


def test_sign_flip():
    assert sign_flip_test([0.1, 0.2, 0.3, 0.1, 0.2, 0.3]) == 2 / 64
    assert sign_flip_test([0, 0, 0]) == 1.0


# ---------------------------------------------------------------- taxonomy
def test_canonicalize_aliases():
    assert canonicalize("k8s") == "Kubernetes"
    assert canonicalize("Postgres") == "PostgreSQL"
    assert canonicalize("pyspark") == "Apache Spark"
    assert canonicalize("Google Cloud") == "GCP"
    assert canonicalize("some niche tool") == "Some Niche Tool"


def test_find_skills_longest_match_and_boundaries():
    found = {s for s, _ in find_skills("Built apps in React Native with PostgreSQL and JavaScript")}
    assert {"React Native", "PostgreSQL", "JavaScript"} <= found
    assert "React" not in found and "SQL" not in found and "Java" not in found


def test_go_not_matched_in_prose():
    found = {s for s, _ in find_skills("We go to market fast. Services written in Go, Python.")}
    assert "Go" in found
    found2 = {s for s, _ in find_skills("Ready to go live next week")}
    assert "Go" not in found2


def test_related():
    assert "TensorFlow" in related_skills("PyTorch", {"TensorFlow", "SQL"})


# ---------------------------------------------------------------- extraction
RESUME = """Jordan Lee
jordan.lee@example.com | +1-555-0100 | Austin, TX
Data Engineer

Summary
Data engineer with 4 years building batch and streaming pipelines.

Skills
Python, SQL, Spark, Airflow, Kafka, Snowflake, dbt

Experience
Data Engineer | Streamly
Feb 2022 – Present
- Built Kafka -> Spark streaming jobs processing 2B events/day
- Migrated 120 Airflow DAGs to dbt + Snowflake
Analyst, Corner Shop Co
2020 - 2022
- Built Tableau dashboards for 40 stores

Education
B.S. in Computer Science, University of Texas, 2020
"""

JOB = """Senior Data Engineer
Company: Example Corp
Location: Remote

About the role
Own our data platform.

Must have
- 5+ years of data engineering experience
- Python and SQL
- Apache Spark and Airflow

Nice to have
- Kafka
- Terraform
"""


def test_offline_resume_schema_valid():
    r = offline_extract_resume(RESUME)
    assert isinstance(r, ResumeSchema)
    ResumeSchema.model_validate(r.model_dump())
    assert r.name == "Jordan Lee" and r.email == "jordan.lee@example.com"
    names = {s.name for s in r.skills}
    assert {"Python", "SQL", "Apache Spark", "Apache Airflow", "Apache Kafka", "Snowflake", "dbt"} <= names
    assert len(r.experience) == 2
    assert r.experience[0].company == "Streamly" and r.experience[0].end == "present"
    assert r.total_years_experience >= 4


def test_offline_job_schema_valid():
    j, _ = normalise_job(offline_extract_job(JOB))
    assert isinstance(j, JobSchema)
    assert j.title == "Senior Data Engineer"
    assert {"Python", "SQL", "Apache Spark", "Apache Airflow"} <= set(j.required_skills)
    assert "Apache Kafka" in j.preferred_skills and "Terraform" in j.preferred_skills
    assert j.min_years_experience == 5
    assert j.seniority == "senior"
