"""RAG (Retrieval-Augmented Generation) routes.

- POST /api/rag/documents  (user uploads via Hub)
- GET  /api/rag/documents
- DELETE /api/rag/documents/{doc_id}
- POST /api/rag/search

- POST /api/admin/rag/documents  (admin uploads from etoh.io/studio/admin, can mark
  scope=global to share with every user)
- GET  /api/admin/rag/documents

Feature-gating: regular users need plan with `features.rag=true` (Pro+).
Admin uploads via X-Admin-Key.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from core.db import db, _now
from core.security import get_current_user
from core.subscriptions import get_features
from core.rag import (
    chunk_text,
    embed_texts,
    extract_text_from_docx,
    extract_text_from_pdf,
    extract_text_from_url,
    search_chunks,
)

logger = logging.getLogger("etoh.rag.routes")

router = APIRouter(prefix="/api/rag", tags=["rag"])
admin_router = APIRouter(prefix="/api/admin/rag", tags=["admin", "rag"])

MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB per file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _require_rag_or_402(user: Dict[str, Any]) -> Dict[str, Any]:
    feats = get_features(user or {})
    if not feats["features"].get("rag"):
        raise HTTPException(402, "RAG indisponible avec votre plan. Passez en Pro pour débloquer.")
    return feats


async def _enforce_doc_quota(user_id: str, plan_features: Dict[str, Any]) -> None:
    """Reject upload if user already at quota (plan-level)."""
    max_docs = int(plan_features["features"].get("rag_max_docs") or 0)
    if max_docs == -1:  # unlimited
        return
    count = await db.rag_documents.count_documents({"user_id": user_id})
    if count >= max_docs:
        raise HTTPException(
            402,
            f"Quota atteint ({max_docs} documents). Passez en Business pour des documents illimités.",
        )


async def _store_document(
    *,
    user_id: Optional[str],
    scope: str,
    source_type: str,
    name: str,
    text: str,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Chunk + embed + persist a freshly-extracted document. Returns the doc row."""
    if not text or len(text.strip()) < 30:
        raise HTTPException(400, "Document text is empty or too short (< 30 chars).")
    chunks = chunk_text(text, chunk_size=800, overlap=100)
    if not chunks:
        raise HTTPException(400, "Could not chunk the document.")

    doc_id = f"doc_{uuid.uuid4().hex[:14]}"
    now = _now()
    embeddings = embed_texts(chunks)  # one batch call to the model

    doc_row = {
        "doc_id": doc_id,
        "user_id": user_id,
        "scope": scope,  # "user" | "global"
        "source_type": source_type,
        "name": name,
        "char_count": len(text),
        "chunk_count": len(chunks),
        "created_at": now,
        "updated_at": now,
        "meta": extra_meta or {},
    }
    await db.rag_documents.insert_one(doc_row)
    await db.rag_chunks.insert_many([
        {
            "chunk_id": f"chk_{uuid.uuid4().hex[:14]}",
            "doc_id": doc_id,
            "user_id": user_id,
            "scope": scope,
            "doc_name": name,
            "chunk_index": i,
            "chunk_text": chunk,
            "embedding": emb,
            "created_at": now,
        }
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ])
    return {
        "doc_id": doc_id,
        "name": name,
        "scope": scope,
        "source_type": source_type,
        "chunk_count": len(chunks),
        "char_count": len(text),
    }


# ---------------------------------------------------------------------------
# User-facing RAG endpoints
# ---------------------------------------------------------------------------
class UrlIngestIn(BaseModel):
    url: str
    name: Optional[str] = None


class TextIngestIn(BaseModel):
    text: str = Field(min_length=30)
    name: str = Field(min_length=1, max_length=200)


