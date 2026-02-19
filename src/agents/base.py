"""
Base agent interface defining the contract for all agents.
"""

from abc import ABC, abstractmethod
from typing import Any
import logging

logger = logging.getLogger(__name__)


class AgentInterface(ABC):
    """Base interface that all agents must implement."""

    def __init__(self, name: str):
        """
        Initialize agent interface.

        Args:
            name: Agent name for logging
        """
        self.name = name
        self.logger = logging.getLogger(f"orchestrator.agent.{name}")

    @abstractmethod
    async def execute(self, task_input: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the agent's main task.

        Args:
            task_input: Input parameters for the agent

        Returns:
            Agent output as dict

        Raises:
            Exception: If agent execution fails
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the agent is healthy and accessible.

        Returns:
            True if healthy, False otherwise
        """
        pass

    async def validate_input(self, task_input: dict[str, Any]) -> bool:
        """
        Validate input parameters.

        Args:
            task_input: Input to validate

        Returns:
            True if valid

        Raises:
            ValueError: If input is invalid
        """
        # Override in subclasses for specific validation
        return True

    def _log_execution(self, task_input: dict[str, Any], result: dict[str, Any]) -> None:
        """Log agent execution for debugging."""
        self.logger.info(
            f"Executed {self.name}",
            extra={
                "agent": self.name,
                "input_keys": list(task_input.keys()),
                "output_keys": list(result.keys()),
            },
        )


class AgentError(Exception):
    """Base exception for agent errors."""

    def __init__(self, agent_name: str, message: str, original_error: Exception | None = None):
        self.agent_name = agent_name
        self.original_error = original_error
        super().__init__(f"[{agent_name}] {message}")


class AgentTimeoutError(AgentError):
    """Raised when agent execution times out."""

    pass


class AgentConnectionError(AgentError):
    """Raised when cannot connect to agent."""

    pass


class AgentValidationError(AgentError):
    """Raised when agent input validation fails."""

    pass


class UnavailableAgentStub(AgentInterface):
    """
    Drop-in stub for agents that couldn't be initialized.

    Returns a clear error result instead of crashing the server.
    Used when agent paths don't exist or imports fail at startup.
    """

    def __init__(self, name: str, reason: str):
        super().__init__(name)
        self.reason = reason
        self.logger.warning(f"Agent '{name}' is unavailable: {reason}")

    async def execute(self, task_input: dict[str, Any]) -> dict[str, Any]:
        raise AgentConnectionError(
            self.name,
            f"Agent unavailable at startup: {self.reason}",
        )

    async def health_check(self) -> bool:
        return False

    def filter_secrets(self, text: str) -> tuple[str, bool]:
        """Passthrough — no filtering when Context Core is unavailable."""
        return text, False
