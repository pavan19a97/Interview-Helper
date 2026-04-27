"""
Document context store with local vector retrieval.

- Files are extracted to text, chunked, embedded, and persisted in ChromaDB.
- A small JSON manifest (data/uploads.json) keeps doc-level metadata + the
  enabled flag (used as a query-time filter).
- build_context_block(query) embeds the query, retrieves top-K relevant
  chunks across enabled docs, and returns them as a system-prompt block.
- Migration from v1.4.0: legacy entries with a `content` field are
  re-embedded once on first access, then the field is stripped.
"""

import json
import os
import time
import uuid

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_INDEX_PATH = os.path.join(_DATA_DIR, "uploads.json")
_CHROMA_PATH = os.path.join(_DATA_DIR, "chroma")
_COLLECTION_NAME = "uploads"

MAX_FILE_CHARS = 60_000
CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200
TOP_K = 4

# Lazy-init: first access triggers Chroma client creation + onnx model download
_collection = None


def _get_collection():
    """Lazy-init Chroma persistent client + collection on first use.
    First call downloads the default embedding model (~80MB onnx)."""
    global _collection
    if _collection is not None:
        return _collection
    import chromadb
    os.makedirs(_CHROMA_PATH, exist_ok=True)
    client = chromadb.PersistentClient(path=_CHROMA_PATH)
    _collection = client.get_or_create_collection(name=_COLLECTION_NAME)
    print(f"[uploads] Chroma ready ({_collection.count()} chunks indexed)", flush=True)
    return _collection


def _read_index() -> list:
    try:
        with open(_INDEX_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _write_index(entries: list) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    tmp = _INDEX_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _INDEX_PATH)


def _extract_text(name: str, data: bytes) -> str:
    ext = os.path.splitext(name)[1].lower()
    if ext in (".txt", ".md", ".json"):
        return data.decode("utf-8", errors="replace")[:MAX_FILE_CHARS]
    if ext == ".pdf":
        try:
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join(p.extract_text() or "" for p in reader.pages)
            return text[:MAX_FILE_CHARS]
        except Exception as e:
            return f"[PDF parse error: {e}]"
    if ext == ".docx":
        try:
            import io
            from docx import Document
            doc = Document(io.BytesIO(data))
            text = "\n".join(p.text for p in doc.paragraphs)
            return text[:MAX_FILE_CHARS]
        except Exception as e:
            return f"[DOCX parse error: {e}]"
    return data.decode("utf-8", errors="replace")[:MAX_FILE_CHARS]


def _chunk_text(text: str) -> list:
    """Greedy ~CHUNK_SIZE-char chunks with CHUNK_OVERLAP overlap.
    Backs up to a clean sentence/paragraph break in the last 30% of each chunk."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= CHUNK_SIZE:
        return [text]

    chunks = []
    pos = 0
    while pos < len(text):
        end = min(pos + CHUNK_SIZE, len(text))
        # Back up to a clean break unless we're already at the doc end
        if end < len(text):
            window_start = pos + int(CHUNK_SIZE * 0.7)
            best = -1
            for sep, slen in (("\n\n", 2), (". ", 2), ("? ", 2), ("! ", 2), ("\n", 1)):
                idx = text.rfind(sep, window_start, end)
                if idx > best:
                    best = idx + slen
            if best > pos:
                end = best

        chunk = text[pos:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        pos = max(pos + 1, end - CHUNK_OVERLAP)

    return chunks


def _embed_doc(doc_id: str, name: str, content: str) -> int:
    """Chunk content and add to Chroma. Returns chunks added."""
    chunks = _chunk_text(content)
    if not chunks:
        return 0
    coll = _get_collection()
    ids = [f"{doc_id}::{i}" for i in range(len(chunks))]
    metadatas = [
        {"doc_id": doc_id, "doc_name": name, "chunk_idx": i}
        for i in range(len(chunks))
    ]
    coll.add(documents=chunks, ids=ids, metadatas=metadatas)
    return len(chunks)


def _migrate_legacy() -> None:
    """One-time migration: re-embed any v1.4.0 entries that still carry a
    `content` field. Strips the field after embedding so it's idempotent."""
    entries = _read_index()
    legacy = [e for e in entries if "content" in e and e.get("content")]
    if not legacy:
        return

    print(f"[uploads] Migrating {len(legacy)} legacy doc(s) to vector DB...", flush=True)
    coll = _get_collection()

    for entry in legacy:
        existing = coll.get(where={"doc_id": entry["id"]}, limit=1)
        if existing and existing.get("ids"):
            del entry["content"]
            continue
        try:
            n = _embed_doc(entry["id"], entry["name"], entry["content"])
            entry["chunks"] = n
            print(f"[uploads]   '{entry['name']}' -> {n} chunks", flush=True)
        except Exception as e:
            print(f"[uploads]   migration failed for '{entry['name']}': {e}", flush=True)
            continue
        del entry["content"]

    _write_index(entries)
    print("[uploads] Migration complete", flush=True)


