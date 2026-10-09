"""Embeddings for semantic search (bge-m3, multilingual, 1024-dim)."""
import hashlib
import math
from typing import List

from .config import settings
from . import llm


def _stub_vectors(texts: List[str]) -> List[List[float]]:
    """Deterministic pseudo-embeddings so search wiring can be tested offline."""
    dim = settings.EMBED_DIM
    out = []
    for t in texts:
        h = hashlib.sha256(t.encode()).digest()
        seed = int.from_bytes(h[:8], "big")
        vec = [math.sin(seed * (i + 1) % 1000 / 100.0) for i in range(dim)]
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        out.append([v / norm for v in vec])
    return out


def embed_texts(texts: List[str]) -> List[List[float]]:
    if settings.STUB:
        return _stub_vectors(texts)
    return llm.embed(settings.EMBED_MODEL, texts)
