"""Deliverable 1 - structured-output extraction module.

    extract_resume(text) -> (ResumeSchema, ExtractionMeta)
    extract_job(text)    -> (JobSchema, ExtractionMeta)

Two interchangeable back-ends produce the *same* fixed schema:

* **LLM** - Claude with structured outputs (``output_format=<Pydantic model>``), so the
  response is constrained to the schema; we re-validate and repair once on failure.
* **Offline** - a deterministic section-aware parser + skill taxonomy, used when no API
  key is configured (and as a fallback if the API call fails).

Both outputs then pass through ``normalise_resume`` / ``normalise_job``, which
canonicalises skill names, de-duplicates, clamps numbers and fills defaults - the
"repair" layer that guarantees downstream code always sees valid data.
"""

from __future__ import annotations

import re
import time
from datetime import date
from typing import Iterable, Optional

from . import config
from .llm import LLMUnavailable, llm_available, structured_call
from .schemas import (
    EducationItem,
    ExperienceItem,
    ExtractionMeta,
    JobSchema,
    ProjectItem,
    ResumeSchema,
    SkillItem,
)
from .skills_taxonomy import (
    ALT_SEP,
    SKILLS,
    canonicalize,
    canonicalize_requirement,
    category_of,
    find_skills,
    is_title_like,
    reduce_requirements,
    requirements_from_text,
)

TODAY = date.today()
OFFLINE_PARSER_VERSION = 4  # bump when the heuristic parser changes -> cache invalidates

# =============================================================================
# Prompts (LLM path)
# =============================================================================
RESUME_SYSTEM = """You are a precise resume parser for a recruiting system.
Convert the resume into the provided JSON schema. Rules:
- Use only information present in the resume; never invent employers, dates or skills.
- Skill names must be canonical and concise: "Kubernetes" (not "k8s"), "PostgreSQL" (not
  "Postgres"), "Apache Spark" (not "PySpark"), "React Native" (not "RN"), "GCP" (not
  "Google Cloud"), "LLMs" for large language models.
- Include skills that are demonstrated in experience/projects even if absent from the skills
  section. Estimate `years` from the roles where the skill was used; null if unclear.
- Dates as YYYY-MM ("present" for ongoing roles). duration_years to one decimal.
- total_years_experience = professional experience only (exclude education/internships
  shorter than 6 months unless that is all there is).
- seniority from titles and years: intern, junior (<2y), mid (2-5y), senior (5-9y),
  lead/principal (9y+ or explicit lead/staff/principal titles).
- Use null for missing contact fields, and empty lists for missing sections."""

JOB_SYSTEM = """You are a precise job-description parser for a recruiting system.
Convert the job description into the provided JSON schema. Rules:
- required_skills = explicit must-haves; preferred_skills = nice-to-haves / bonus.
  A skill appears in only one of the two lists.
- When the JD accepts alternatives ("Tableau, Power BI or Looker", "Python or Go"), write
  them as ONE entry joined by " / " (e.g. "Tableau / Power BI / Looker"); separate
  requirements stay separate entries.
- Canonical, concise skill names ("Kubernetes", "PostgreSQL", "Apache Airflow", "AWS",
  "React Native", "LLMs"). Include soft skills only if explicitly required
  (e.g. "Stakeholder Management", "Communication").
- min_years_experience: the smallest number of years stated (e.g. "5+ years" -> 5); null if absent.
- responsibilities: concise bullet-style statements.
- Never invent requirements that are not in the text."""


# =============================================================================
# Public API
# =============================================================================
def extract_resume(text: str, use_llm: bool = True) -> tuple[ResumeSchema, ExtractionMeta]:
    warnings: list[str] = []
    if use_llm and llm_available():
        try:
            parsed, meta = structured_call(
                system=RESUME_SYSTEM,
                user=f"<resume>\n{text}\n</resume>",
                output_model=ResumeSchema,
                effort=config.EXTRACTION_EFFORT,
            )
            resume, changed = normalise_resume(parsed)
            return resume, ExtractionMeta(
                method="llm", model=meta["model"], latency_ms=meta["latency_ms"],
                repaired=meta["repaired"] or changed, warnings=warnings,
            )
        except LLMUnavailable as exc:
            warnings.append(f"LLM extraction failed, used offline parser: {exc}")
    t0 = time.perf_counter()
    resume, changed = normalise_resume(offline_extract_resume(text))
    return resume, ExtractionMeta(
        method="offline", model=None, latency_ms=int((time.perf_counter() - t0) * 1000),
        repaired=changed, warnings=warnings,
    )


