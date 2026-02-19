"""
Context Core interface - integrates with Context Core via direct Python imports.
Provides semantic search, RAG chat, and SECRET FILTERING.
"""

import sys
from pathlib import Path
from typing import Any
import logging

from .base import AgentInterface, AgentError

logger = logging.getLogger(__name__)


class ContextCoreInterface(AgentInterface):
    """Interface to Context Core via direct imports."""

    def __init__(self, context_core_path: str):
        """
        Initialize Context Core interface.

        Args:
            context_core_path: Path to Context Core project
        """
        super().__init__("context")
        self.context_core_path = Path(context_core_path)

        # Add Context Core to Python path
        src_path = self.context_core_path / "src"
        if str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))

        # Import Context Core modules
        try:
            from context_core.vault import Vault
            from context_core.search import search_vault
            from context_core.rag import RAGPipeline
            from context_core.security import SecretDetector

            self.Vault = Vault
            self.search_vault = search_vault
            self.RAGPipeline = RAGPipeline
            self.SecretDetector = SecretDetector

            # Initialize vault and detector
            self.vault = Vault()
            self.secret_detector = SecretDetector()

            self.logger.info("Context Core interface initialized successfully")

        except ImportError as e:
            raise AgentError(
                self.name,
                f"Failed to import Context Core from {context_core_path}",
                e,
            )

    async def execute(self, task_input: dict[str, Any]) -> dict[str, Any]:
        """
        Execute context search or chat.

        Args:
            task_input: Must contain either:
                - 'query': str (for search)
                - 'chat_query': str (for RAG chat)
                - 'check_secrets': str (for secret detection)

        Returns:
            Context results dict with:
                - query: str
                - relevant_docs: list[dict]
                - summary: str (if chat)
                - has_prior_work: bool
                - confidence: float

        Raises:
            AgentError: If context operation fails
        """
        try:
            await self.validate_input(task_input)

            # Secret detection (CRITICAL FOR SECURITY)
            if "check_secrets" in task_input:
                return await self._check_secrets(task_input["check_secrets"])

            # Search mode
            if "query" in task_input:
                return await self._search(task_input)

            # Chat/RAG mode
            if "chat_query" in task_input:
                return await self._chat(task_input)

            raise ValueError("Invalid task_input - need 'query', 'chat_query', or 'check_secrets'")

        except Exception as e:
            if isinstance(e, AgentError):
                raise
            raise AgentError(self.name, f"Context operation failed: {str(e)}", e)

    async def _search(self, task_input: dict[str, Any]) -> dict[str, Any]:
        """Perform semantic search."""
        query = task_input["query"]
        n_results = task_input.get("n_results", 10)
        min_similarity = task_input.get("min_similarity", 0.5)

        self.logger.info(f"Searching context for: {query}")

        # Perform search (sync function, but wrapped in async)
        results = self.search_vault(
            self.vault,
            query=query,
            n_results=n_results,
            min_similarity=min_similarity,
        )

        # Convert to dict format
        relevant_docs = [
            {
                "document_id": r.document_id,
                "content": r.content,
                "similarity": r.similarity,
                "metadata": r.metadata,
            }
            for r in results
        ]

        # Check if we have prior work
        has_prior_work = len(relevant_docs) > 0 and relevant_docs[0]["similarity"] > 0.7

        result = {
            "query": query,
            "relevant_docs": relevant_docs,
            "has_prior_work": has_prior_work,
            "confidence": relevant_docs[0]["similarity"] if relevant_docs else 0.0,
        }

        self._log_execution(task_input, result)
        return result

    async def _chat(self, task_input: dict[str, Any]) -> dict[str, Any]:
        """Perform RAG chat."""
        query = task_input["chat_query"]
        model = task_input.get("model", "llama3.1:8b-instruct-q8_0")

        self.logger.info(f"RAG chat query: {query}")

        # Initialize pipeline
        pipeline = self.RAGPipeline(self.vault)

        # Query (sync function)
        response = pipeline.query(query_text=query, model=model)

        # Get relevant docs from vault
        search_results = self.search_vault(self.vault, query=query, n_results=5)

        relevant_docs = [
            {
                "document_id": r.document_id,
                "content": r.content,
                "similarity": r.similarity,
                "metadata": r.metadata,
            }
            for r in search_results
        ]

        result = {
            "query": query,
            "summary": response.content,
            "relevant_docs": relevant_docs,
            "has_prior_work": len(relevant_docs) > 0,
            "confidence": relevant_docs[0]["similarity"] if relevant_docs else 0.0,
        }

        self._log_execution(task_input, result)
        return result

    async def _check_secrets(self, text: str) -> dict[str, Any]:
        """
        Check text for secrets (CRITICAL SECURITY FUNCTION).

        Args:
            text: Text to scan

        Returns:
            Dict with:
                - has_secrets: bool
                - matched_patterns: list[str]
                - descriptions: list[str]
        """
        self.logger.debug("Scanning for secrets")

        scan_result = self.secret_detector.scan(text)

        return {
            "has_secrets": len(scan_result["matched_patterns"]) > 0,
            "matched_patterns": scan_result["matched_patterns"],
            "descriptions": scan_result["descriptions"],
        }

    async def health_check(self) -> bool:
        """Check if Context Core is accessible."""
        try:
            # Try to access vault
            _ = self.vault
            return True
        except Exception as e:
            self.logger.warning(f"Health check failed: {e}")
            return False

    async def validate_input(self, task_input: dict[str, Any]) -> bool:
        """Validate context task input."""
        has_query = "query" in task_input
        has_chat = "chat_query" in task_input
        has_secret_check = "check_secrets" in task_input

        if not (has_query or has_chat or has_secret_check):
            raise ValueError(
                "Context task input must contain 'query', 'chat_query', or 'check_secrets'"
            )

        return True

    def filter_secrets(self, text: str) -> tuple[str, bool]:
        """
        CRITICAL: Filter secrets from text before passing between agents.

        Args:
            text: Text to filter

        Returns:
            Tuple of (filtered_text, had_secrets)
        """
        scan_result = self.secret_detector.scan(text)

        if scan_result["matched_patterns"]:
            self.logger.warning(
                f"Secrets detected: {scan_result['descriptions']}"
            )
            filtered = text
            for secret in scan_result["matched_patterns"]:
                filtered = filtered.replace(secret, "[REDACTED]")
            return filtered, True

        return text, False