def add(name: str, file_bytes: bytes) -> dict:
    """Ingest a file: extract text, chunk, embed, persist metadata."""
    _migrate_legacy()

    content = _extract_text(name, file_bytes)
    doc_id = str(uuid.uuid4())
    n_chunks = _embed_doc(doc_id, name, content)

    entry = {
        "id": doc_id,
        "name": name,
        "size": len(file_bytes),
        "chars": len(content),
        "chunks": n_chunks,
        "enabled": True,
        "added": int(time.time()),
    }
    entries = _read_index()
    entries.append(entry)
    _write_index(entries)
    print(f"[uploads] Added '{name}' ({len(content)} chars -> {n_chunks} chunks)", flush=True)
    return entry


def list_all() -> list:
    """Return all entries (no content field — chunks live in Chroma)."""
    return [{k: v for k, v in e.items() if k != "content"} for e in _read_index()]


def delete(item_id: str) -> bool:
    """Remove entry from manifest + its chunks from Chroma."""
    entries = _read_index()
    new = [e for e in entries if e["id"] != item_id]
    if len(new) == len(entries):
        return False

    try:
        coll = _get_collection()
        coll.delete(where={"doc_id": item_id})
    except Exception as e:
        print(f"[uploads] Warning: chunk cleanup failed for {item_id}: {e}", flush=True)

    _write_index(new)
    print(f"[uploads] Deleted {item_id}", flush=True)
    return True


def set_enabled(item_id: str, enabled: bool) -> bool:
    """Toggle the enabled flag (used as a query-time filter)."""
    entries = _read_index()
    for e in entries:
        if e["id"] == item_id:
            e["enabled"] = enabled
            _write_index(entries)
            print(f"[uploads] {'Enabled' if enabled else 'Disabled'} '{e['name']}'", flush=True)
            return True
    return False


def build_context_block(query: str = "") -> str:
    """Retrieve top-K chunks relevant to the query from enabled docs.
    Returns formatted block ready to inject into a system prompt, or "" if
    no enabled docs / no query / retrieval fails."""
    if not query or not query.strip():
        return ""

    entries = _read_index()
    enabled_ids = [e["id"] for e in entries if e.get("enabled")]
    if not enabled_ids:
        return ""

    try:
        _migrate_legacy()
        coll = _get_collection()
        where = {"doc_id": enabled_ids[0]} if len(enabled_ids) == 1 \
                else {"doc_id": {"$in": enabled_ids}}

        result = coll.query(
            query_texts=[query],
            n_results=TOP_K,
            where=where,
        )
    except Exception as e:
        print(f"[uploads] Retrieval error: {e}", flush=True)
        return ""

    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    if not docs:
        return ""

    parts = []
    for chunk, meta in zip(docs, metas):
        src = (meta or {}).get("doc_name", "unknown")
        parts.append(f"=== {src} ===\n{chunk}")
    return "\n\n".join(parts)
