"""Skill taxonomy: canonical names, aliases, categories and related-skill groups.

Used for
  * normalising skill names coming out of either extractor (``k8s`` -> ``Kubernetes``),
  * the offline heuristic extractor (finding skills in free text),
  * skill-coverage features in the hybrid ranker,
  * "transferable skill" detection in the skill-gap chain.
"""

from __future__ import annotations

import re
from functools import lru_cache

# canonical name -> (category, [aliases]).  Aliases are matched case-insensitively
# with alphanumeric word boundaries, except those listed in CASE_SENSITIVE.
SKILLS: dict[str, tuple[str, list[str]]] = {
    # ---- programming languages ------------------------------------------------
    "Python": ("programming_language", ["python", "python3"]),
    "Java": ("programming_language", ["java"]),
    "JavaScript": ("programming_language", ["javascript", "js", "es6", "ecmascript"]),
    "TypeScript": ("programming_language", ["typescript", "ts"]),
    "Go": ("programming_language", ["golang", "Go"]),
    "Rust": ("programming_language", ["rust"]),
    "C++": ("programming_language", ["c++", "cpp"]),
    "C#": ("programming_language", ["c#", "csharp"]),
    "Scala": ("programming_language", ["scala"]),
    "Kotlin": ("programming_language", ["kotlin"]),
    "Swift": ("programming_language", ["swift", "swiftui"]),
    "Objective-C": ("programming_language", ["objective-c", "objc"]),
    "R": ("programming_language", ["R", "rstudio"]),
    "SQL": ("programming_language", ["sql", "t-sql", "pl/sql", "ansi sql"]),
    "Bash": ("programming_language", ["bash", "shell scripting", "shell", "zsh"]),
    "Ruby": ("programming_language", ["ruby"]),
    "PHP": ("programming_language", ["php"]),
    "Dart": ("programming_language", ["dart"]),
    "HTML": ("mobile_frontend", ["html", "html5"]),
    "CSS": ("mobile_frontend", ["css", "css3", "scss", "sass", "tailwind", "tailwindcss"]),
    # ---- ML / AI ---------------------------------------------------------------
    "Machine Learning": ("ml_ai", ["machine learning", "ml"]),
    "Deep Learning": ("ml_ai", ["deep learning", "neural networks", "neural network"]),
    "NLP": ("ml_ai", ["nlp", "natural language processing", "text mining", "text classification"]),
    "Computer Vision": ("ml_ai", ["computer vision", "image classification", "object detection", "opencv"]),
    "LLMs": ("ml_ai", ["llm", "llms", "large language models", "large language model", "generative ai", "genai", "gpt", "prompt engineering"]),
    "RAG": ("ml_ai", ["rag", "retrieval-augmented generation", "retrieval augmented generation"]),
    "Transformers": ("ml_ai", ["transformers", "transformer models", "transformer", "hugging face", "huggingface", "bert", "roberta"]),
    "PyTorch": ("ml_ai", ["pytorch", "torch"]),
    "TensorFlow": ("ml_ai", ["tensorflow", "tf2"]),
    "Keras": ("ml_ai", ["keras"]),
    "JAX": ("ml_ai", ["jax"]),
    "scikit-learn": ("ml_ai", ["scikit-learn", "sklearn", "scikit learn"]),
    "XGBoost": ("ml_ai", ["xgboost", "lightgbm", "catboost", "gradient boosting"]),
    "spaCy": ("ml_ai", ["spacy"]),
    "NLTK": ("ml_ai", ["nltk"]),
    "LangChain": ("ml_ai", ["langchain", "llamaindex", "llama index"]),
    "Vector Databases": ("ml_ai", ["vector database", "vector databases", "vector db", "pinecone", "faiss", "chromadb", "chroma", "weaviate", "milvus", "pgvector", "qdrant"]),
    "MLOps": ("ml_ai", ["mlops", "ml ops", "model deployment", "model serving"]),
    "MLflow": ("ml_ai", ["mlflow"]),
    "Kubeflow": ("ml_ai", ["kubeflow"]),
    "SageMaker": ("ml_ai", ["sagemaker", "aws sagemaker"]),
    "Vertex AI": ("ml_ai", ["vertex ai"]),
    "Statistics": ("data", ["statistics", "statistical analysis", "statistical modeling", "statistical modelling", "hypothesis testing", "regression analysis", "significance testing", "statistical significance", "power analysis", "confidence intervals", "sample-size planning", "sample size planning", "bayesian", "regression models"]),
    "A/B Testing": ("data", ["a/b testing", "a/b tests", "ab testing", "experimentation", "experiment design"]),
    "Feature Engineering": ("ml_ai", ["feature engineering", "feature store"]),
    "Recommender Systems": ("ml_ai", ["recommender systems", "recommendation systems", "recommendation engine"]),
    "Time Series": ("ml_ai", ["time series", "forecasting"]),
    # ---- data ------------------------------------------------------------------
    "Pandas": ("data", ["pandas"]),
    "NumPy": ("data", ["numpy"]),
    "Apache Spark": ("data", ["spark", "apache spark", "pyspark", "spark sql", "spark streaming"]),
    "Hadoop": ("data", ["hadoop", "hdfs", "hive", "mapreduce"]),
    "Apache Airflow": ("data", ["airflow", "apache airflow"]),
    "Dagster": ("data", ["dagster", "prefect", "luigi"]),
    "Apache Kafka": ("data", ["kafka", "apache kafka", "kafka streams"]),
    "Apache Flink": ("data", ["flink", "apache flink"]),
    "Kinesis": ("data", ["kinesis", "aws kinesis"]),
    "dbt": ("data", ["dbt", "data build tool"]),
    "ETL": ("data", ["etl", "elt", "data pipelines", "data pipeline", "etl pipelines", "etl pipeline"]),
    "Data Warehousing": ("data", ["data warehousing", "data warehouse", "dimensional modeling", "dimensional modelling", "star schema", "data modeling", "data modelling", "kimball"]),
    "Data Lake": ("data", ["data lake", "lakehouse", "delta lake", "apache iceberg", "iceberg"]),
    "Snowflake": ("data", ["snowflake"]),
    "BigQuery": ("data", ["bigquery", "big query"]),
    "Redshift": ("data", ["redshift", "aws redshift"]),
    "Databricks": ("data", ["databricks"]),
    "Tableau": ("data", ["tableau"]),
    "Power BI": ("data", ["power bi", "powerbi", "dax"]),
    "Looker": ("data", ["looker", "lookml", "looker studio", "google data studio"]),
    "Metabase": ("data", ["metabase", "superset", "apache superset"]),
    "Excel": ("tool", ["excel", "microsoft excel", "advanced excel", "pivot tables", "vlookup", "google sheets", "spreadsheets"]),
    "Data Visualization": ("data", ["data visualization", "data visualisation", "dashboards", "dashboarding", "dashboard", "matplotlib", "seaborn", "plotly"]),
    "Data Analysis": ("data", ["data analysis", "data analytics", "exploratory data analysis", "eda", "analytics"]),
    "Streaming": ("data", ["stream processing", "real-time streaming", "streaming pipelines", "event streaming", "pub/sub"]),
    # ---- databases ---------------------------------------------------------------
    "PostgreSQL": ("database", ["postgresql", "postgres", "psql"]),
    "MySQL": ("database", ["mysql", "mariadb"]),
    "SQL Server": ("database", ["sql server", "mssql", "microsoft sql server"]),
    "Oracle": ("database", ["oracle", "oracle db"]),
    "MongoDB": ("database", ["mongodb", "mongo"]),
    "Redis": ("database", ["redis"]),
    "Cassandra": ("database", ["cassandra"]),
    "DynamoDB": ("database", ["dynamodb"]),
    "Elasticsearch": ("database", ["elasticsearch", "opensearch", "elk", "elastic stack"]),
    "SQLite": ("database", ["sqlite"]),
    "Firebase": ("database", ["firebase", "firestore"]),
    # ---- cloud / devops ------------------------------------------------------------
    "AWS": ("cloud_devops", ["aws", "amazon web services", "ec2", "s3", "lambda", "aws lambda", "ecs", "eks", "cloudwatch", "iam"]),
    "GCP": ("cloud_devops", ["gcp", "google cloud", "google cloud platform", "gke", "cloud run"]),
    "Azure": ("cloud_devops", ["azure", "microsoft azure", "aks"]),
    "Docker": ("cloud_devops", ["docker", "containers", "containerization", "containerisation", "docker compose"]),
    "Kubernetes": ("cloud_devops", ["kubernetes", "k8s", "openshift"]),
    "Helm": ("cloud_devops", ["helm", "helm charts"]),
    "Terraform": ("cloud_devops", ["terraform", "infrastructure as code", "infra-as-code", "iac", "pulumi", "cloudformation"]),
    "Ansible": ("cloud_devops", ["ansible", "chef", "puppet"]),
    "CI/CD": ("cloud_devops", ["ci/cd", "cicd", "continuous integration", "continuous delivery", "continuous deployment", "jenkins", "github actions", "gitlab ci", "circleci", "argo cd", "argocd", "bitrise", "fastlane"]),
    "Linux": ("cloud_devops", ["linux", "unix", "ubuntu", "centos", "rhel"]),
    "Prometheus": ("cloud_devops", ["prometheus"]),
    "Grafana": ("cloud_devops", ["grafana"]),
    "Observability": ("cloud_devops", ["observability", "monitoring", "alerting", "datadog", "new relic", "opentelemetry", "splunk", "sentry", "logging"]),
    "SRE": ("cloud_devops", ["sre", "site reliability", "site reliability engineering", "slos", "slo", "sli", "error budgets", "incident response", "on-call", "postmortems"]),
    "Networking": ("cloud_devops", ["networking", "tcp/ip", "dns", "load balancing", "nginx", "vpc"]),
    "Microservices": ("framework_library", ["microservices", "microservice", "service-oriented architecture", "soa", "distributed systems"]),
    "Serverless": ("cloud_devops", ["serverless"]),
    # ---- backend frameworks & APIs ------------------------------------------------
    "REST APIs": ("framework_library", ["rest", "restful", "rest api", "rest apis", "restful apis", "restful services", "openapi"]),
    "gRPC": ("framework_library", ["grpc", "protobuf", "protocol buffers"]),
    "GraphQL": ("framework_library", ["graphql", "apollo"]),
    "Django": ("framework_library", ["django", "django rest framework", "drf"]),
    "Flask": ("framework_library", ["flask"]),
    "FastAPI": ("framework_library", ["fastapi"]),
    "Spring Boot": ("framework_library", ["spring boot", "spring", "spring framework"]),
    "Node.js": ("framework_library", ["node.js", "nodejs", "node", "express", "express.js", "nestjs"]),
    "Gin": ("framework_library", ["gin", "echo framework"]),
    ".NET": ("framework_library", [".net", "dotnet", "asp.net", ".net core"]),
    "Ruby on Rails": ("framework_library", ["rails", "ruby on rails"]),
    "Celery": ("framework_library", ["celery", "rabbitmq", "message queues", "message queue", "sqs"]),
    # ---- frontend / mobile ------------------------------------------------------------
    "React": ("mobile_frontend", ["react", "react.js", "reactjs", "react hooks", "next.js", "nextjs"]),
    "React Native": ("mobile_frontend", ["react native", "react-native", "RN", "expo"]),
    "Redux": ("mobile_frontend", ["redux", "redux toolkit", "zustand", "mobx", "state management"]),
    "Angular": ("mobile_frontend", ["angular", "angularjs"]),
    "Vue.js": ("mobile_frontend", ["vue", "vue.js", "vuejs", "nuxt"]),
    "Flutter": ("mobile_frontend", ["flutter"]),
    "iOS": ("mobile_frontend", ["ios", "xcode", "app store", "testflight", "cocoapods"]),
    "Android": ("mobile_frontend", ["android", "android studio", "google play", "play store", "gradle"]),
    "Mobile Development": ("mobile_frontend", ["mobile development", "mobile apps", "mobile app", "mobile applications", "cross-platform"]),
    "Jest": ("tool", ["jest", "react testing library", "detox", "cypress", "playwright", "unit testing", "e2e testing"]),
    "Webpack": ("tool", ["webpack", "vite", "babel"]),
    "UI/UX": ("mobile_frontend", ["ui/ux", "ux", "figma", "user interface", "design systems", "accessibility"]),
    # ---- tools ------------------------------------------------------------------------
    "Git": ("tool", ["git", "github", "gitlab", "bitbucket", "version control"]),
    "Jira": ("tool", ["jira", "confluence"]),
    # ---- methodology / soft skills ----------------------------------------------------
    "Agile": ("methodology", ["agile", "scrum", "kanban", "sprint planning"]),
    "System Design": ("methodology", ["system design", "software architecture", "scalable systems", "high availability"]),
    "Testing": ("methodology", ["testing", "test automation", "tdd", "pytest", "integration testing"]),
    "Communication": ("soft_skill", ["communication", "communicating", "communicated", "presentation skills", "presentations", "presented", "presenting", "storytelling", "data storytelling", "written communication", "technical writing", "documentation", "runbooks", "design docs", "workshops"]),
    "Stakeholder Management": ("soft_skill", ["stakeholder management", "stakeholders", "stakeholder", "cross-functional", "business partners", "business stakeholders", "partner with", "partnered with", "partnering with", "worked closely with", "work closely with", "product managers", "business teams"]),
    "Leadership": ("soft_skill", ["leadership", "team lead", "led a team", "people management", "managed a team"]),
    "Mentoring": ("soft_skill", ["mentoring", "mentored", "mentorship", "coaching"]),
    "Problem Solving": ("soft_skill", ["problem solving", "problem-solving", "analytical thinking"]),
    "Customer Service": ("domain", ["customer service", "customer support", "client support", "call center", "help desk"]),
}

