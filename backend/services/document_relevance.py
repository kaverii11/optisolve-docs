"""
Answer check for uploaded-document chunks.

Seed entries are stored as questions, so a reworded ticket lands close to them in
embedding space. Document chunks are passages, and the same embedding puts a
question noticeably further from a passage even when the passage answers it
(about 0.55-0.75 confidence in local checks, never Tier 1). A cross-encoder reads
the ticket and the passage together and scores whether the passage answers it,
which separates "answers this" from "same topic" far better than cosine distance.

Runs locally on CPU (~90 MB model, downloaded on first use): no Groq calls.
"""
import logging
import threading

import torch
from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)

MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L6-v2"

_model: CrossEncoder | None = None
_model_lock = threading.Lock()


def _get_model() -> CrossEncoder:
    global _model
    with _model_lock:
        if _model is None:
            _model = CrossEncoder(MODEL_NAME)
        return _model


def document_answer_score(ticket_text: str, passages: list[str]) -> float:
    """Highest 0-1 probability that one of the passages answers the ticket."""
    if not passages:
        return 0.0
    scores = _get_model().predict(
        [(ticket_text, passage) for passage in passages],
        activation_fn=torch.nn.Sigmoid(),
    )
    return float(max(scores))
