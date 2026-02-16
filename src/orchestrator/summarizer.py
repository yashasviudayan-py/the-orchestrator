"""
Context Summarization Module - Critical for managing context window.

Summarizes agent outputs before passing to next agent to prevent context overflow.
Uses Ollama to intelligently compress information while preserving key details.
"""

import logging
from typing import Any, Optional

from langchain_ollama import ChatOllama

from ..state.schemas import TaskState, ResearchResult, ContextResult, PRResult

logger = logging.getLogger(__name__)


class ContextSummarizer:
    """Intelligent context summarization using Ollama."""

    def __init__(
        self,
        llm: ChatOllama,
        max_summary_tokens: int = 500,
    ):
        """
        Initialize summarizer.

        Args:
            llm: Ollama LLM instance
            max_summary_tokens: Maximum tokens for summaries
        """
        self.llm = llm
        self.max_summary_tokens = max_summary_tokens

    async def summarize_research_results(
        self,
        research: ResearchResult,
        objective: str,
    ) -> str:
        """
        Summarize research results for passing to next agent.

        Args:
            research: Research results
            objective: Original task objective

        Returns:
            Concise summary
        """
        logger.info("Summarizing research results")

        prompt = f"""Summarize these research findings concisely for use in {objective}.

Research Topic: {research.topic}

Summary: {research.summary if research.summary else 'N/A'}

Key Findings:
{chr(10).join(f'- {finding}' for finding in research.key_findings[:5])}

URLs Found: {len(research.urls)}

Create a concise summary (max 300 words) focusing on:
1. Most relevant findings for the objective
2. Recommended approach
3. Key considerations

Summary:"""

        try:
            response = await self.llm.ainvoke(prompt)
            summary = response.content.strip()

            logger.debug(f"Research summary: {len(summary)} chars")
            return summary

        except Exception as e:
            logger.error(f"Failed to summarize research: {e}")
            # Fallback to truncated original
            return (research.summary or "")[:500]

    async def summarize_context_results(
        self,
        context: ContextResult,
        objective: str,
    ) -> str:
        """
        Summarize context search results.

        Args:
            context: Context search results
            objective: Original task objective

        Returns:
            Concise summary
        """
        logger.info("Summarizing context results")

        # Extract relevant doc snippets
        doc_snippets = []
        for doc in context.relevant_docs[:3]:  # Top 3 most relevant
            content = doc.get("content", "")[:200]  # First 200 chars
            similarity = doc.get("similarity", 0.0)
            doc_snippets.append(f"[{similarity:.2f}] {content}")

        docs_text = "\n\n".join(doc_snippets) if doc_snippets else "No relevant docs found"

        prompt = f"""Summarize the context found for: {objective}

Prior Work Found: {'Yes' if context.has_prior_work else 'No'}
Confidence: {context.confidence:.2f}

Relevant Documents:
{docs_text}

Create a brief summary (max 200 words) highlighting:
1. Whether similar work exists
2. Key patterns or approaches found
3. Recommendations based on context

Summary:"""

        try:
            response = await self.llm.ainvoke(prompt)
            summary = response.content.strip()

            logger.debug(f"Context summary: {len(summary)} chars")
            return summary

        except Exception as e:
            logger.error(f"Failed to summarize context: {e}")
            # Fallback
            return f"Prior work: {context.has_prior_work}, Confidence: {context.confidence:.2f}"

    async def summarize_task_state(
        self,
        state: TaskState,
    ) -> str:
        """
        Create a comprehensive summary of current task state.

        Args:
            state: Current task state

        Returns:
            Summary suitable for routing decisions
        """
        logger.info(f"Summarizing task state (iteration {state.iteration})")

        parts = []

        # Objective
        parts.append(f"Objective: {state.objective}")

        # Status
        parts.append(f"Status: {state.status.value}")
        parts.append(f"Iteration: {state.iteration}/{state.max_iterations}")

        # Agents called
        if state.agents_called:
            agents = ", ".join([a.value for a in state.agents_called])
            parts.append(f"Agents called: {agents}")

        # Research summary
        if state.research_results:
            parts.append(
                f"\nResearch: {len(state.research_results.key_findings)} findings, "
                f"{len(state.research_results.urls)} URLs"
            )
            if state.research_results.key_findings:
                parts.append(f"Top finding: {state.research_results.key_findings[0][:100]}")

        # Context summary
        if state.context_results:
            parts.append(
                f"\nContext: {len(state.context_results.relevant_docs)} docs, "
                f"Prior work: {state.context_results.has_prior_work}, "
                f"Confidence: {state.context_results.confidence:.2f}"
            )

        # PR summary
        if state.pr_results:
            parts.append(
                f"\nPR: {'✓' if state.pr_results.success else '✗'}, "
                f"Files: {len(state.pr_results.files_changed)}"
            )
            if state.pr_results.pr_url:
                parts.append(f"URL: {state.pr_results.pr_url}")

        # Errors
        if state.errors:
            parts.append(f"\nErrors: {len(state.errors)}")
            parts.append(f"Latest: {state.errors[-1][:100]}")

        return "\n".join(parts)

    async def create_agent_context(
        self,
        state: TaskState,
        target_agent: str,
    ) -> dict[str, Any]:
        """
        Create optimized context for a specific agent.

        Args:
            state: Current task state
            target_agent: Agent that will receive this context

        Returns:
            Optimized context dict
        """
        logger.info(f"Creating context for {target_agent}")

        context = {
            "objective": state.objective,
            "iteration": state.iteration,
        }

        # Tailor context based on target agent
        if target_agent == "research":
            # Research agent needs minimal context - just the objective
            context["focus"] = "Find best practices and implementation patterns"

        elif target_agent == "context":
            # Context agent needs to know what research found
            if state.research_results:
                summary = await self.summarize_research_results(
                    state.research_results,
                    state.objective,
                )
                context["research_findings"] = summary

        elif target_agent == "pr":
            # PR agent needs both research and context
            summaries = []

            if state.research_results:
                research_summary = await self.summarize_research_results(
                    state.research_results,
                    state.objective,
                )
                summaries.append(f"Research Findings:\n{research_summary}")

            if state.context_results:
                context_summary = await self.summarize_context_results(
                    state.context_results,
                    state.objective,
                )
                summaries.append(f"Context & Prior Work:\n{context_summary}")

            context["background"] = "\n\n".join(summaries)

        return context

    async def estimate_token_count(self, text: str) -> int:
        """
        Estimate token count for text.

        Args:
            text: Text to estimate

        Returns:
            Approximate token count (rough estimate: 1 token ≈ 4 chars)
        """
        return len(text) // 4

    async def should_summarize(self, text: str) -> bool:
        """
        Determine if text should be summarized.

        Args:
            text: Text to check

        Returns:
            True if text exceeds threshold
        """
        estimated_tokens = await self.estimate_token_count(text)
        return estimated_tokens > self.max_summary_tokens