# Aliases matched case-sensitively (they collide with ordinary English words).
CASE_SENSITIVE = {"Go", "R", "RN"}

# Short aliases only trusted when they appear in an explicit skills list.
WEAK_ALIASES = {"ml", "ts", "js", "tf2", "rest", "node", "spring", "shell", "eda", "iam", "soa",
                "gin", "ux", "dns", "vpc", "elk", "s3", "lambda", "chroma", "torch", "transformer",
                "expo", "gradle", "testing", "logging", "analytics", "dashboard", "spreadsheets"}

# Groups of mutually transferable skills (used for partial matches in gap analysis).
RELATED_GROUPS: list[set[str]] = [
    {"PyTorch", "TensorFlow", "Keras", "JAX"},
    {"Deep Learning", "PyTorch", "TensorFlow", "Keras"},
    {"NLP", "Transformers", "LLMs", "spaCy", "NLTK", "RAG"},
    {"LLMs", "RAG", "LangChain", "Vector Databases", "Transformers"},
    {"Machine Learning", "scikit-learn", "XGBoost", "Deep Learning", "Statistics"},
    {"MLOps", "MLflow", "Kubeflow", "SageMaker", "Vertex AI", "Docker", "Kubernetes"},
    {"AWS", "GCP", "Azure"},
    {"Terraform", "Ansible"},
    {"Docker", "Kubernetes", "Helm"},
    {"Prometheus", "Grafana", "Observability", "SRE"},
    {"PostgreSQL", "MySQL", "SQL Server", "Oracle", "SQLite", "SQL"},
    {"MongoDB", "Cassandra", "DynamoDB", "Redis", "Firebase"},
    {"Snowflake", "BigQuery", "Redshift", "Databricks", "Data Warehousing"},
    {"Tableau", "Power BI", "Looker", "Metabase", "Data Visualization"},
    {"Apache Kafka", "Kinesis", "Apache Flink", "Streaming"},
    {"Apache Airflow", "Dagster"},
    {"Apache Spark", "Hadoop", "Databricks"},
    {"ETL", "Apache Airflow", "dbt", "Data Warehousing"},
    {"Python", "Go", "Java", "Scala", "Kotlin", "Rust", "C++", "C#", "Ruby"},
    {"JavaScript", "TypeScript"},
    {"React", "React Native", "Angular", "Vue.js"},
    {"React Native", "Flutter", "iOS", "Android", "Mobile Development", "Swift", "Kotlin"},
    {"Django", "Flask", "FastAPI", "Spring Boot", "Node.js", "Gin", ".NET", "Ruby on Rails"},
    {"REST APIs", "gRPC", "GraphQL", "Microservices"},
    {"Excel", "SQL", "Data Analysis"},
    {"Statistics", "A/B Testing", "Data Analysis"},
    {"Leadership", "Mentoring", "Stakeholder Management"},
    {"CI/CD", "Git", "Testing"},
    {"Python", "R"},                        # analysis languages
    {"Python", "Pandas", "NumPy"},
    {"Python", "Go", "Bash"},               # scripting / automation
    {"Apache Kafka", "Celery"},             # message brokers (RabbitMQ/SQS alias -> Celery)
    {"Elasticsearch", "Observability"},     # ELK logging
    {"Jest", "Testing"},
]

