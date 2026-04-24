# Interview Copilot — Build Tracker

## Architecture Contract (DO NOT MODIFY)

| Contract | Value |
|----------|-------|
| WS endpoint | ws://localhost:8000/ws/ui |
| Groq model | llama-3.1-8b-instant (llama3-8b-8192 decommissioned) |
| Claude model | claude-haiku-4-5-20251001 |
| Affinity flag | 0x00000011 (WDA_EXCLUDEFROMCAPTURE) |
| broadcast() owner | main.py |
| current_engine owner | main.py |

### Message Schema
- UI→BE: { "type": "set_engine", "value": "groq"|"claude" }
- BE→UI: { "type": "transcript", "text": "..." }
- BE→UI: { "type": "answer_chunk", "text": "..." }
- BE→UI: { "type": "answer_done" }

---

## File Status

| File | Status | Notes |
|------|--------|-------|
| TASKS.md | ✅ | Project tracker with architecture contract |
| .env.example | ✅ | Three keys: DEEPGRAM, GROQ, ANTHROPIC |
| requirements.txt | ✅ | 8 dependencies, no pinned versions |
| core/__init__.py | ✅ | Empty package marker |
| web/index.html | ✅ | Dark glass UI; vanilla JS WS client; 2s reconnect loop |
| core/llm_router.py | ✅ | Groq + Claude streaming paths; verbatim system prompt |
| core/audio_engine.py | ✅ | WASAPI loopback; Deepgram nova-2; reconnect loop |
| main.py | ✅ | FastAPI WS; uvicorn daemon thread; pywebview; WDA_EXCLUDEFROMCAPTURE |

---

## Session Protocol

Start every new session with:
"Read TASKS.md. State what is done, what is next, and any blockers."

After completing a file, update its status to ✅ and add notes.
Never modify the Architecture Contract section.
