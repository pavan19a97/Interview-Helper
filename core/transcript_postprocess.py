import json
import os
import re
import threading

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "keyterms.json")
_lock = threading.Lock()
_cached: dict = {}
_mtime: float = 0.0


def _load_config() -> dict:
    global _cached, _mtime
    with _lock:
        try:
            mt = os.path.getmtime(_CONFIG_PATH)
            if mt != _mtime:
                with open(_CONFIG_PATH, encoding="utf-8") as f:
                    _cached = json.load(f)
                _mtime = mt
                print(f"[postprocess] Reloaded keyterms config ({len(_cached.get('keyterms', []))} terms, "
                      f"{len(_cached.get('postprocess', {}))} replacements)", flush=True)
        except Exception as e:
            print(f"[postprocess] Config load error: {e}", flush=True)
        return _cached


def get_dg_keyterms_qs() -> str:
    """Returns URL query string fragment: keyterm=X&keyterm=Y&..."""
    cfg = _load_config()
    terms = cfg.get("keyterms", [])
    if not terms:
        return ""
    return "&".join(f"keyterm={t}" for t in terms)


def postprocess_transcript(text: str) -> str:
    """Apply mishearing corrections from config. Returns corrected text."""
    cfg = _load_config()
    replacements = cfg.get("postprocess", {})
    if not replacements:
        return text
    # Sort longer phrases first — prevents partial matches shadowing full phrases
    for wrong, right in sorted(replacements.items(), key=lambda x: -len(x[0])):
        pattern = r"(?<![A-Za-z0-9])" + re.escape(wrong) + r"(?![A-Za-z0-9])"
        text = re.sub(pattern, right, text, flags=re.IGNORECASE)
    return text