_TITLE_WORDS = (
    "engineer", "developer", "analyst", "scientist", "manager", "intern", "lead", "architect",
    "consultant", "specialist", "administrator", "designer", "head", "director", "associate",
    "representative", "officer", "researcher", "sre", "devops", "programmer", "technician",
    "coordinator", "executive", "founder", "freelance", "contractor", "trainee", "fellow",
    "student", "teacher", "professor", "assistant", "postdoc", "doctoral", "lecturer", "tutor",
    "cto", "vp", "owner", "agent",
)


def is_title_like(text: str) -> bool:
    t = text.lower()
    return any(re.search(rf"\b{w}\b", t) for w in _TITLE_WORDS)


# --------------------------------------------------------------------------- #
# Alias lookup / normalisation
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _alias_index() -> dict[str, str]:
    idx: dict[str, str] = {}
    for canon, (_, aliases) in SKILLS.items():
        idx[canon.lower()] = canon
        for a in aliases:
            idx.setdefault(a.lower(), canon)
    return idx


def category_of(skill: str) -> str:
    canon = canonicalize(skill)
    return SKILLS[canon][0] if canon in SKILLS else "other"


def canonicalize(name: str) -> str:
    """Map any alias to its canonical name; unknown skills are tidied, not dropped."""
    raw = re.sub(r"\s+", " ", name.strip().strip(".,;:-•*")).strip()
    if not raw:
        return raw
    hit = _alias_index().get(raw.lower())
    if hit:
        return hit
    # e.g. "Python 3.11", "AWS (EC2, S3)" -> try the first token / the part before "("
    for cand in (raw.split("(")[0].strip(), raw.split()[0]):
        hit = _alias_index().get(cand.lower())
        if hit and len(cand) > 2:
            return hit
    return raw if any(c.isupper() for c in raw) else raw.title()


