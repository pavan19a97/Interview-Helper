import json
import os
import time
import uuid

_DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "uploads.json")
MAX_FILE_CHARS = 60_000
MAX_PROMPT_CHARS = 40_000


def _read() -> list:
    try:
        with open(_DATA_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _write(entries: list) -> None:
    os.makedirs(os.path.dirname(_DATA_PATH), exist_ok=True)
    tmp = _DATA_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _DATA_PATH)


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
    # Fallback: try UTF-8 decode
    return data.decode("utf-8", errors="replace")[:MAX_FILE_CHARS]


def add(name: str, file_bytes: bytes) -> dict:
    """Ingest a file, persist to data store, return entry without content field."""
    entries = _read()
    content = _extract_text(name, file_bytes)
    entry = {
        "id": str(uuid.uuid4()),
        "name": name,
        "size": len(file_bytes),
        "chars": len(content),
        "enabled": True,
        "added": int(time.time()),
        "content": content,
    }
    entries.append(entry)
    _write(entries)
    print(f"[uploads] Added '{name}' ({len(content)} chars)", flush=True)
    # Return without content (for API response)
    return {k: v for k, v in entry.items() if k != "content"}


def list_all() -> list:
    """Return all entries without the content field."""
    return [{k: v for k, v in e.items() if k != "content"} for e in _read()]


def delete(item_id: str) -> bool:
    """Delete entry by id. Returns True if found and deleted."""
    entries = _read()
    new = [e for e in entries if e["id"] != item_id]
    if len(new) == len(entries):
        return False
    _write(new)
    print(f"[uploads] Deleted {item_id}", flush=True)
    return True


def set_enabled(item_id: str, enabled: bool) -> bool:
    """Toggle enabled flag. Returns True if found."""
    entries = _read()
    for e in entries:
        if e["id"] == item_id:
            e["enabled"] = enabled
            _write(entries)
            print(f"[uploads] {'Enabled' if enabled else 'Disabled'} '{e['name']}'", flush=True)
            return True
    return False


def build_context_block() -> str:
    """Build combined context string from all enabled uploads (capped at MAX_PROMPT_CHARS)."""
    entries = _read()
    parts = []
    total = 0
    for e in entries:
        if not e.get("enabled"):
            continue
        chunk = e.get("content", "")
        if not chunk:
            continue
        remaining = MAX_PROMPT_CHARS - total
        if len(chunk) > remaining:
            chunk = chunk[:remaining]
        parts.append(f"=== {e['name']} ===\n{chunk}")
        total += len(chunk)
        if total >= MAX_PROMPT_CHARS:
            break
    if not parts:
        return ""
    return "\n\n".join(parts)
