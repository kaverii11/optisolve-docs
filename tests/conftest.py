import os
import shutil
import tempfile

# Must run before any backend import: knowledge_base opens Chroma and ai_service
# reads the Groq key at import time. setdefault would let a real key leak in from
# the shell, so both are forced.
_CHROMA_DIR = tempfile.mkdtemp(prefix="optisolve-test-chroma-")
os.environ["CHROMA_DB_PATH"] = _CHROMA_DIR
os.environ["GROQ_API_KEY"] = "test-key-not-used"

from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402
from backend.services import ai_service  # noqa: E402
from backend.utils.knowledge_base import get_collection, seed_knowledge_base  # noqa: E402


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_CHROMA_DIR, ignore_errors=True)


@pytest.fixture(scope="session")
def client():
    seed_knowledge_base()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def collection():
    return get_collection()


@pytest.fixture
def captured_llm_calls(monkeypatch):
    """Replace the Groq chat call so analyze_ticket runs its real retrieval
    without spending free-tier quota; returns the prompts it would have sent."""
    calls = []

    def fake_create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="stub reply"))]
        )

    monkeypatch.setattr(ai_service.client.chat.completions, "create", fake_create)
    return calls
