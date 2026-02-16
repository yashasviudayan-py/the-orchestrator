"""Agent interfaces for integrating with external agents."""

from .base import AgentInterface, AgentError, AgentTimeoutError, AgentConnectionError
from .research import ResearchAgentInterface
from .context import ContextCoreInterface
from .pr_agent import PRAgentInterface

__all__ = [
    "AgentInterface",
    "AgentError",
    "AgentTimeoutError",
    "AgentConnectionError",
    "ResearchAgentInterface",
    "ContextCoreInterface",
    "PRAgentInterface",
]