def is_known(skill: str) -> bool:
    return canonicalize(skill) in SKILLS


@lru_cache(maxsize=1)
def _compiled_patterns() -> list[tuple[re.Pattern, str, str]]:
    pats: list[tuple[re.Pattern, str, str]] = []
    for canon, (_, aliases) in SKILLS.items():
        for alias in set(aliases + [canon]):
            flags = 0 if alias in CASE_SENSITIVE else re.IGNORECASE
            body = re.escape(alias).replace(r"\ ", r"[\s-]+")
            if alias == "Go":
                pat = r"(?<![A-Za-z0-9\-])Go(?![A-Za-z0-9\-])(?!\s+(?:to|live|ahead|over|through|back)\b)"
            elif alias == "R":
                pat = r"(?<![A-Za-z0-9&\-'.])R(?![A-Za-z0-9&'\-.])"
            else:
                pat = rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9+#])"
            pats.append((re.compile(pat, flags), canon, alias.lower()))
    # longest aliases first so "React Native" wins over "React"
    pats.sort(key=lambda p: -len(p[2]))
    return pats


def find_skill_spans(text: str, allow_weak: bool = True) -> list[tuple[str, int, int]]:
    """All non-overlapping skill mentions as (canonical, start, end), in text order.

    Longest-match-first with span masking, so "React Native" doesn't also yield "React"
    and "PostgreSQL" doesn't yield "SQL".
    """
    taken = [False] * (len(text) + 1)
    spans: list[tuple[str, int, int]] = []
    for pat, canon, alias in _compiled_patterns():
        if not allow_weak and alias in WEAK_ALIASES:
            continue
        for m in pat.finditer(text):
            s, e = m.span()
            if any(taken[s:e]):
                continue
            for i in range(s, e):
                taken[i] = True
            spans.append((canon, s, e))
    return sorted(spans, key=lambda x: x[1])


