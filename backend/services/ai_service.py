import logging
import os
import numpy as np
from openai import OpenAI
from difflib import SequenceMatcher
from dotenv import load_dotenv
from typing import Union, Dict
from hashlib import sha256

# 1. LOAD DOTENV FIRST
load_dotenv()

# 2. INITIALIZE GROQ CLIENT
# Groq is OpenAI-compatible, so we just change the base_url
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise ValueError("❌ Groq API Key not found! Check your .env file.")

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=api_key,
    max_retries=6,  # ride out Groq free-tier rate limits (429) instead of failing
)

REPLY_MODEL = "openai/gpt-oss-120b"

# 3. VECTOR STORE
from backend.utils.knowledge_base import DOCUMENT_SOURCE, get_collection
from backend.services.document_relevance import document_answer_score

logger = logging.getLogger(__name__)
collection = get_collection()


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().strip().split())

AGENT_SOURCES = {"agent_resolution", "agent_turn", "resolved_conversation"}


def analyze_ticket(text: str) -> Dict[str, Union[float, str]]:
    """
    RAG-based analysis using Groq (gpt-oss-120b).

    Seed entries and agent-resolved examples live in the same Chroma collection,
    so one retrieval covers both: once agents resolve an issue, similar queries
    match that example and confidence rises through the similarity score itself.
    """
    results = collection.query(
        query_texts=[text],
        n_results=3
    )

    distances = results['distances'][0]
    similarities = [max(0, 1 - d) for d in distances]

    if not similarities:
        return {"confidence": 0.0, "draft_reply": "No context found."}

    top_similarity = similarities[0]
    mean_similarity = np.mean(similarities)
    confidence = 0.75 * top_similarity + 0.25 * mean_similarity

    metadata_rows = results.get("metadatas", [[]])[0]

    # Uploaded documents are passages, not questions, so similarity alone
    # under-rates them. If a retrieved chunk clearly answers the ticket, let that
    # judgement set confidence; it can only raise it, never lower it.
    document_passages = [
        document
        for document, metadata in zip(results["documents"][0], metadata_rows)
        if isinstance(metadata, dict) and metadata.get("source") == DOCUMENT_SOURCE
    ]
    if document_passages:
        confidence = max(confidence, document_answer_score(text, document_passages))

    confidence = round(float(np.clip(confidence, 0.0, 1.0)), 4)
    context_parts = []
    for metadata in metadata_rows:
        if not isinstance(metadata, dict):
            continue
        text_val = metadata.get("reply") or metadata.get("resolution")
        if not text_val:
            continue
        if metadata.get("source") in AGENT_SOURCES:
            text_val = f"[Agent-resolved example] {text_val}"
        context_parts.append(str(text_val))

    retrieved_context = "\n---\n".join(context_parts) if context_parts else "No context found."

    system_prompt = """You are a friendly technical support assistant.
Be concise, helpful, and human.

Rules:
- Keep total response under 110 words.
- Start with one short empathetic line (natural, not scripted).
- Give clear numbered steps (2-4 max).
- End with one brief check-in line (for example: "Tell me what you see after step 2.").
- Avoid overly formal or robotic phrasing.
- Avoid long explanations, but keep the tone warm.
- If key details are missing, ask at most 2 short clarifying questions.
- Use provided context where relevant.
- Write plain text only: no markdown, bold, or asterisks.
"""

    user_prompt = (
        f"Support ticket:\n{text}\n\n"
        f"Relevant past solutions:\n{retrieved_context}\n\n"
        "Write a pinpoint support reply following the required structure."
    )

    response = client.chat.completions.create(
        model=REPLY_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2
    )

    return {
        "confidence": confidence,
        "draft_reply": response.choices[0].message.content
    }

def store_agent_resolution(original_ticket: str, agent_reply: str, tier: str) -> bool:
    if not original_ticket or not agent_reply:
        return False

    normalized_text = _normalize_text(original_ticket)
    digest = sha256(f"{normalized_text}|{agent_reply}".encode("utf-8")).hexdigest()[:16]
    resolution_id = f"res_{digest}"

    try:
        collection.add(
            documents=[original_ticket],
            metadatas=[
                {
                    "reply": agent_reply,
                    "source": "agent_resolution",
                    "tier": tier,
                }
            ],
            ids=[resolution_id],
        )
        return True
    except Exception:
        return False


def get_vector_update_count() -> int:
    resolution_records = collection.get(where={"source": "agent_resolution"})
    return len(resolution_records.get("ids", []))


def _build_conversation_text(messages: list[dict]) -> str:
    lines: list[str] = []
    for message in messages:
        role = str(message.get("role", "unknown")).upper()
        content = str(message.get("content", "")).strip()
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _generate_conversation_summary(full_conversation_text: str) -> str | None:
    if not full_conversation_text.strip():
        return None

    summary_prompt = f"""
Summarize this support conversation in 2-3 sentences.
Focus on: what the user's issue was, what solution was provided.
Be specific and concrete.

Conversation:
{full_conversation_text}
"""

    try:
        response = client.chat.completions.create(
            model=REPLY_MODEL,
            messages=[
                {"role": "system", "content": "You are a concise support summarizer."},
                {"role": "user", "content": summary_prompt},
            ],
            temperature=0.1,
        )
        summary = response.choices[0].message.content
        if not summary:
            return None
        return summary.strip()
    except Exception:
        return None


def store_resolved_conversation_memory(
    conversation_id: str,
    username: str,
    messages: list[dict],
) -> dict:
    user_messages = [message for message in messages if message.get("role") == "user"]
    summary_written = False
    chunk_writes = 0

    if len(user_messages) >= 2:
        full_conversation_text = _build_conversation_text(messages)
        summary = _generate_conversation_summary(full_conversation_text)
        final_agent_messages = [
            message.get("content", "")
            for message in messages
            if message.get("role") == "agent"
        ]
        final_agent_message = final_agent_messages[-1] if final_agent_messages else ""

        if summary:
            try:
                collection.upsert(
                    documents=[summary],
                    metadatas=[
                        {
                            "type": "conversation_summary",
                            "conversation_id": conversation_id,
                            "username": username,
                            "resolution": final_agent_message,
                            "source": "resolved_conversation",
                        }
                    ],
                    ids=[f"summary_{conversation_id}"],
                )
                summary_written = True
            except Exception:
                summary_written = False

    last_user_message = None
    turn_index = 0
    for message in messages:
        role = message.get("role")

        if role == "user":
            last_user_message = message
            continue

        if role != "agent" or not last_user_message:
            continue

        user_content = str(last_user_message.get("content", "")).strip()
        agent_content = str(message.get("content", "")).strip()
        ai_draft = last_user_message.get("agent_draft_reply")

        if not user_content or not agent_content:
            last_user_message = None
            continue

        if ai_draft:
            similarity = SequenceMatcher(None, str(ai_draft), agent_content).ratio()
            if similarity >= 0.85:
                last_user_message = None
                continue

        turn_index += 1
        chunk_id = f"chunk_{conversation_id}_{turn_index}"
        try:
            collection.upsert(
                documents=[user_content],
                metadatas=[
                    {
                        "type": "turn_chunk",
                        "conversation_id": conversation_id,
                        "reply": agent_content,
                        "source": "agent_turn",
                        "turn_index": turn_index,
                    }
                ],
                ids=[chunk_id],
            )
            chunk_writes += 1
        except Exception:
            pass

        last_user_message = None

    return {
        "summary_written": summary_written,
        "chunk_writes": chunk_writes,
    }