def extract_job(text: str, use_llm: bool = True) -> tuple[JobSchema, ExtractionMeta]:
    warnings: list[str] = []
    if use_llm and llm_available():
        try:
            parsed, meta = structured_call(
                system=JOB_SYSTEM,
                user=f"<job_description>\n{text}\n</job_description>",
                output_model=JobSchema,
                effort=config.EXTRACTION_EFFORT,
            )
            job, changed = normalise_job(parsed)
            return job, ExtractionMeta(
                method="llm", model=meta["model"], latency_ms=meta["latency_ms"],
                repaired=meta["repaired"] or changed, warnings=warnings,
            )
        except LLMUnavailable as exc:
            warnings.append(f"LLM extraction failed, used offline parser: {exc}")
    t0 = time.perf_counter()
    job, changed = normalise_job(offline_extract_job(text))
    return job, ExtractionMeta(
        method="offline", model=None, latency_ms=int((time.perf_counter() - t0) * 1000),
        repaired=changed, warnings=warnings,
    )


# =============================================================================
# Normalisation / repair layer (applied to BOTH back-ends)
# =============================================================================
def _dedupe(items: Iterable[str]) -> list[str]:
    seen, out = set(), []
    for it in items:
        key = it.lower()
        if it and key not in seen:
            seen.add(key)
            out.append(it)
    return out


def _canon_list(items: Iterable[str]) -> list[str]:
    return _dedupe(canonicalize(s) for s in items if s and s.strip())


def normalise_resume(r: ResumeSchema) -> tuple[ResumeSchema, bool]:
    before = r.model_dump_json()
    merged: dict[str, SkillItem] = {}
    for s in r.skills:
        name = canonicalize(s.name)
        if not name:
            continue
        cat = category_of(name) if name in SKILLS else s.category
        years = None if s.years is None else round(max(0.0, min(float(s.years), 50.0)), 1)
        prev = merged.get(name.lower())
        if prev is None or (years or 0) > (prev.years or 0):
            merged[name.lower()] = SkillItem(name=name, category=cat, years=years,
                                             proficiency=s.proficiency)
    r.skills = list(merged.values())
    for e in r.experience:
        e.technologies = _canon_list(e.technologies)
        e.highlights = [h.strip() for h in e.highlights if h.strip()]
        if e.duration_years is not None:
            e.duration_years = round(max(0.0, min(e.duration_years, 50.0)), 1)
    for p in r.projects:
        p.technologies = _canon_list(p.technologies)
    r.certifications = _dedupe(c.strip() for c in r.certifications)
    r.total_years_experience = round(max(0.0, min(float(r.total_years_experience or 0), 50.0)), 1)
    r.headline = r.headline.strip() or (r.experience[0].title if r.experience else "Candidate")
    return r, r.model_dump_json() != before


def normalise_job(j: JobSchema) -> tuple[JobSchema, bool]:
    before = j.model_dump_json()
    j.required_skills = _dedupe(canonicalize_requirement(s) for s in j.required_skills if s.strip())
    req = {s.lower() for s in j.required_skills}
    j.preferred_skills = [s for s in _dedupe(canonicalize_requirement(s) for s in j.preferred_skills if s.strip())
                          if s.lower() not in req]
    j.responsibilities = [x.strip() for x in j.responsibilities if x.strip()]
    if j.min_years_experience is not None:
        j.min_years_experience = max(0.0, min(float(j.min_years_experience), 30.0))
    return j, j.model_dump_json() != before


