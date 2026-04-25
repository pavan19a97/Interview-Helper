# Interview Helper - Changelog

All notable changes to this project will be documented in this file.

---

## [Unreleased]

### Added
- **Context Management** - Created `core/context_manager.py` to track Q&A history
  - Tracks conversation history across multiple exchanges
  - Maintains last 5 exchanges for context
  - Provides context to LLM for more relevant responses

- **Question Relationship Analysis** - Detects question types:
  - `new_topic` - Independent new question
  - `rephrased` - Same question asked differently (>40% word overlap)
  - `follow_up` - Builds on previous answer
  - `clarification` - Asks for more detail

- **Enhanced Labeling** - Updated frontend labels:
  - Changed "Q" → "Interviewer" (orange)
  - Changed "A" → "AI" (green)
  - Added question type indicators in history

- **Interviewee Persona** - Updated system prompt with human-like response style:
  - No structured bullet lists
  - Natural conversational openers
  - Shows vulnerability and enthusiasm
  - Ends with check-in questions
  - 2-4 sentence responses

- **Comprehensive Logging** - Added detailed startup logs:
  - `[main]` - Server and window lifecycle
  - `[audio_engine]` - Audio device and Deepgram connection
  - `[llm_router]` - LLM API calls and errors

### Modified
- `core/llm_router.py`:
  - Added context passing to LLM prompts
  - Added error handling for API calls
  - Added conversational response style

- `web/index.html`:
  - Updated labels from "Q"/"A" to "Interviewer"/"AI"
  - Added CSS for question type indicators
  - Added question type message handling

- `main.py`:
  - Added startup logging throughout
  - Added error handling in broadcast function
  - Improved logging configuration

- `core/audio_engine.py`:
  - Added comprehensive logging
  - Added error handling for device issues

---

## [1.0.0] - 2026-04-24 (Initial Release)

### Added
- Basic audio capture via WASAPI loopback
- Deepgram transcription integration
- Groq and Claude LLM routing
- WebSocket-based UI communication
- Desktop window with transparency controls
- Dark/light theme support
- Basic Q&A history display