import os
import sys
import groq as groq_sdk
import anthropic
from dotenv import load_dotenv
from core.context_manager import get_context

load_dotenv()

_GROQ_API_KEY = os.getenv("GROQ_API_KEY")
_ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

print("[llm_router] Initialized", flush=True)

SUMMARY_PROMPT = """
You are reviewing a live interview session for Pavan Reddy, a Principal AI Engineer.
Based on the Q&A pairs below (including what the candidate actually said when available),
produce a concise end-of-session debrief in 4 short sections:

1. KEY THEMES — topics covered in this session
2. STRONG MOMENTS — answers that landed well and why
3. GAPS — questions that could have been answered better
4. NEXT STEPS — 2–3 concrete prep tips for the next round

Be direct and specific. No preamble. Use plain text, no markdown headers.
"""

SYSTEM_PROMPT = """
You are a silent, real-time interview copilot for PAVAN REDDY.

CANDIDATE PROFILE:
- Principal AI Engineer | 6+ years in FinTech, banking, insurance (Zurich NA, Wells Fargo, Fiserv)
- Current/Recent: Senior AI Engineer at Zurich NA — built multi-agent LangChain/LangGraph pipelines on Azure OpenAI (GPT-4o) for insurance underwriting and claims automation
- Key wins: RAG apps with Pinecone/FAISS, self-healing ML pipelines (data drift + latency SLA monitoring), virtual assistant handling 35K+ monthly interactions at 91% resolution, 55% faster deployments via Docker/K8s/Azure DevOps CI/CD
- ML stack: Databricks, MLflow, Delta Lake, PySpark — 500M+ daily records, sub-100ms inference
- Cloud: Azure (primary — Azure AI Studio, Azure ML, Azure OpenAI, AKS, Terraform), AWS
- Frameworks: LangChain, LangGraph, FastAPI, PyTorch, TensorFlow, Hugging Face, Scikit-learn
- Data: FAISS, Pinecone, Chroma, PostgreSQL, MongoDB, Kafka
- Languages: Python, SQL, PySpark, Java, JavaScript
- Education: MS Computer Science — Wilmington University (2023–2024)

INTERVIEWEE PERSONA (IMPORTANT - Follow exactly):
Role: Act as a highly qualified but relatable job candidate in a live interview.
Objective: Answer questions with the nuance, pacing, and structure of a real human, not a list-generating AI.

Guidelines for Responses:
- Avoid Structured Lists: Do not use "Point 1, Point 2, Point 3." Instead, use transition words like "Building on that," "Actually," or "On the flip side."
- Use Natural Phrasing: Incorporate brief conversational openers such as "That's a great question," "I was actually just thinking about this recently," or "To be honest, it took me a trial or two to get this right."
- Inject Soft Skills: Show vulnerability where appropriate (mentioning a past mistake and how you fixed it) and express genuine enthusiasm for the work.
- Length & Pacing: Keep answers concise but meaty. Aim for a "back-and-forth" feel rather than a long lecture.
- The "Human" Hook: End answers by occasionally checking in, like "Does that align with what your team is looking for?" or "I can dive deeper into that specific project if you'd like."
- Constraint: Do not provide meta-commentary or introductory text like "Here is my answer." Start speaking immediately as the candidate.

Example of the Difference:
- Standard LLM Answer: "I have strong communication skills. I am proficient in Python. I enjoy working in teams."
- Human-Style Answer: "You know, I've always found that technical skills only get you halfway there. While I've spent the last four years heavily focused on Python and data architecture, I've realized my real strength is being the 'translator' between the dev team and the stakeholders. There was a project last year where things almost stalled because of a communication gap, and I stepped in to bridge that. I really enjoy that mix of high-level coding and people management."

RESPONSE RULES:
- Give conversational, flowing answers (2-4 sentences max) that sound like natural speech
- Be specific — cite actual tools, numbers, and projects from the profile above
- Never say "follow best practices" or "it depends"
- For agentic AI / LLM / RAG questions → reference Zurich NA work (LangChain, LangGraph, GPT-4o)
- For ML pipelines / data questions → reference Wells Fargo work (Databricks, MLflow, 500M records)
- For backend / API / DevOps questions → reference FastAPI, Docker, AKS, 55% deployment speedup
- For NLP / conversational AI questions → reference the 35K interaction virtual assistant at Wells Fargo
- For governance / compliance → reference regulated FinTech experience and model controls at Zurich NA
- IMPORTANT: Use the conversation context to provide relevant follow-up information when the interviewer asks follow-up or clarification questions
- If CANDIDATE-PROVIDED CONTEXT is present below, prioritize it to give personalized, specific answers
"""


def build_system_prompt() -> str:
    """Build system prompt, prepending any enabled upload context."""
    from core.uploads import build_context_block
    block = build_context_block()
    if block:
        return (
            SYSTEM_PROMPT.strip()
            + "\n\nCANDIDATE-PROVIDED CONTEXT (use this to personalize and ground your answers):\n"
            + block
        )
    return SYSTEM_PROMPT.strip()


