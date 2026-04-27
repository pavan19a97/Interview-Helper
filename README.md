<div align="center">

# 🎙️ Interview Copilot

### *Your invisible AI companion for live interviews — real-time transcription, instant answers, total stealth.*

[![Python 3.13](https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-0078D4?logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![Deepgram](https://img.shields.io/badge/Deepgram-nova--3-13EF93?logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciLz4=)](https://deepgram.com/)
[![Groq](https://img.shields.io/badge/Groq-LLaMA%203.1-F55036)](https://groq.com/)
[![Claude](https://img.shields.io/badge/Anthropic-Claude%20Haiku-D97757?logo=anthropic&logoColor=white)](https://www.anthropic.com/)
[![Version](https://img.shields.io/badge/version-1.4.0-brightgreen)](https://github.com/pavan19a97/Interview-Helper/releases/tag/v1.4.0)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[**Features**](#-features) • [**Architecture**](#-architecture) • [**Setup Guide**](#-first-time-setup) • [**Tech Stack**](#-tech-stack)

---

</div>

## ✨ Overview

**Interview Copilot** is a Windows desktop overlay that listens to a live interview through your speakers, transcribes the interviewer in real time with Deepgram **nova-3**, and streams human-like answers from **Groq** or **Anthropic Claude** — all in a frameless, always-on-top window that's **invisible to screen capture** (Zoom / Teams / Meet won't see it).

> 💡 Built for the candidate who wants AI co-pilot superpowers without breaking eye contact.

<div align="center">

```
   ┌─────────────────────────────────────────┐
   │  ⚡ Copilot   ⚡Groq  ■□  ◐━━●  ⏱━●━  ●  │
   ├─────────────────────────────────────────┤
   │  CURRENT                                │
   │  Interviewer  Tell me about a time       │
   │               you scaled an ML pipeline │
   │  AI           You know, at Wells Fargo  │
   │               we processed 500M records │
   │               daily on Databricks…      │
   │  You          Yeah, exactly — and the   │
   │               trick was MLflow tracking │
   ├─────────────────────────────────────────┤
   │     [SUMMARIZE]  [CLEAR]                │
   ├─────────────────────────────────────────┤
   │  HISTORY                                │
   │  ──────────────                         │
   │  Q  What's your stack?      ↳Follow-up │
   │  A  Mostly Python, FastAPI…            │
   └─────────────────────────────────────────┘
```

*The overlay sits on top of your meeting window — frameless, draggable, screen-capture invisible.*

</div>

---

## 🎯 Features

<table>
<tr>
<td width="50%" valign="top">

### 🔊 **Dual Audio Capture**
- **Loopback** captures the interviewer's voice via WASAPI
- **Microphone** captures your own responses
- Both stream concurrently, transcribed independently

### ⚡ **Real-Time Transcription**
- Deepgram **nova-3** with smart formatting
- 23 domain keyterms (LangChain, Databricks, Pinecone…)
- Adjustable pause sensitivity (500–3000ms slider)
- KeepAlive frames prevent silence-based disconnects

### 🧠 **Context-Aware Answers**
- Detects **NEW_TOPIC**, **FOLLOW_UP**, **REPHRASED**, **CLARIFICATION**
- Carries last 3 Q&A pairs as context to the LLM
- Records what *you actually said* alongside AI suggestions

</td>
<td width="50%" valign="top">

### 🥷 **Stealth UI**
- Frameless, always-on-top, draggable
- **Screen-capture excluded** via `SetWindowDisplayAffinity`
- Adjustable opacity (10–100%) — see-through when needed
- Dark / Light themes

### 📋 **Session Tools**
- **SUMMARIZE** — end-of-interview debrief (themes, gaps, prep tips)
- **SAVE** — persists full session to `data/sessions/*.json` and clears context
- **CLEAR** — wipes history and resets LLM conversation context
- **📎 DOCS** — upload .txt / .md / .json / .pdf / .docx files as live context
- Persistent settings via `localStorage` (theme, engine, opacity, pause)

### 🔄 **Engine Switching**
- ⚡ **Groq** — `llama-3.1-8b-instant` (fastest)
- 🧠 **Claude** — `claude-haiku-4-5` (highest quality)
- Switch mid-session, no restart

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 🎯 **Sentence Karaoke Highlight**
- Answer text split into sentences after streaming completes
- Active sentence highlighted with green outline + background
- Matched word inside bolded + underlined for pinpoint accuracy
- Fuzzy matching with Levenshtein distance (tolerates ASR errors)
- Stem + filler removal (`um`, `uh`, `like`…) before matching
- Contraction expansion (`don't` → `do not`) for better recall
- Distance penalty prevents multi-sentence jumps on weak evidence
- Look-ahead auto-advance: pre-jumps to next sentence when within last ~5 words
- Active sentence always scrolls to **center** of the answer view

</td>
<td width="50%" valign="top">

### 🔒 **Reliability & Stealth**
- Thread-safe `Settings` class (`RLock`) — no race conditions under load
- Fire-and-forget LLM tasks keep Deepgram receive loop unblocked
- Dual Deepgram health banner — tracks loopback + mic independently
- Audio queue drop counter logs upstream lag visibility
- Mute clears in-flight transcript buffer (no stale partials after unmute)
- `You` row clamped to ~2 lines, auto-scrolls to show latest speech
- Question-type tagging in history (`↳ Follow-up`, `↻ Rephrased`, `? Clarify`)

</td>
</tr>
</table>

---

## 🏗️ Architecture

```mermaid
flowchart LR
    subgraph "Audio Sources"
        SPK[🔊 System Audio<br/>WASAPI Loopback]
        MIC[🎤 Microphone<br/>WASAPI Input]
    end

    subgraph "Audio Engine — daemon thread"
        LOOP[run]
        MICR[run_mic]
    end

    subgraph "Deepgram nova-3"
        DG1[WS Stream 1<br/>+ keyterms]
        DG2[WS Stream 2<br/>+ keyterms]
    end

    subgraph "Backend"
        CTX[ConversationContext<br/>Q-type analyzer]
        LLM[llm_router<br/>Groq / Claude]
    end

    subgraph "FastAPI"
        WS[WebSocket /ws/ui<br/>broadcast]
    end

    subgraph "pywebview UI"
        UI[index.html<br/>frameless overlay]
    end

    SPK --> LOOP --> DG1 -->|UtteranceEnd| LLM
    MIC --> MICR --> DG2 -->|user_speech| CTX
    LLM --> CTX
    LLM -->|stream chunks| WS
    CTX --> LLM
    DG1 -->|transcript| WS
    DG2 -->|mic_transcript| WS
    WS -->|JSON over WS| UI
    UI -->|set_engine, set_uend, summarize, reset| WS

    style LOOP fill:#a8ff78,color:#000
    style MICR fill:#64b5f6,color:#000
    style LLM fill:#ffaa00,color:#000
    style UI fill:#1a1a1a,color:#a8ff78
```

### Threading Model

| Thread | Purpose | Event Loop |
|--------|---------|-----------|
| **Main (STA COM)** | pywebview window | n/a — blocks on `webview.start()` |
| **Daemon — uvicorn** | FastAPI WebSocket | ProactorEventLoop |
| **Daemon — audio** | Loopback + Mic capture | SelectorEventLoop *(Python 3.13 fix)* |

> Cross-thread `broadcast()` uses `asyncio.run_coroutine_threadsafe` against the captured uvicorn loop — no shared state hazards.

---

## 🚀 First-Time Setup

> **Estimated time: 10–15 minutes.** You'll need a Windows PC with internet access and about 500 MB of free disk space (for Python, dependencies, and the embedding model that downloads on first doc upload).

---

### Step 1 — System Requirements

| Requirement | Details |
|-------------|---------|
| **OS** | Windows 10 (build 1903+) or Windows 11 — WASAPI loopback is Windows-only |
| **Python** | 3.11 or later (3.13+ recommended) — [download here](https://www.python.org/downloads/) |
| **Audio** | A working speaker/headphone output (for loopback capture) and optionally a microphone |
| **Network** | Internet connection for Deepgram, Groq, and Anthropic API calls |

> [!NOTE]
> During Python installation, **check "Add Python to PATH"** — the app is launched from the command line.

---

### Step 2 — Clone & Install Dependencies

Open **PowerShell** or **Command Prompt** and run:

```bash
# Clone the repository
git clone https://github.com/pavan19a97/Interview-Helper.git
cd Interview-Helper

# (Recommended) Create a virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install all dependencies
pip install -r requirements.txt
```

<details>
<summary><b>What gets installed?</b></summary>

| Package | Purpose |
|---------|---------|
| `fastapi` + `uvicorn` | Local WebSocket server |
| `pywebview` | Desktop window (Edge WebView2) |
| `pyaudiowpatch` | WASAPI loopback + mic audio capture |
| `websockets` | Deepgram streaming connection |
| `groq` | Groq LLM SDK |
| `anthropic` | Anthropic Claude SDK |
| `python-dotenv` | `.env` file loading |
| `pypdf` + `python-docx` | Document text extraction |
| `python-multipart` | File upload support |
| `chromadb` | Local vector database for document context |

</details>

---

### Step 3 — Get Your API Keys

You need **at least two** API keys to run the app. Copy the example file first:

```bash
copy .env.example .env
```

Then open `.env` in any text editor and replace the placeholder values:

```env
DEEPGRAM_API_KEY=your_deepgram_api_key_here
GROQ_API_KEY=your_groq_api_key_here
# Optional — only needed if you want to use the Claude engine
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

Here's where to get each key:

#### 🟢 Deepgram (Required — powers transcription)
1. Go to [console.deepgram.com](https://console.deepgram.com/) and create a free account
2. Navigate to **API Keys** in the left sidebar
3. Click **Create a New API Key**, give it a name, and copy the key
4. Free tier includes **$200 in credit** — more than enough for testing

#### 🟠 Groq (Required — default LLM engine)
1. Go to [console.groq.com](https://console.groq.com/) and sign up
2. Click **API Keys** → **Create API Key**
3. Copy the key (starts with `gsk_`)
4. Free tier with generous rate limits — no credit card needed

#### 🟣 Anthropic (Optional — higher quality answers)
1. Go to [console.anthropic.com](https://console.anthropic.com/) and create an account
2. Navigate to **API Keys** → **Create Key**
3. Copy the key (starts with `sk-ant-`)
4. Pay-as-you-go pricing — you only need this if you want to switch to Claude mid-session

> [!IMPORTANT]
> The app works with **just Deepgram + Groq** (both free). The Anthropic key is optional — if omitted, the Claude engine toggle will show an error when selected, but Groq will work fine.

---

### Step 4 — Configure Your Audio

The app captures audio from two sources:

| Source | What it captures | How it works |
|--------|-----------------|--------------|
| **System Audio (Loopback)** | The interviewer's voice from Zoom/Teams/Meet | Captures whatever plays through your default speakers/headphones |
| **Microphone** | Your own voice (for the "You said" track) | Uses your default Windows microphone |

**Before running the app:**

1. Open **Settings → System → Sound**
2. Make sure your **Output** device is set to the speakers/headphones you'll use during the interview
3. Make sure your **Input** device is set to your microphone
4. Play some audio (e.g., a YouTube video) to verify your speakers are working — the loopback only captures what you can hear

> [!TIP]
> If you're using a Bluetooth headset, make sure it's connected **before** launching the app — the audio device is selected at startup.

---

### Step 5 — Personalize (Important!)

The AI answers are tailored to a specific candidate profile. **You must update this to match your own background**, otherwise the AI will answer as someone else.

**Edit `core/llm_router.py`** and find the `SYSTEM_PROMPT` variable (around line 33). Replace the `CANDIDATE PROFILE` section with your own:

```python
SYSTEM_PROMPT = """
You are a silent, real-time interview copilot for YOUR NAME HERE.

CANDIDATE PROFILE:
- Your title | X years experience in your domains
- Current role: Your current role — what you built/led
- Key wins: Your measurable achievements
- Tech stack: Your tools and frameworks
- Cloud: Your cloud platforms
- Education: Your degree(s)
...
"""
```

**Also update `config/keyterms.json`** with domain terms relevant to your field. These are sent to Deepgram for better proper-noun recognition:

```json
{
  "keyterms": [
    "YourFramework", "YourCompany", "YourTools"
  ],
  "postprocess": {
    "Mis Heard Term": "CorrectTerm"
  }
}
```

---

### Step 6 — Run the App

```bash
python main.py
```

**What happens on first launch:**

1. The terminal prints startup logs — watch for `[main] OK` messages
2. A frameless, dark overlay window appears on your screen
3. The status dot in the top-right of the overlay turns **🟢 green** when Deepgram connects
4. If you upload documents (📎 button), the first upload triggers a one-time **~80 MB embedding model download** — this takes 30–60 seconds

**Expected terminal output on a healthy start:**

```
[main] Starting Interview Helper...
[main] Finding free port...
[main] Using port: 54321
[main] Starting uvicorn server...
[main] OK Server started
[main] Creating webview window...
[main] OK Window created
[main] Starting audio thread...
[main] Starting webview...
[audio_engine] Initializing...
[audio_engine] Opening audio stream...
[audio_engine] Found loopback: device 5, 48000Hz, 2ch
[audio_engine] OK Audio stream started successfully
[audio_engine] OK Connected to Deepgram (Token 48000Hz/2ch)
[mic_engine] OK Mic stream started: 48000Hz, 1ch
[mic_engine] OK Connected to Deepgram (Token 48000Hz/1ch)
```

---

### Step 7 — Verify Everything Works

Use this checklist to confirm the app is running correctly:

- [ ] **Status dot is green** — Deepgram connection is live
- [ ] **Play audio** through your speakers → the **Interviewer** row should show transcription
- [ ] **Speak into your mic** → the **You** row should show your speech
- [ ] **Ask a question aloud** (play a YouTube interview question) → after a pause, the **AI** row should stream an answer
- [ ] **Toggle the engine** (⚡ button) — should switch between Groq and Claude
- [ ] **Adjust opacity slider** — window should become more/less transparent
- [ ] **Drag the window** from the dark header area

> [!WARNING]
> If the status dot stays **🔴 red**, check the terminal for errors. Common causes:
> - Invalid `DEEPGRAM_API_KEY` in `.env`
> - No internet connection
> - Firewall blocking WebSocket connections to `api.deepgram.com`

---

### Quick Reference — Keyboard-Free Controls

Once the app is running, everything is controlled from the overlay UI:

| Control | Location | Function |
|---------|----------|----------|
| ⚡ Engine toggle | Header | Switch Groq ↔ Claude |
| ■ □ Theme | Header | Dark / Light mode |
| Opacity slider | Header | 10–100% window transparency |
| Pause slider | Header | 500–3000ms silence before LLM fires |
| 🔴/🟢 Dot | Header | Connection status |
| ─ | Header | Minimize |
| ✕ | Header | Close app |
| SUMMARIZE | Below current Q&A | End-of-session debrief |
| SAVE | Below current Q&A | Save session to `data/sessions/` |
| CLEAR | Below current Q&A | Wipe history & reset context |
| 📎 DOCS | Below current Q&A | Upload context docs (PDF, DOCX, TXT, MD, JSON) |

The overlay is **invisible to screen capture** — Zoom, Teams, Meet, and OBS will not see it.

---

## 🛠️ Tech Stack

<div align="center">

| Layer | Technology |
|-------|-----------|
| **UI** | `pywebview` + HTML/CSS/JS — Edge WebView2 on Windows |
| **Server** | `FastAPI` + `uvicorn` over WebSocket |
| **Audio** | `pyaudiowpatch` for WASAPI loopback + mic |
| **STT** | `Deepgram nova-3` streaming WebSocket API |
| **LLM** | `groq` SDK (LLaMA 3.1) · `anthropic` SDK (Claude Haiku 4.5) |
| **Stealth** | Win32 `SetWindowDisplayAffinity` + `LWA_ALPHA` |

</div>

---

## 📂 Project Structure

```
Interview-Helper/
├── 🐍 main.py                  # Entry point — pywebview + FastAPI + threads
├── 📁 core/
│   ├── audio_engine.py        # WASAPI loopback + mic + Deepgram streaming
│   ├── llm_router.py          # Groq + Claude streaming, summarize_session
│   └── context_manager.py     # Q-type analyzer, conversation history
├── 📁 web/
│   └── index.html             # Frameless overlay UI (HTML/CSS/JS)
├── 📄 requirements.txt
├── 📄 .env                    # API keys (not committed)
├── 📋 CHANGELOG.md
└── 📖 README.md
```

---

## 🧪 How It Works

### 1️⃣ Audio capture
Two `pyaudio` streams run in parallel:
- **Loopback** grabs anything playing through your speakers (the interviewer on a call)
- **Microphone** grabs your own voice for the "You said" track

### 2️⃣ Transcription
Each stream pipes raw PCM into a Deepgram WebSocket. Interim results paint the UI in real time; an `UtteranceEnd` event marks the end of a thought.

### 3️⃣ Context analysis
When the interviewer's utterance ends, `ConversationContext._analyze_question_type()` decides: is this a *new topic*, a *follow-up*, a *rephrase*, or a *clarification*? The label colors the question in the UI and informs the prompt.

### 4️⃣ LLM streaming
The transcript + last 3 Q&A pairs of context get fed to the chosen engine. Tokens stream back over the WebSocket and paint the AI row character-by-character.

### 5️⃣ Sentence karaoke highlight
Once the answer finishes streaming, it's split into sentence spans. As you speak your reply, the mic transcript is normalized (stems, filler removal, contraction expansion) and fuzzy-matched against each sentence using sliding-window Jaccard similarity with Levenshtein word tolerance. The matching sentence gets a green outline + background; the matched word gets bold + underline. A distance penalty prevents jumps of 2+ sentences unless confidence is high. When you're within ~5 words of finishing a sentence, the highlight pre-advances to the next one.

### 6️⃣ Session debrief
Hit **SUMMARIZE** at the end — the entire session (questions, AI suggestions, what you actually said) goes to the LLM and you get a 4-section debrief: themes, strong moments, gaps, and prep tips for next time.

---

## 🎨 Customization

Edit `core/llm_router.py` to swap the candidate profile in `SYSTEM_PROMPT` for your own background. The current profile targets a **Principal AI Engineer** with FinTech experience.

Add your domain terms to `_DG_KEYWORDS` in `core/audio_engine.py` for better proper-noun recognition (frameworks, tools, company names).

---

## 🔒 Privacy & Stealth

- **Screen capture exclusion** — `SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)` makes the window invisible to OBS, Zoom share, Teams share, screenshot tools
- **No telemetry** — all data flows directly: your machine ⇄ Deepgram ⇄ Groq/Anthropic
- **No persistence** — transcripts and Q&A pairs live only in memory; CLEAR wipes them

> ⚠️ Use responsibly. Many companies prohibit AI assistance during interviews — check the rules of the company you're interviewing with.

---

## 🐛 Troubleshooting

<details>
<summary><b>The Interviewer row stays empty</b></summary>

- Check the status dot — if 🔴, the WebSocket isn't connected
- Look for a red **Deepgram offline** banner — likely an API key issue
- Verify audio is actually playing through your default speakers (loopback only catches what you can hear)

</details>

<details>
<summary><b>The AI never answers</b></summary>

- The terminal will show `[llm_router] ERROR — ...` on API failures — check your Groq / Anthropic key
- The default trigger is any non-empty utterance, but very short interim transcripts (1–2 words) won't trigger until UtteranceEnd fires after `utterance_end_ms` of silence

</details>

<details>
<summary><b>Mic stream not capturing</b></summary>

- The terminal prints `[mic_engine] No mic found, skipping` if no default WASAPI input is set
- Set a default microphone in **Settings → System → Sound → Input**

</details>

<details>
<summary><b>Window won't drag / resize</b></summary>

- Drag from the dark header (avoid the controls)
- Resize from the dotted grip in the bottom-right corner

</details>

---

## 🗺️ Roadmap

- [ ] Session export to Markdown
- [ ] Hotkey to toggle visibility
- [ ] Custom prompt templates per role (PM / Eng / DS)
- [ ] Multi-language support
- [ ] Audio device selector in UI
- [ ] Cross-platform (macOS via CoreAudio)

---

## 📄 License

MIT — do whatever you want, but a star ⭐ is appreciated.

---

<div align="center">

**Built with ❤️ for the candidate who refuses to be caught off-guard.**

[Report Bug](https://github.com/pavan19a97/Interview-Helper/issues) · [Request Feature](https://github.com/pavan19a97/Interview-Helper/issues)

</div>
