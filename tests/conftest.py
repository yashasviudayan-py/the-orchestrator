"""
Shared pytest fixtures for The Orchestrator test suite.
"""

import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure project root is in sys.path so `src` is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ─── Redis fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
async def redis_client():
    """
    Real async Redis client using test DB (db=1).
    Skips automatically if Redis is not running.
    """
    try:
        from src.state.redis_client import RedisClient
        client = RedisClient(host="localhost", port=6379, db=1)
        await client.connect()
        yield client
        await client.flushdb()
        await client.disconnect()
    except Exception as e:
        pytest.skip(f"Redis not available: {e}")


@pytest.fixture
async def state_manager(redis_client):
    """StateManager backed by real Redis test DB."""
    from src.state.manager import StateManager
    return StateManager(redis_client, key_prefix="test:", default_ttl=60)


# ─── Mock agent fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def mock_research_agent():
    """Mock ResearchAgentInterface."""
    agent = MagicMock()
    agent.execute = AsyncMock(return_value={
        "topic": "test topic",
        "summary": "Test research summary",
        "content": "Detailed content here",
        "urls": ["https://example.com"],
        "key_findings": ["Finding 1", "Finding 2"],
        "elapsed_ms": 100.0,
        "errors": {},
    })
    agent.health_check = AsyncMock(return_value=True)
    agent.filter_secrets = MagicMock(return_value=("filtered text", False))
    return agent


@pytest.fixture
def mock_context_agent():
    """Mock ContextCoreInterface."""
    agent = MagicMock()
    agent.execute = AsyncMock(return_value={
        "query": "test query",
        "relevant_docs": [],
        "summary": "No prior work found",
        "has_prior_work": False,
        "confidence": 0.0,
    })
    agent.health_check = AsyncMock(return_value=True)
    agent.filter_secrets = MagicMock(return_value=("filtered text", False))
    return agent


@pytest.fixture
def mock_pr_agent():
    """Mock PRAgentInterface."""
    agent = MagicMock()
    agent.execute = AsyncMock(return_value={
        "title": "Test PR",
        "pr_url": "https://github.com/test/repo/pull/1",
        "branch_name": "feature/test",
        "files_changed": ["file.py"],
        "success": True,
        "error": None,
    })
    agent.health_check = AsyncMock(return_value=True)
    return agent


@pytest.fixture
def mock_llm():
    """Mock ChatOllama LLM."""
    llm = MagicMock()
    response = MagicMock()
    response.content = "research"
    llm.ainvoke = AsyncMock(return_value=response)
    return llm
