# Ranking evaluation - NDCG@5 against human rankings

Candidates: **50**, job descriptions: **6**, human-graded pairs: **300** (grades 0-3, gain 2^rel-1).

Label source: Proxy annotations written by an AI assistant following the rubric, by reading each resume against each JD. Replace or adjust them with real human judgments via the app's Annotate screen or by editing this file.

Resume extraction used: 0 via Claude, 50 via the offline parser.


## Leaderboard

| # | Method | Family | Representation | NDCG@5 | NDCG@10 | P@5 (grade>=2) |
|---|---|---|---|---|---|---|
| 1 | BM25 (lexical) | lexical | structured | **0.955** | 0.980 | 1.00 |
| 2 | MiniLM-L6 (contextual) | contextual | structured | **0.953** | 0.945 | 1.00 |
| 3 | GloVe-100 (mean) | static | structured | **0.947** | 0.901 | 0.93 |
| 4 | BGE-small (contextual) | contextual | structured | **0.928** | 0.945 | 0.97 |
| 5 | Hybrid: BGE + skill coverage | hybrid | structured | **0.921** | 0.958 | 0.97 |
| 6 | BM25 (lexical) | lexical | raw | **0.921** | 0.967 | 0.97 |
| 7 | GloVe-100 (SIF) | static | structured | **0.908** | 0.931 | 0.90 |
| 8 | Hybrid: BGE + skill coverage | hybrid | raw | **0.869** | 0.937 | 0.97 |
| 9 | BGE-small (contextual) | contextual | raw | **0.864** | 0.910 | 0.93 |
| 10 | MiniLM-L6 (contextual) | contextual | raw | **0.854** | 0.896 | 0.93 |
| 11 | Two-stage rerank (experimental) | hybrid | structured | **0.827** | 0.905 | 0.93 |
| 12 | Two-stage rerank (experimental) | hybrid | raw | **0.827** | 0.908 | 0.93 |
| 13 | GloVe-100 (SIF) | static | raw | **0.815** | 0.856 | 0.83 |
| 14 | GloVe-100 (mean) | static | raw | **0.806** | 0.829 | 0.73 |

## Static vs contextual embeddings

- Best static: **glove_mean** (structured) - NDCG@5 = 0.947
- Best contextual: **minilm** (structured) - NDCG@5 = 0.953
- Difference: **+0.006**; contextual better on 5/6 jobs (0 ties); exact paired sign-flip test p = 0.781 (with only 6 queries the smallest attainable p is 0.031).
- Like-for-like on `structured` text: static glove_mean 0.947 vs contextual minilm 0.953 (delta +0.006; contextual better on 5/6 jobs, p = 0.781)
- Like-for-like on `raw` text: static glove_sif 0.815 vs contextual bge_small 0.864 (delta +0.049; contextual better on 3/6 jobs, p = 0.469)

## Per-job NDCG@5 (structured representation)

| Method | J01 Senior Machine Learnin | J02 Data Analyst | J03 Backend Software Engin | J04 React Native Mobile De | J05 Site Reliability Engin | J06 Data Engineer | Mean |
|---|---|---|---|---|---|---|---|
| BM25 (lexical) | 0.895 | 0.925 | 1.000 | 1.000 | 0.910 | 1.000 | **0.955** |
| MiniLM-L6 (contextual) | 0.767 | 1.000 | 1.000 | 1.000 | 0.976 | 0.976 | **0.953** |
| GloVe-100 (mean) | 0.991 | 0.903 | 0.991 | 0.991 | 0.849 | 0.960 | **0.947** |
| BGE-small (contextual) | 0.737 | 0.925 | 0.991 | 0.991 | 0.949 | 0.976 | **0.928** |
| Hybrid: BGE + skill coverage | 0.805 | 1.000 | 0.976 | 0.869 | 0.886 | 0.991 | **0.921** |
| GloVe-100 (SIF) | 0.841 | 0.804 | 0.976 | 0.991 | 0.835 | 1.000 | **0.908** |
| Two-stage rerank (experimental) | 0.712 | 0.842 | 0.781 | 0.753 | 0.886 | 0.991 | **0.827** |

## Per-job NDCG@5 (raw representation)

| Method | J01 | J02 | J03 | J04 | J05 | J06 | Mean |
|---|---|---|---|---|---|---|---|
| BM25 (lexical) | 0.764 | 0.903 | 0.868 | 0.991 | 1.000 | 1.000 | **0.921** |
| Hybrid: BGE + skill coverage | 0.805 | 0.916 | 0.976 | 0.764 | 0.868 | 0.886 | **0.869** |
| BGE-small (contextual) | 0.737 | 0.925 | 0.976 | 0.764 | 0.895 | 0.886 | **0.864** |
| MiniLM-L6 (contextual) | 0.660 | 0.925 | 0.895 | 0.827 | 0.868 | 0.949 | **0.854** |
| Two-stage rerank (experimental) | 0.712 | 0.842 | 0.781 | 0.753 | 0.886 | 0.991 | **0.827** |
| GloVe-100 (SIF) | 0.865 | 0.916 | 0.714 | 0.827 | 0.625 | 0.946 | **0.815** |
| GloVe-100 (mean) | 0.835 | 0.887 | 0.697 | 0.814 | 0.644 | 0.960 | **0.806** |

## Why static embeddings struggle here (GloVe OOV)

- Mean share of resume tokens missing from the GloVe-100 vocabulary: 6.2%.
- Taxonomy skills with at least one token not in GloVe (28): C#, LLMs, PyTorch, TensorFlow, scikit-learn, XGBoost, NLTK, LangChain, MLOps, MLflow, Kubeflow, SageMaker, Dagster, BigQuery, Databricks, Metabase, Redis, DynamoDB, Elasticsearch, Kubernetes, Grafana, Microservices, Serverless, gRPC, GraphQL, FastAPI, Vue.js, Webpack
- Words that *are* in the vocabulary carry their 2014 general-English sense ('spark', 'airflow', 'docker', 'rust', 'swift'), so averaging blurs role-specific meaning.

## Top-5 per method (job J01 example, structured)

- **glove_mean**: R25(3), R01(3), R08(3), R32(2), R33(3)
- **glove_sif**: R25(3), R33(3), R19(2), R31(1), R01(3)
- **minilm**: R19(2), R01(3), R12(2), R25(3), R08(3)
- **bge_small**: R01(3), R12(2), R25(3), R32(2), R34(1)
- **hybrid**: R01(3), R25(3), R12(2), R32(2), R19(2)
- **rerank**: R01(3), R31(1), R25(3), R19(2), R32(2)
- **bm25**: R01(3), R25(3), R19(2), R08(3), R12(2)

Numbers in brackets are the human grades of the retrieved candidates.