# =============================================================================
# Offline heuristic extractor
# =============================================================================
SECTION_ALIASES = {
    "summary": ["summary", "profile", "about", "about me", "professional summary", "objective",
                "career objective", "overview", "career summary"],
    "skills": ["skills", "technical skills", "core competencies", "competencies", "tech stack",
               "technologies", "tools", "key skills", "skills & tools", "skills and tools",
               "toolbox", "expertise"],
    "experience": ["experience", "work experience", "professional experience", "employment",
                   "employment history", "work history", "career history", "relevant experience"],
    "education": ["education", "academic background", "qualifications", "academics"],
    "certifications": ["certifications", "certificates", "licenses", "licenses & certifications",
                       "certifications & training", "training", "courses"],
    "projects": ["projects", "selected projects", "personal projects", "side projects",
                 "key projects", "open source", "portfolio"],
    # job description sections
    "about_role": ["about the role", "role overview", "the role", "about the job", "overview",
                   "about us", "who we are", "about the team", "job summary", "position summary"],
    "responsibilities": ["responsibilities", "what you'll do", "what you will do", "key responsibilities",
                         "your responsibilities", "the work", "day to day", "in this role you will"],
    "requirements": ["requirements", "must have", "must-have", "must haves", "what we're looking for",
                     "what we are looking for", "qualifications", "required qualifications",
                     "minimum qualifications", "you have", "who you are", "required skills"],
    "preferred": ["nice to have", "nice-to-have", "preferred qualifications", "preferred",
                  "bonus points", "bonus", "good to have", "pluses", "extra credit", "desirable"],
    "benefits": ["benefits", "perks", "what we offer", "compensation", "why join us"],
}

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_MONTH_RE = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_DATE_TOKEN = rf"(?:{_MONTH_RE}\.?\s+\d{{4}}|\d{{1,2}}/\d{{4}}|\d{{4}}-\d{{2}}|\d{{4}})"
_PRESENT = r"(?:present|current|now|today|date|ongoing)"
DATE_RANGE_RE = re.compile(
    rf"(?P<start>{_DATE_TOKEN})\s*(?:–|—|-|to|until|till)\s*(?P<end>{_DATE_TOKEN}|{_PRESENT})",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
BULLET_RE = re.compile(r"^\s*(?:[-•*▪●◦·]|\d+[.)])\s+")
DEGREE_RE = re.compile(
    r"\b(ph\.?d|doctorate|m\.?\s?tech|m\.?\s?sc|m\.?\s?s\b|m\.?\s?eng|m\.?\s?e\b|mba|m\.?\s?a\b|master'?s?|"
    r"b\.?\s?tech|b\.?\s?sc|b\.?\s?s\b|b\.?\s?eng|b\.?\s?e\b|b\.?\s?a\b|bca|mca|bachelor'?s?|diploma|associate'?s?|"
    r"high school|bootcamp|certificate|ingenier[ií]a|licenciatura|licence|laurea|diplom|"
    r"engineer'?s degree|b\.?\s?com|m\.?\s?com)", re.IGNORECASE)
INSTITUTION_RE = re.compile(
    r"(universit|universidad|université|universität|hochschule|politecnico|école|ecole|institute|"
    r"instituto|college|school|academy|iit|nit|bits|polytechnic|bootcamp|"
    r"general assembly|coursera|udacity)", re.IGNORECASE)


def _parse_date(tok: str) -> Optional[tuple[int, int]]:
    tok = tok.strip().lower().rstrip(".")
    if re.fullmatch(_PRESENT, tok):
        return (TODAY.year, TODAY.month)
    m = re.match(rf"({_MONTH_RE})\.?\s+(\d{{4}})", tok)
    if m:
        return (int(m.group(2)), MONTHS[m.group(1)[:3]])
    m = re.fullmatch(r"(\d{1,2})/(\d{4})", tok)
    if m:
        return (int(m.group(2)), max(1, min(12, int(m.group(1)))))
    m = re.fullmatch(r"(\d{4})-(\d{2})", tok)
    if m:
        return (int(m.group(1)), max(1, min(12, int(m.group(2)))))
    m = re.fullmatch(r"\d{4}", tok)
    if m:
        return (int(tok), 1)
    return None


def _fmt(ym: Optional[tuple[int, int]]) -> Optional[str]:
    return f"{ym[0]:04d}-{ym[1]:02d}" if ym else None


def _months_between(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(0, (b[0] - a[0]) * 12 + (b[1] - a[1]))


def _normalise_header(line: str) -> str:
    return re.sub(r"[^a-z&' -]", "", line.lower()).strip(" -:")


def split_sections(text: str, keys: Iterable[str]) -> tuple[list[str], dict[str, list[str]]]:
    """Split text into (preamble lines, {section_key: lines})."""
    alias_to_key = {a: k for k in keys for a in SECTION_ALIASES[k]}
    preamble: list[str] = []
    sections: dict[str, list[str]] = {}
    current: Optional[str] = None
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        candidate = _normalise_header(stripped.rstrip(":"))
        is_header = (
            stripped
            and len(stripped) <= 48
            and not BULLET_RE.match(stripped)
            and candidate in alias_to_key
        )
        # also accept "Skills: Python, SQL" style inline headers
        inline = None
        if not is_header and ":" in stripped and not BULLET_RE.match(stripped):
            head, _, rest = stripped.partition(":")
            if _normalise_header(head) in alias_to_key and rest.strip() and len(head) <= 30:
                inline = (alias_to_key[_normalise_header(head)], rest.strip())
        if is_header:
            current = alias_to_key[candidate]
            sections.setdefault(current, [])
        elif inline:
            current = inline[0]
            sections.setdefault(current, []).append(inline[1])
        elif current is None:
            preamble.append(line)
        else:
            sections[current].append(line)
    return preamble, sections


def _clean(line: str) -> str:
    return BULLET_RE.sub("", line).strip()


def _split_title_company(line: str) -> tuple[str, str]:
    line = DATE_RANGE_RE.sub("", line)
    line = re.sub(r"[(\[]\s*[)\]]", "", line).strip(" |,–—-()")
    if re.search(r"\s+at\s+", line, re.IGNORECASE):
        a, b = re.split(r"\s+at\s+", line, maxsplit=1, flags=re.IGNORECASE)
        return a.strip(" |,–—-"), b.strip(" |,–—-")
    # strong separators first ("Title — Company", "Title | Company"); commas only as a fallback
    parts = [p.strip() for p in re.split(r"\s+[|–—]\s+|\s+-\s+|\s+@\s+", line) if p.strip()]
    if len(parts) == 1:
        parts = [p.strip() for p in re.split(r",\s+", line) if p.strip()]
        if len(parts) > 2:  # "Title, Department, Company" -> company is the last part
            parts = [", ".join(parts[:-1]), parts[-1]] if is_title_like(parts[0]) else parts
    if not parts:
        return "", ""
    if len(parts) == 1:
        return (parts[0], "") if is_title_like(parts[0]) else ("", parts[0])
    if is_title_like(parts[0]) or not is_title_like(parts[1]):
        return parts[0], ", ".join(parts[1:])
    return parts[1], parts[0]


def _parse_experience(lines: list[str]) -> list[dict]:
    """Group experience lines into entries keyed on date-range lines."""
    entries: list[dict] = []
    header_buf: list[str] = []
    nonempty = [l.strip() for l in lines if l.strip()]
    for idx, s in enumerate(nonempty):
        is_bullet = bool(BULLET_RE.match(s))
        nxt = nonempty[idx + 1] if idx + 1 < len(nonempty) else ""
        next_is_date = bool(nxt) and not BULLET_RE.match(nxt) and bool(DATE_RANGE_RE.search(nxt)) \
            and len(DATE_RANGE_RE.sub("", nxt).strip(" |,–—-()")) < 4
        if not is_bullet and not DATE_RANGE_RE.search(s) and next_is_date:
            header_buf.append(s)  # a line directly above a date-only line is always a header
            continue
        m = DATE_RANGE_RE.search(s) if not is_bullet else None
        if m:
            rest = DATE_RANGE_RE.sub("", s).strip(" |,–—-()")
            header_text = " | ".join(header_buf + ([rest] if rest else []))
            header_buf = []
            title, company = _split_title_company(header_text)
            start, end = _parse_date(m.group("start")), _parse_date(m.group("end"))
            ongoing = bool(re.fullmatch(_PRESENT, m.group("end").strip().lower()))
            entries.append({
                "title": title or "Role", "company": company or "Unknown", "start": start,
                "end": end, "ongoing": ongoing, "bullets": [],
            })
        elif is_bullet or (entries and not header_buf and len(s) > 70):
            if entries:
                entries[-1]["bullets"].append(_clean(s))
        else:
            # A non-bullet, non-date line: header for the next entry (or a stray bullet).
            if entries and not is_title_like(s) and len(s) > 60:
                entries[-1]["bullets"].append(s)
            else:
                header_buf.append(s)
    return entries


def _merge_months(intervals: list[tuple[tuple[int, int], tuple[int, int]]]) -> int:
    idx = sorted((a[0] * 12 + a[1], b[0] * 12 + b[1]) for a, b in intervals if a and b)
    total, cur_s, cur_e = 0, None, None
    for s, e in idx:
        if cur_s is None:
            cur_s, cur_e = s, e
        elif s <= cur_e:
            cur_e = max(cur_e, e)
        else:
            total += cur_e - cur_s
            cur_s, cur_e = s, e
    if cur_s is not None:
        total += cur_e - cur_s
    return total


def _seniority(title: str, years: float) -> str:
    t = title.lower()
    if "intern" in t or "trainee" in t:
        return "intern"
    if re.search(r"\b(principal|distinguished)\b", t):
        return "principal"
    if re.search(r"\b(lead|staff|head|director|manager|architect)\b", t):
        return "lead"
    if re.search(r"\b(senior|sr\.?)\b", t):
        return "senior"
    if re.search(r"\b(junior|jr\.?|associate|graduate|entry)\b", t):
        return "junior"
    if years < 2:
        return "junior"
    if years < 5:
        return "mid"
    if years < 9:
        return "senior"
    return "lead"


def _skills_from_list(lines: list[str]) -> list[str]:
    """Skills section: taxonomy hits + comma-separated items that look like skills."""
    joined = " \n ".join(_clean(l) for l in lines)
    names = [c for c, _ in find_skills(joined, allow_weak=True)]
    for part in re.split(r"[,;|•·\n]|\s/\s", joined):
        part = re.sub(r"^[A-Za-z &/]{2,30}:\s*", "", part.strip())  # "Languages: Python"
        part = part.strip(" .()")
        if 1 < len(part) <= 28 and len(part.split()) <= 3 and not re.search(r"\d{3,}", part):
            canon = canonicalize(part)
            if canon in SKILLS and canon not in names:
                names.append(canon)
    return names


def offline_extract_resume(text: str) -> ResumeSchema:
    keys = ["summary", "skills", "experience", "education", "certifications", "projects"]
    preamble, sec = split_sections(text, keys)
    pre = [l.strip() for l in preamble if l.strip()]

    name = pre[0] if pre else "Unknown Candidate"
    if EMAIL_RE.search(name) or len(name.split()) > 5:
        name = "Unknown Candidate"
    contact_blob = " | ".join(pre[1:4])
    email = (EMAIL_RE.search(contact_blob) or EMAIL_RE.search(text))
    phone = PHONE_RE.search(contact_blob)
    location = None
    contact_parts = [p.strip() for p in re.split(r"\s*[|•·]\s*", contact_blob) if p.strip()]
    for p in contact_parts:
        if not EMAIL_RE.search(p) and not PHONE_RE.search(p) and "linkedin" not in p.lower() \
                and "github" not in p.lower() and "http" not in p.lower() and not is_title_like(p) \
                and len(p) < 48 and ("," in p or (any(EMAIL_RE.search(q) or PHONE_RE.search(q) for q in contact_parts)
                                                  and re.fullmatch(r"[^\d@]{2,40}", p) and len(p.split()) <= 4)):
            location = p
            break
    headline = ""
    for l in pre[1:4]:
        if not EMAIL_RE.search(l) and not PHONE_RE.search(l) and l != location:
            headline = l.split("|")[0].strip()
            break

    # --- experience
    exp_entries = _parse_experience(sec.get("experience", []))
    experience: list[ExperienceItem] = []
    intervals = []
    for e in exp_entries:
        months = _months_between(e["start"], e["end"]) if e["start"] and e["end"] else None
        if e["start"] and e["end"]:
            intervals.append((e["start"], e["end"]))
        body = " ".join(e["bullets"]) + " " + e["title"]
        experience.append(ExperienceItem(
            title=e["title"], company=e["company"], start=_fmt(e["start"]),
            end="present" if e["ongoing"] else _fmt(e["end"]),
            duration_years=round(months / 12, 1) if months is not None else None,
            highlights=e["bullets"],
            technologies=[c for c, _ in find_skills(body, allow_weak=False)],
        ))
    total_years = round(_merge_months(intervals) / 12, 1)
    stated = re.search(r"(\d+(?:\.\d+)?)\+?\s*(?:years|yrs)(?:\s+of)?\s+(?:professional\s+|industry\s+|hands-on\s+)?experience",
                       " ".join(sec.get("summary", []) + pre), re.IGNORECASE)
    if stated and (total_years == 0 or abs(float(stated.group(1)) - total_years) > 3):
        total_years = float(stated.group(1)) if total_years == 0 else total_years

    # --- skills with years estimated from experience entries
    listed = _skills_from_list(sec.get("skills", []))
    narrative = "\n".join(sec.get("experience", []) + sec.get("projects", []) + sec.get("summary", []))
    demonstrated = [c for c, _ in find_skills(narrative, allow_weak=False)]
    skills: list[SkillItem] = []
    for sk in _dedupe(listed + demonstrated):
        yrs = sum(x.duration_years or 0 for x in experience if sk in x.technologies)
        yrs = round(min(yrs, total_years or yrs), 1) if yrs else None
        if yrs is None:
            prof = "unknown" if sk not in demonstrated else "beginner"
        else:
            prof = "beginner" if yrs < 1 else "intermediate" if yrs < 3 else "advanced" if yrs < 6 else "expert"
        skills.append(SkillItem(name=sk, category=category_of(sk), years=yrs, proficiency=prof))

    # --- education
    education: list[EducationItem] = []
    edu_lines = [l.strip() for l in sec.get("education", []) if l.strip()]
    i = 0
    while i < len(edu_lines):
        line = _clean(edu_lines[i])
        nxt = _clean(edu_lines[i + 1]) if i + 1 < len(edu_lines) else ""
        if DEGREE_RE.search(line) or INSTITUTION_RE.search(line):
            combo = line
            if nxt and not DEGREE_RE.search(nxt) and (INSTITUTION_RE.search(nxt) or re.search(r"\b(19|20)\d{2}\b", nxt)):
                combo = f"{line} | {nxt}"
                i += 1
            years = re.findall(r"\b(?:19|20)\d{2}\b", combo)
            parts = [p.strip() for p in re.split(r"\s*[|,–—]\s*|\s+-\s+", DATE_RANGE_RE.sub("", combo)) if p.strip()]
            inst = next((p for p in parts if INSTITUTION_RE.search(p)), parts[-1] if len(parts) > 1 else "")
            deg = next((p for p in parts if DEGREE_RE.search(p) and p != inst), parts[0] if parts else line)
            fld = None
            m = re.search(r"\b(?:in|of)\s+([A-Z][A-Za-z &]+)", deg)
            if m:
                fld = m.group(1).strip()
            education.append(EducationItem(degree=re.sub(r"\b(19|20)\d{2}\b", "", deg).strip(" ()-"),
                                           field=fld, institution=re.sub(r"\b(19|20)\d{2}\b", "", inst).strip(" ()-") or "Unknown",
                                           year=int(years[-1]) if years else None))
        i += 1

    certifications = [_clean(l) for l in sec.get("certifications", []) if _clean(l)]

    projects: list[ProjectItem] = []
    for l in sec.get("projects", []):
        c = _clean(l)
        if not c:
            continue
        m = re.match(r"^(.{3,60}?)\s*(?:[:–—]|\s-\s)\s*(.+)$", c)
        pname, desc = (m.group(1), m.group(2)) if m else (c[:50], c)
        projects.append(ProjectItem(name=pname.strip(), description=desc.strip(),
                                    technologies=[s for s, _ in find_skills(c, allow_weak=False)]))

    summary_lines = [l.strip() for l in sec.get("summary", []) if l.strip()]
    summary = " ".join(summary_lines)
    if not summary:
        first_bullets = [h for e in experience for h in e.highlights][:2]
        summary = (f"{headline}. " if headline else "") + " ".join(first_bullets)
    if not headline:
        headline = experience[0].title if experience else "Candidate"

    current_title = experience[0].title if experience else headline
    seniority = _seniority(f"{headline} {current_title}", total_years)

    return ResumeSchema(
        name=name, email=email.group(0) if email else None, phone=phone.group(0).strip() if phone else None,
        location=location, headline=headline, summary=summary.strip()[:900],
        total_years_experience=total_years, seniority=seniority, skills=skills,
        experience=experience, education=education, certifications=certifications, projects=projects,
    )


def offline_extract_job(text: str) -> JobSchema:
    keys = ["about_role", "responsibilities", "requirements", "preferred", "education", "benefits"]
    preamble, sec = split_sections(text, keys)
    pre = [l.strip() for l in preamble if l.strip()]
    title = pre[0] if pre else "Untitled role"

    def field(label: str) -> Optional[str]:
        m = re.search(rf"^\s*(?:{label})\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        return m.group(1).strip() if m else None

    company = field("company")
    location = field("location")
    employment_type = field(r"employment type|job type|type")

    req_text = "\n".join(_clean(l) for l in sec.get("requirements", []))
    pref_text = "\n".join(_clean(l) for l in sec.get("preferred", []))
    resp_lines = [_clean(l) for l in sec.get("responsibilities", []) if _clean(l)]

    required = requirements_from_text(req_text, allow_weak=True)
    if not required:  # no explicit requirements section -> take everything
        required = requirements_from_text(text, allow_weak=False)
    covered = {p for r in required for p in r.split(ALT_SEP)}
    preferred = reduce_requirements(requirements_from_text(pref_text, allow_weak=True), exclude=covered)
    covered |= {p for r in preferred for p in r.split(ALT_SEP)}
    # skills that only appear in responsibilities count as preferred context
    for c, _ in find_skills("\n".join(resp_lines), allow_weak=False):
        if c not in covered:
            preferred.append(c)
            covered.add(c)

    # The first "N+ years" in the requirements is the overall bar
    # ("5+ years ..., with at least 2 years in NLP" -> 5).
    yr_re = re.compile(r"(\d+)\s*\+?\s*(?:-\s*\d+\s*)?(?:years|yrs)", re.IGNORECASE)
    m_years = yr_re.search(req_text) or yr_re.search(text)
    min_years = float(m_years.group(1)) if m_years else None

    about = " ".join(l.strip() for l in sec.get("about_role", []) if l.strip())
    summary = about or " ".join(resp_lines[:2]) or title
    edu_lines = [_clean(l) for l in sec.get("education", []) if _clean(l)]
    edu = edu_lines[0] if edu_lines else None
    if not edu:
        m = re.search(r"[^.\n]*\b(bachelor'?s?|master'?s?|degree|b\.?s\.?|m\.?s\.?|phd)\b[^.\n]*", req_text, re.IGNORECASE)
        edu = _clean(m.group(0)) if m else None

    seniority = _seniority(title, min_years if min_years is not None else 3)
    domain = None
    for d, kws in {
        "fintech": ["fintech", "payments", "banking", "lending"],
        "healthcare": ["healthcare", "health tech", "clinical", "patients"],
        "e-commerce": ["e-commerce", "ecommerce", "retail", "marketplace"],
        "logistics": ["logistics", "supply chain", "delivery"],
        "edtech": ["edtech", "education platform", "learners"],
        "media": ["media", "streaming platform", "content"],
        "saas": ["saas", "b2b"],
    }.items():
        if any(k in text.lower() for k in kws):
            domain = d
            break

    return JobSchema(
        title=title, company=company, location=location, employment_type=employment_type,
        seniority=seniority, min_years_experience=min_years, summary=summary[:900],
        required_skills=required, preferred_skills=preferred, responsibilities=resp_lines,
        education_requirement=edu, domain=domain,
    )
