"""RAG (Retrieval-Augmented Generation) core helpers.

- Text extraction from PDF / DOCX / URL / raw text
- Chunking (RecursiveCharacterTextSplitter-style, no langchain dep)
- Embedding via `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
  (384 dims, multilingual FR/EN/ES/IT/DE/PT/…)
- Cosine similarity search in pure Python/numpy (works against MongoDB local;
  swap to MongoDB Atlas Vector Search when the user moves to Atlas)

The embedding model is loaded LAZILY on first call to save backend memory
when nobody is doing RAG. ~80 MB RAM once loaded.
"""

from __future__ import annotations

import io
import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("etoh.rag")

EMBEDDING_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIMS = 384

_MODEL = None


def _get_model():
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading embedding model %s …", EMBEDDING_MODEL_NAME)
        _MODEL = SentenceTransformer(EMBEDDING_MODEL_NAME)
        logger.info("Embedding model loaded (dims=%d).", EMBEDDING_DIMS)
    return _MODEL


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------
def extract_text_from_pdf(content: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(content))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception as e:
            logger.warning("pdf page extract failed: %s", e)
    return "\n\n".join(pages).strip()


def extract_text_from_docx(content: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(content))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    # Tables
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts).strip()


def extract_text_from_url(url: str, timeout: int = 15) -> str:
    import requests
    from bs4 import BeautifulSoup
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "etoh-rag/1.0"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    # Drop boilerplate
    for tag in soup(["script", "style", "nav", "footer", "aside", "header", "iframe", "form"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Chunking — recursive split on natural separators
# ---------------------------------------------------------------------------
_SEPARATORS = ["\n\n\n", "\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " "]


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> List[str]:
    """Split text into ~chunk_size-char chunks with overlap, respecting natural
    boundaries. Returns a list of non-empty trimmed chunks."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            # Try to break on a natural separator near `end`
            for sep in _SEPARATORS:
                idx = text.rfind(sep, start + chunk_size // 2, end)
                if idx != -1:
                    end = idx + len(sep)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


# ---------------------------------------------------------------------------
# Embedding & search
# ---------------------------------------------------------------------------
def embed_texts(texts: List[str]) -> List[List[float]]:
    """Batch-encode texts → list of 384-d float lists."""
    if not texts:
        return []
    model = _get_model()
    arr = model.encode(texts, batch_size=32, show_progress_bar=False, normalize_embeddings=True)
    return arr.tolist()


def embed_text(text: str) -> List[float]:
    return embed_texts([text])[0]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine sim of two pre-normalized vectors == dot product."""
    av = np.asarray(a, dtype=np.float32)
    bv = np.asarray(b, dtype=np.float32)
    return float(np.dot(av, bv))


async def search_chunks(
    db,
    user_id: str,
    query: str,
    top_k: int = 5,
    include_global: bool = True,
    use_mmr: bool = True,
    mmr_lambda: float = 0.65,
) -> List[Dict[str, Any]]:
    """Return the top_k chunks most similar to `query`, scoped to a user
    (+ optionally the system-wide `global` admin docs).

    When `use_mmr=True` we apply **Maximal Marginal Relevance** (Carbonell &
    Goldstein, 1998) over a candidate pool of 4×top_k. This avoids the case
    where 5 nearly-identical chunks from the same long document dominate the
    results and crowd out short-but-specific chunks from other documents.
    `mmr_lambda` close to 1.0 → favours similarity to query, close to 0.0 →
    favours diversity. 0.65 is a sane default for FR/multilingual content.
    """
    q_emb = embed_text(query)

    user_filter: Dict[str, Any] = {"$or": [{"user_id": user_id}]}
    if include_global:
        user_filter["$or"].append({"scope": "global"})
    cursor = db.rag_chunks.find(
        user_filter,
        {"chunk_id": 1, "doc_id": 1, "chunk_text": 1, "embedding": 1, "doc_name": 1, "scope": 1, "_id": 0},
    )

    candidates: List[Tuple[float, Dict[str, Any], List[float]]] = []
    async for c in cursor:
        emb = c.get("embedding")
        if not emb:
            continue
        score = cosine_similarity(q_emb, emb)
        candidates.append((score, c, emb))

    candidates.sort(key=lambda x: x[0], reverse=True)

    if not use_mmr or len(candidates) <= top_k:
        selected = candidates[:top_k]
    else:
        # MMR: greedy reranking from a 4×top_k pool (capped at 60)
        pool = candidates[: max(top_k * 4, 20)][:60]
        selected: List[Tuple[float, Dict[str, Any], List[float]]] = []
        remaining = list(pool)
        # First: always pick top-1 by similarity
        selected.append(remaining.pop(0))
        while len(selected) < top_k and remaining:
            best_idx = -1
            best_score = -1e9
            for i, (sim, _doc, emb) in enumerate(remaining):
                # Diversity = max cosine sim to any already-selected chunk
                max_div = max(cosine_similarity(emb, s_emb) for _s, _d, s_emb in selected)
                mmr = mmr_lambda * sim - (1 - mmr_lambda) * max_div
                if mmr > best_score:
                    best_score = mmr
                    best_idx = i
            if best_idx == -1:
                break
            selected.append(remaining.pop(best_idx))

    out: List[Dict[str, Any]] = []
    for score, c, _emb in selected:
        out.append({
            "chunk_id": c.get("chunk_id"),
            "doc_id": c.get("doc_id"),
            "doc_name": c.get("doc_name"),
            "scope": c.get("scope") or "user",
            "score": round(score, 4),
            "text": c.get("chunk_text"),
        })
    return out


def build_rag_context(chunks: List[Dict[str, Any]], max_chars: int = 3500) -> str:
    """Format retrieved chunks into a prompt-friendly context block."""
    if not chunks:
        return ""
    out_lines = ["--- DOCUMENTS UTILES (récupérés depuis votre base de connaissance) ---"]
    total = 0
    for i, c in enumerate(chunks, 1):
        snippet = (c.get("text") or "").strip()
        if not snippet:
            continue
        doc_label = c.get("doc_name") or c.get("doc_id") or "doc"
        block = f"\n[Source {i} — {doc_label}]:\n{snippet}\n"
        if total + len(block) > max_chars:
            break
        out_lines.append(block)
        total += len(block)
    out_lines.append("\n--- FIN DES DOCUMENTS ---")
    return "\n".join(out_lines)


__all__ = [
    "extract_text_from_pdf",
    "extract_text_from_docx",
    "extract_text_from_url",
    "chunk_text",
    "embed_texts",
    "embed_text",
    "search_chunks",
    "build_rag_context",
    "cosine_similarity",
    "EMBEDDING_DIMS",
    "EMBEDDING_MODEL_NAME",
]