async def stream_answer(transcript: str, engine: str) -> None:
    import sys
    broadcast = sys.modules['__main__'].broadcast  # thread-safe sync function
    
    print(f"[llm_router] Processing: '{transcript[:50]}...'", flush=True)
    
    # Get conversation context
    ctx = get_context()
    ctx.add_question(transcript)
    
    # Get question type before processing — must broadcast before answer_done
    q_type = ctx._analyze_question_type()
    print(f"[llm_router] Question type: {q_type.value}", flush=True)
    broadcast({"type": "question_type", "question_type": q_type.value})
    
    # Build messages with context
    context_str = ctx.get_recent_context(count=3)
    
    if context_str:
        user_content = f"""CONVERSATION CONTEXT:
{context_str}

CURRENT QUESTION (Interviewer):
{transcript}"""
    else:
        user_content = transcript

    broadcast({"type": "answer_thinking"})

    if engine == "groq":
        print(f"[llm_router] Calling Groq API...", flush=True)
        client = groq_sdk.AsyncGroq(api_key=_GROQ_API_KEY)
        try:
            stream = await client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": build_system_prompt()},
                    {"role": "user", "content": user_content},
                ],
                stream=True,
            )
            
            full_answer = ""
            async for chunk in stream:
                text = chunk.choices[0].delta.content
                if text is not None:
                    full_answer += text
                    broadcast({"type": "answer_chunk", "text": text})
            print(f"[llm_router] OK Groq response complete", flush=True)
            broadcast({"type": "answer_done"})
            
            # Store the answer in context after streaming completes
            ctx.add_answer(full_answer)
        except Exception as e:
            print(f"[llm_router] ERROR - Groq API failed: {e}", flush=True)
            broadcast({"type": "answer_chunk", "text": f"[Error: {e}]"})
            broadcast({"type": "answer_done"})

    else:  # claude
        print(f"[llm_router] Calling Claude API...", flush=True)
        try:
            full_answer = ""
            async with anthropic.AsyncAnthropic(api_key=_ANTHROPIC_API_KEY).messages.stream(
                model="claude-haiku-4-5-20251001",
                max_tokens=512,
                system=build_system_prompt(),
                messages=[{"role": "user", "content": user_content}],
            ) as stream:
                async for delta in stream.text_stream:
                    full_answer += delta
                    broadcast({"type": "answer_chunk", "text": delta})
            print(f"[llm_router] OK Claude response complete", flush=True)
            broadcast({"type": "answer_done"})
            
            # Store the answer in context after streaming completes
            ctx.add_answer(full_answer)
        except Exception as e:
            print(f"[llm_router] ERROR - Claude API failed: {e}", flush=True)
            broadcast({"type": "answer_chunk", "text": f"[Error: {e}]"})
            broadcast({"type": "answer_done"})


async def summarize_session(engine: str) -> None:
    """Stream an end-of-interview debrief from the full Q&A history."""
    broadcast = sys.modules['__main__'].broadcast
    ctx = get_context()

    broadcast({"type": "summary_start"})

    if not ctx.history:
        broadcast({"type": "answer_chunk", "text": "No session history to summarize yet."})
        broadcast({"type": "answer_done"})
        return

    lines = []
    for i, qa in enumerate(ctx.history, 1):
        lines.append(f"Q{i} [{qa.question_type.value}]: {qa.question}")
        lines.append(f"AI suggested: {qa.answer}")
        if qa.user_answer:
            lines.append(f"Candidate said: {qa.user_answer}")
        lines.append("")
    history_text = "\n".join(lines)

    broadcast({"type": "answer_thinking"})
    print("[llm_router] Generating session summary...", flush=True)

    try:
        if engine == "groq":
            client = groq_sdk.AsyncGroq(api_key=_GROQ_API_KEY)
            stream = await client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": SUMMARY_PROMPT.strip()},
                    {"role": "user", "content": history_text},
                ],
                stream=True,
            )
            async for chunk in stream:
                text = chunk.choices[0].delta.content
                if text is not None:
                    broadcast({"type": "answer_chunk", "text": text})
        else:
            async with anthropic.AsyncAnthropic(api_key=_ANTHROPIC_API_KEY).messages.stream(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                system=SUMMARY_PROMPT.strip(),
                messages=[{"role": "user", "content": history_text}],
            ) as stream:
                async for delta in stream.text_stream:
                    broadcast({"type": "answer_chunk", "text": delta})

        broadcast({"type": "answer_done"})
        print("[llm_router] Session summary complete", flush=True)
    except Exception as e:
        print(f"[llm_router] Summary error: {e}", flush=True)
        broadcast({"type": "answer_chunk", "text": f"[Error generating summary: {e}]"})
        broadcast({"type": "answer_done"})

