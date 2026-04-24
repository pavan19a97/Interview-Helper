import os
import groq as groq_sdk
import anthropic
from dotenv import load_dotenv

load_dotenv()

_GROQ_API_KEY = os.getenv("GROQ_API_KEY")
_ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

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

RESPONSE RULES:
- Give 3-5 bullet points the candidate can glance at and speak naturally
- Every bullet is one sentence, scannable in under 2 seconds
- Be specific — cite actual tools, numbers, and projects from the profile above
- Never say "follow best practices" or "it depends"
- For agentic AI / LLM / RAG questions → reference Zurich NA work (LangChain, LangGraph, GPT-4o)
- For ML pipelines / data questions → reference Wells Fargo work (Databricks, MLflow, 500M records)
- For backend / API / DevOps questions → reference FastAPI, Docker, AKS, 55% deployment speedup
- For NLP / conversational AI questions → reference the 35K interaction virtual assistant at Wells Fargo
- For governance / compliance → reference regulated FinTech experience and model controls at Zurich NA
"""


async def stream_answer(transcript: str, engine: str) -> None:
    import sys
    broadcast = sys.modules['__main__'].broadcast  # thread-safe sync function

    if engine == "groq":
        client = groq_sdk.AsyncGroq(api_key=_GROQ_API_KEY)
        stream = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT.strip()},
                {"role": "user", "content": transcript},
            ],
            stream=True,
        )
        async for chunk in stream:
            text = chunk.choices[0].delta.content
            if text is not None:
                broadcast({"type": "answer_chunk", "text": text})
        broadcast({"type": "answer_done"})

    else:  # claude
        async with anthropic.AsyncAnthropic(api_key=_ANTHROPIC_API_KEY).messages.stream(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=SYSTEM_PROMPT.strip(),
            messages=[{"role": "user", "content": transcript}],
        ) as stream:
            async for delta in stream.text_stream:
                broadcast({"type": "answer_chunk", "text": delta})
        broadcast({"type": "answer_done"})