@router.post("/documents")
async def ingest_document(
    request: Request,
    user=Depends(get_current_user),
    file: UploadFile | None = File(default=None),
):
    """Upload a PDF or DOCX file (multipart form, field `file`).

    For URL or raw text use POST /api/rag/documents/url and /text respectively.
    """
    feats = _require_rag_or_402(user)
    await _enforce_doc_quota(user["user_id"], feats)
    if not file:
        raise HTTPException(400, "file is required (multipart form-data field 'file')")

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File too large (max {MAX_UPLOAD_BYTES // 1024 // 1024} MB).")

    fname = file.filename or "document"
    lower = fname.lower()
    if lower.endswith(".pdf"):
        text = extract_text_from_pdf(content)
        source_type = "pdf"
    elif lower.endswith(".docx"):
        text = extract_text_from_docx(content)
        source_type = "docx"
    else:
        raise HTTPException(400, "Only .pdf and .docx are supported for file uploads.")

    return await _store_document(
        user_id=user["user_id"],
        scope="user",
        source_type=source_type,
        name=fname,
        text=text,
        extra_meta={"bytes": len(content)},
    )


@router.post("/documents/url")
async def ingest_url(payload: UrlIngestIn, user=Depends(get_current_user)):
    feats = _require_rag_or_402(user)
    await _enforce_doc_quota(user["user_id"], feats)
    try:
        text = extract_text_from_url(payload.url)
    except Exception as e:
        raise HTTPException(400, f"URL fetch failed: {e}")
    return await _store_document(
        user_id=user["user_id"],
        scope="user",
        source_type="url",
        name=payload.name or payload.url,
        text=text,
        extra_meta={"url": payload.url},
    )


@router.post("/documents/text")
async def ingest_text(payload: TextIngestIn, user=Depends(get_current_user)):
    feats = _require_rag_or_402(user)
    await _enforce_doc_quota(user["user_id"], feats)
    return await _store_document(
        user_id=user["user_id"],
        scope="user",
        source_type="text",
        name=payload.name,
        text=payload.text,
    )


@router.get("/documents")
async def list_documents(user=Depends(get_current_user)):
    cursor = db.rag_documents.find(
        {"$or": [{"user_id": user["user_id"]}, {"scope": "global"}]},
        {"_id": 0, "embedding": 0},
    ).sort("created_at", -1)
    out = []
    async for d in cursor:
        out.append(d)
    return {"documents": out, "count": len(out)}


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, user=Depends(get_current_user)):
    doc = await db.rag_documents.find_one({"doc_id": doc_id, "user_id": user["user_id"]})
    if not doc:
        raise HTTPException(404, "document not found")
    await db.rag_chunks.delete_many({"doc_id": doc_id})
    await db.rag_documents.delete_one({"doc_id": doc_id})
    return {"ok": True, "doc_id": doc_id}


class RagSearchIn(BaseModel):
    query: str = Field(min_length=2)
    top_k: int = Field(default=5, ge=1, le=20)


@router.post("/search")
async def rag_search(payload: RagSearchIn, user=Depends(get_current_user)):
    """Return the top_k most similar chunks for the user's query."""
    _require_rag_or_402(user)
    hits = await search_chunks(db, user["user_id"], payload.query, top_k=payload.top_k)
    return {"query": payload.query, "results": hits, "count": len(hits)}


# ---------------------------------------------------------------------------
# Admin RAG endpoints (etoh.io/studio/admin back-office)
# ---------------------------------------------------------------------------
from routes.admin import require_admin_key  # type: ignore  # noqa: E402


@admin_router.post("/documents")
async def admin_ingest_document(
    _: None = Depends(require_admin_key),
    file: UploadFile | None = File(default=None),
    scope: str = Form(default="global"),
    name: Optional[str] = Form(default=None),
):
    """Upload a PDF/DOCX as admin. `scope=global` makes it visible to ALL users
    (system-wide knowledge base); `scope=user` requires `user_id` form field."""
    if scope not in ("global", "user"):
        raise HTTPException(400, "scope must be 'global' or 'user'")
    if not file:
        raise HTTPException(400, "file is required")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large.")
    fname = name or file.filename or "admin_doc"
    lower = (file.filename or "").lower()
    if lower.endswith(".pdf"):
        text = extract_text_from_pdf(content)
        source_type = "pdf"
    elif lower.endswith(".docx"):
        text = extract_text_from_docx(content)
        source_type = "docx"
    else:
        raise HTTPException(400, "Only .pdf and .docx supported.")
    return await _store_document(
        user_id=None if scope == "global" else None,  # global has no owner
        scope=scope,
        source_type=source_type,
        name=fname,
        text=text,
        extra_meta={"uploaded_by": "admin", "bytes": len(content)},
    )


class AdminUrlIn(BaseModel):
    url: str
    name: Optional[str] = None
    scope: str = "global"


@admin_router.post("/documents/url")
async def admin_ingest_url(payload: AdminUrlIn, _: None = Depends(require_admin_key)):
    if payload.scope not in ("global", "user"):
        raise HTTPException(400, "scope must be 'global' or 'user'")
    try:
        text = extract_text_from_url(payload.url)
    except Exception as e:
        raise HTTPException(400, f"URL fetch failed: {e}")
    return await _store_document(
        user_id=None,
        scope=payload.scope,
        source_type="url",
        name=payload.name or payload.url,
        text=text,
        extra_meta={"url": payload.url, "uploaded_by": "admin"},
    )


@admin_router.get("/documents")
async def admin_list_documents(_: None = Depends(require_admin_key)):
    cursor = db.rag_documents.find({}, {"_id": 0, "embedding": 0}).sort("created_at", -1)
    out = []
    async for d in cursor:
        out.append(d)
    return {"documents": out, "count": len(out)}


@admin_router.delete("/documents/{doc_id}")
async def admin_delete_document(doc_id: str, _: None = Depends(require_admin_key)):
    doc = await db.rag_documents.find_one({"doc_id": doc_id})
    if not doc:
        raise HTTPException(404, "document not found")
    await db.rag_chunks.delete_many({"doc_id": doc_id})
    await db.rag_documents.delete_one({"doc_id": doc_id})
    return {"ok": True, "doc_id": doc_id}