def find_skills(text: str, allow_weak: bool = True) -> list[tuple[str, int]]:
    """Return (canonical skill, first position) for skills mentioned in ``text``."""
    found: dict[str, int] = {}
    for canon, s, _ in find_skill_spans(text, allow_weak):
        found.setdefault(canon, s)
    return sorted(found.items(), key=lambda kv: kv[1])


# --------------------------------------------------------------------------- #
# Alternative requirements:  "Tableau / Power BI / Looker" = any one of them
# --------------------------------------------------------------------------- #
ALT_SEP = " / "
_ALT_MARKER = re.compile(r"\b(or|and/or|such as|e\.g\.|for example|comparable|similar|one of|any of|like)\b",
                         re.IGNORECASE)


def requirement_parts(req: str) -> list[str]:
    """Split an alternatives requirement into canonical parts (a plain skill -> [skill])."""
    return [canonicalize(p) for p in req.split(ALT_SEP) if p.strip()]


def canonicalize_requirement(req: str) -> str:
    parts = list(dict.fromkeys(requirement_parts(req)))
    return ALT_SEP.join(parts)


def _related(a: str, b: str) -> bool:
    return any(a in g and b in g for g in RELATED_GROUPS)


def requirements_from_text(text: str, allow_weak: bool = True) -> list[str]:
    """Skills required by a block of JD text, grouping alternatives.

    In a clause that signals alternatives ("X, Y or Z", "such as", "e.g."), skills that
    are mutually transferable (same related group) are merged into one requirement
    "X / Y / Z"; unrelated skills in the same clause stay separate requirements.
    """
    out: list[str] = []
    for clause in re.split(r"[;\n]|\.\s", text):
        spans = find_skill_spans(clause, allow_weak)
        names = list(dict.fromkeys(c for c, _, _ in spans))
        if not names:
            continue
        if not _ALT_MARKER.search(clause) or len(names) == 1:
            out.extend(names)
            continue
        # union-find over "related" edges
        parent = {n: n for n in names}

        def root(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for i, a in enumerate(names):
            for b in names[i + 1:]:
                if _related(a, b):
                    parent[root(b)] = root(a)
        clusters: dict[str, list[str]] = {}
        for n in names:
            clusters.setdefault(root(n), []).append(n)
        for members in clusters.values():
            out.append(ALT_SEP.join(members))
    return reduce_requirements(out)


def reduce_requirements(entries: list[str], exclude: set[str] | None = None) -> list[str]:
    """Remove redundancy: parts that are individually required (or in ``exclude``) are
    dropped from alternative groups; a group left with one part becomes a plain skill."""
    exclude = set(exclude or ())
    individual = {e for e in entries if ALT_SEP not in e}
    final: list[str] = []
    for e in entries:
        if ALT_SEP in e:
            parts = [p for p in e.split(ALT_SEP) if p not in individual and p not in exclude]
            e = ALT_SEP.join(parts)
        if e and e not in final and e not in exclude:
            final.append(e)
    return final


def related_skills(skill: str, candidate_skills: set[str]) -> list[str]:
    """Candidate skills that are transferable to ``skill`` (same related group)."""
    out: list[str] = []
    parts = requirement_parts(skill)
    for canon in parts:
        for group in RELATED_GROUPS:
            if canon in group:
                out.extend(s for s in group if s not in parts and s in candidate_skills)
    seen: set[str] = set()
    return [s for s in out if not (s in seen or seen.add(s))]


def has_requirement(req: str, candidate_skills: set[str]) -> list[str]:
    """Parts of ``req`` the candidate has (empty list = not met)."""
    low = {s.lower() for s in candidate_skills}
    return [p for p in requirement_parts(req) if p.lower() in low]
