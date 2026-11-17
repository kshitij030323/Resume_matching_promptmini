"""Embedding back-ends compared in Deliverable 2.

Static (one vector per word type, context-independent)
  * ``glove_mean`` - average of GloVe-100 vectors of in-vocabulary, non-stopword tokens.
  * ``glove_sif``  - Smooth Inverse Frequency weighting (Arora et al., 2017):
                     weight a/(a+p(w)) and removal of the first principal component.

Contextual (transformer sentence encoders, one vector per passage)
  * ``minilm``    - sentence-transformers/all-MiniLM-L6-v2 (384-d, 256-token window).
  * ``bge_small`` - BAAI/bge-small-en-v1.5 (384-d, 512-token window).
  Long documents are split into sentence-packed chunks that fit the encoder window;
  chunk vectors are length-weighted, averaged and re-normalised.

Lexical baseline (no embeddings): ``bm25`` - Okapi BM25 on the same tokens.

All dense vectors are L2-normalised so cosine similarity == dot product, which is
what the ChromaDB collections (``hnsw:space=cosine``) use.
"""

from __future__ import annotations

import math
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

import numpy as np

from . import config

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

_TOKEN_RE = re.compile(r"[a-z][a-z0-9+#]*(?:\.[a-z0-9]+)?|\d+(?:\.\d+)?")


@lru_cache(maxsize=1)
def _stopwords() -> frozenset[str]:
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

    extra = {"experience", "years", "year", "using", "used", "work", "worked", "team", "teams",
             "including", "strong", "ability", "role", "will", "new", "across", "within", "etc"}
    return frozenset(ENGLISH_STOP_WORDS | extra)


def tokenize(text: str) -> list[str]:
    toks = _TOKEN_RE.findall(text.lower())
    sw = _stopwords()
    return [t for t in toks if t not in sw and len(t) > 1]


def _l2(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(n == 0, 1.0, n)


# =============================================================================
# Static embeddings - GloVe
# =============================================================================
@lru_cache(maxsize=1)
def load_glove():
    from gensim.models import KeyedVectors

    if config.GLOVE_KV_PATH.exists():
        return KeyedVectors.load(str(config.GLOVE_KV_PATH), mmap="r")
    import gensim.downloader as api

    kv = api.load(config.GLOVE_NAME)  # ~130 MB download on first run
    kv.save(str(config.GLOVE_KV_PATH))
    return kv


@dataclass
class EmbedderInfo:
    key: str
    label: str
    family: str  # static | contextual | lexical | hybrid
    description: str


class GloveMean:
    info = EmbedderInfo(
        "glove_mean", "GloVe-100 (mean)", "static",
        "Average of pre-trained GloVe word vectors (Wikipedia+Gigaword, 400k vocab). "
        "Context-independent; out-of-vocabulary tech terms are dropped.")

    def __init__(self):
        self.kv = load_glove()
        self.dim = self.kv.vector_size

    def fit(self, docs: list[str]) -> None:  # nothing to learn
        pass

    def _vec(self, text: str) -> np.ndarray:
        toks = [t for t in tokenize(text) if t in self.kv.key_to_index]
        if not toks:
            return np.zeros(self.dim, dtype=np.float32)
        return np.mean([self.kv[t] for t in toks], axis=0)

    def embed(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        return _l2(np.vstack([self._vec(t) for t in texts]).astype(np.float32))

    def oov_rate(self, text: str) -> float:
        toks = tokenize(text)
        return 0.0 if not toks else sum(t not in self.kv.key_to_index for t in toks) / len(toks)


class GloveSIF(GloveMean):
    info = EmbedderInfo(
        "glove_sif", "GloVe-100 (SIF)", "static",
        "Smooth-Inverse-Frequency weighted GloVe average with the corpus' first principal "
        "component removed (Arora et al., 2017) - a strong static baseline.")

    def __init__(self, a: float = 1e-3):
        super().__init__()
        self.a = a
        self.pc: Optional[np.ndarray] = None
        n = len(self.kv.key_to_index)
        # GloVe vocab is frequency-ordered; approximate p(w) with a Zipf law over rank.
        self._harmonic = math.log(n) + 0.5772

    def _p(self, word: str) -> float:
        rank = self.kv.key_to_index[word] + 1
        return 1.0 / (rank * self._harmonic)

    def _vec(self, text: str) -> np.ndarray:
        toks = [t for t in tokenize(text) if t in self.kv.key_to_index]
        if not toks:
            return np.zeros(self.dim, dtype=np.float32)
        w = np.array([self.a / (self.a + self._p(t)) for t in toks], dtype=np.float32)
        return (w[:, None] * np.vstack([self.kv[t] for t in toks])).sum(0) / len(toks)

    def fit(self, docs: list[str]) -> None:
        X = np.vstack([self._vec(d) for d in docs])
        X = X[np.linalg.norm(X, axis=1) > 0]
        if len(X) >= 2:
            _, _, vt = np.linalg.svd(X - 0.0, full_matrices=False)
            self.pc = vt[0]

    def embed(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        X = np.vstack([self._vec(t) for t in texts]).astype(np.float32)
        if self.pc is not None:
            X = X - np.outer(X @ self.pc, self.pc)
        return _l2(X)


# =============================================================================
# Contextual embeddings - sentence transformers
# =============================================================================
@lru_cache(maxsize=4)
def load_sentence_model(name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(name, device="cpu")


def chunk_text(text: str, max_words: int) -> list[str]:
    """Pack sentences/lines into chunks of at most ``max_words`` words."""
    pieces = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", text) if p.strip()]
    chunks, cur, n = [], [], 0
    for p in pieces:
        w = len(p.split())
        if w > max_words:  # very long line: hard split
            words = p.split()
            for i in range(0, len(words), max_words):
                chunks.append(" ".join(words[i:i + max_words]))
            continue
        if n + w > max_words and cur:
            chunks.append(" ".join(cur))
            cur, n = [], 0
        cur.append(p)
        n += w
    if cur:
        chunks.append(" ".join(cur))
    return chunks or [text[:1000]]


class SentenceEmbedder:
    def __init__(self, key: str, label: str, model_name: str, max_words: int, description: str,
                 query_prefix: str = ""):
        self.info = EmbedderInfo(key, label, "contextual", description)
        self.model_name = model_name
        self.max_words = max_words
        self.query_prefix = query_prefix
        self.model = load_sentence_model(model_name)
        self.dim = self.model.get_sentence_embedding_dimension()

    def fit(self, docs: list[str]) -> None:
        pass

    def embed(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        all_chunks, owners, weights = [], [], []
        for i, t in enumerate(texts):
            for c in chunk_text(t, self.max_words):
                all_chunks.append((self.query_prefix + c) if is_query else c)
                owners.append(i)
                weights.append(len(c.split()))
        E = self.model.encode(all_chunks, batch_size=32, normalize_embeddings=True,
                              show_progress_bar=False, convert_to_numpy=True)
        out = np.zeros((len(texts), E.shape[1]), dtype=np.float32)
        for e, o, w in zip(E, owners, weights):
            out[o] += w * e
        return _l2(out)

    def similarity_matrix(self, a: list[str], b: list[str]) -> np.ndarray:
        """Plain (unchunked) cosine matrix - used for skill/evidence matching."""
        if not a or not b:
            return np.zeros((len(a), len(b)), dtype=np.float32)
        ea = self.model.encode(a, normalize_embeddings=True, show_progress_bar=False)
        eb = self.model.encode(b, normalize_embeddings=True, show_progress_bar=False)
        return ea @ eb.T


def make_minilm() -> SentenceEmbedder:
    return SentenceEmbedder(
        "minilm", "MiniLM-L6 (contextual)", config.MINILM_MODEL, max_words=150,
        description="all-MiniLM-L6-v2 sentence-transformer (6-layer, 384-d), trained "
                    "contrastively on 1B sentence pairs; documents chunked to its 256-token window.")


def make_bge() -> SentenceEmbedder:
    return SentenceEmbedder(
        "bge_small", "BGE-small (contextual)", config.BGE_MODEL, max_words=300,
        description="BAAI bge-small-en-v1.5 (12-layer, 384-d) retrieval encoder; "
                    "documents chunked to its 512-token window.")


# =============================================================================
# Lexical baseline - BM25
# =============================================================================
@dataclass
class BM25:
    k1: float = 1.5
    b: float = 0.75
    docs: dict[str, Counter] = field(default_factory=dict)
    lens: dict[str, int] = field(default_factory=dict)
    df: Counter = field(default_factory=Counter)

    info = EmbedderInfo("bm25", "BM25 (lexical)", "lexical",
                        "Okapi BM25 keyword matching - no embeddings; a reference baseline.")

    def add(self, doc_id: str, text: str) -> None:
        if doc_id in self.docs:
            for t in self.docs[doc_id]:
                self.df[t] -= 1
        toks = tokenize(text)
        self.docs[doc_id] = Counter(toks)
        self.lens[doc_id] = len(toks)
        for t in set(toks):
            self.df[t] += 1

    def scores(self, query: str) -> dict[str, float]:
        n = len(self.docs)
        avgdl = (sum(self.lens.values()) / n) if n else 1.0
        q = Counter(tokenize(query))
        out: dict[str, float] = {}
        for d, tf in self.docs.items():
            s = 0.0
            for t in q:
                if t not in tf:
                    continue
                idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                f = tf[t]
                s += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.lens[d] / avgdl))
            out[d] = s
        return out
