"""
Enhanced Supervisor - Intelligent routing with multiple strategies.

The supervisor analyzes task state and decides optimal agent routing using
sophisticated strategies and Ollama-powered decision making.
"""

import logging
from enum import Enum
from typing import Optional, List
from dataclasses import dataclass

from langchain_ollama import ChatOllama

from ..state.schemas import TaskState, AgentType
from .summarizer import ContextSummarizer

logger = logging.getLogger(__name__)


class RoutingStrategy(str, Enum):
    """Available routing strategies."""

    RESEARCH_FIRST = "research_first"  # Always start with research
    CONTEXT_FIRST = "context_first"  # Check context before research
    ADAPTIVE = "adaptive"  # LLM decides based on objective
    PARALLEL = "parallel"  # Call multiple agents in parallel (future)


@dataclass
class RoutingDecision:
    """Routing decision with reasoning."""

    next_agent: Optional[AgentType]
    strategy_used: RoutingStrategy
    reasoning: str
    confidence: float
    alternative_agents: List[AgentType]


class EnhancedSupervisor:
    """
    Intelligent supervisor for agent orchestration.

    Implements multiple routing strategies and learns from execution history.
    """

    def __init__(
        self,
        llm: ChatOllama,
        summarizer: ContextSummarizer,
        default_strategy: RoutingStrategy = RoutingStrategy.ADAPTIVE,
    ):
        """
        Initialize supervisor.

        Args:
            llm: Ollama LLM for decisions
            summarizer: Context summarizer
            default_strategy: Default routing strategy
        """
        self.llm = llm
        self.summarizer = summarizer
        self.default_strategy = default_strategy

        # Decision history for learning
        self.decision_history: List[RoutingDecision] = []

    async def decide_initial_route(
        self,
        objective: str,
        strategy: Optional[RoutingStrategy] = None,
    ) -> RoutingDecision:
        """
        Decide which agent to call first.

        Args:
            objective: Task objective
            strategy: Optional override strategy

        Returns:
            Routing decision
        """
        strategy = strategy or self.default_strategy

        logger.info(f"Deciding initial route using {strategy.value}")

        if strategy == RoutingStrategy.RESEARCH_FIRST:
            return self._research_first_strategy(objective)

        elif strategy == RoutingStrategy.CONTEXT_FIRST:
            return self._context_first_strategy(objective)

        elif strategy == RoutingStrategy.ADAPTIVE:
            return await self._adaptive_strategy(objective)

        else:
            # Default to research
            return self._research_first_strategy(objective)

    def _research_first_strategy(self, objective: str) -> RoutingDecision:
        """Always start with research - good for new features."""
        return RoutingDecision(
            next_agent=AgentType.RESEARCH,
            strategy_used=RoutingStrategy.RESEARCH_FIRST,
            reasoning="New feature - start with research to find best practices",
            confidence=1.0,
            alternative_agents=[AgentType.CONTEXT, AgentType.PR],
        )

    def _context_first_strategy(self, objective: str) -> RoutingDecision:
        """Start with context - good for similar past work."""
        return RoutingDecision(
            next_agent=AgentType.CONTEXT,
            strategy_used=RoutingStrategy.CONTEXT_FIRST,
            reasoning="Check if similar work exists in context before researching",
            confidence=1.0,
            alternative_agents=[AgentType.RESEARCH, AgentType.PR],
        )

    async def _adaptive_strategy(self, objective: str) -> RoutingDecision:
        """
        Use LLM to decide best first agent based on objective.
        """
        prompt = f"""Analyze this software development task and determine the BEST first agent to call.

Task: {objective}

Available agents:
1. RESEARCH - Find best practices, design patterns, and implementation approaches
   - Best for: New features, unfamiliar technologies, need for external knowledge
   - Example: "Add OAuth authentication" → research OAuth best practices first

2. CONTEXT - Search codebase history and prior work
   - Best for: Similar past features, code refactoring, existing patterns
   - Example: "Update login flow" → check how we did login before

3. PR - Directly write code and create pull request
   - Best for: Simple changes, bug fixes, well-defined small tasks
   - Example: "Fix typo in button text" → just do it

Analyze the task and respond with ONLY the agent name: RESEARCH, CONTEXT, or PR

Consider:
- Is this new functionality or modifying existing code?
- Does it require external knowledge or pattern examples?
- Is it simple enough to implement directly?

Agent:"""

        try:
            response = await self.llm.ainvoke(prompt)
            decision = response.content.strip().upper()

            # Map to AgentType
            agent_map = {
                "RESEARCH": AgentType.RESEARCH,
                "CONTEXT": AgentType.CONTEXT,
                "PR": AgentType.PR,
            }

            next_agent = agent_map.get(decision, AgentType.RESEARCH)

            # Get reasoning
            reasoning = await self._get_reasoning(objective, next_agent)

            return RoutingDecision(
                next_agent=next_agent,
                strategy_used=RoutingStrategy.ADAPTIVE,
                reasoning=reasoning,
                confidence=0.8,  # LLM decision has some uncertainty
                alternative_agents=[a for a in AgentType if a != next_agent],
            )

        except Exception as e:
            logger.error(f"Adaptive strategy failed: {e}, falling back to research")
            return self._research_first_strategy(objective)

    async def decide_next_route(
        self,
        state: TaskState,
    ) -> RoutingDecision:
        """
        Decide next agent based on current state.

        Args:
            state: Current task state

        Returns:
            Routing decision
        """
        logger.info(f"Deciding next route (iteration {state.iteration})")

        # Safety checks
        if state.iteration >= state.max_iterations:
            return RoutingDecision(
                next_agent=None,
                strategy_used=self.default_strategy,
                reasoning=f"Max iterations ({state.max_iterations}) reached",
                confidence=1.0,
                alternative_agents=[],
            )

        if len(state.errors) >= state.max_retries:
            return RoutingDecision(
                next_agent=None,
                strategy_used=self.default_strategy,
                reasoning=f"Max errors ({state.max_retries}) reached",
                confidence=1.0,
                alternative_agents=[],
            )

        # Build state summary for LLM
        state_summary = await self.summarizer.summarize_task_state(state)

        # Use LLM to decide next agent
        prompt = f"""Given the current task progress, decide the next agent to call or if task is complete.

{state_summary}

Decision Logic:
- If PR successful → DONE
- If research not done and needed → RESEARCH
- If context not checked and could help → CONTEXT
- If ready to implement → PR
- If errors in agent and retries available → retry that agent
- If stuck or max iterations near → DONE

Respond with ONLY: RESEARCH, CONTEXT, PR, or DONE

Next:"""

        try:
            response = await self.llm.ainvoke(prompt)
            decision = response.content.strip().upper()

            if decision == "DONE":
                next_agent = None
                reasoning = "Task complete or should finalize"
            else:
                agent_map = {
                    "RESEARCH": AgentType.RESEARCH,
                    "CONTEXT": AgentType.CONTEXT,
                    "PR": AgentType.PR,
                }
                next_agent = agent_map.get(decision, None)
                reasoning = await self._get_next_reasoning(state, next_agent)

            decision_obj = RoutingDecision(
                next_agent=next_agent,
                strategy_used=RoutingStrategy.ADAPTIVE,
                reasoning=reasoning,
                confidence=0.75,
                alternative_agents=[],
            )

            # Record decision
            self.decision_history.append(decision_obj)

            return decision_obj

        except Exception as e:
            logger.error(f"Next route decision failed: {e}")
            return RoutingDecision(
                next_agent=None,
                strategy_used=self.default_strategy,
                reasoning=f"Decision error: {str(e)}",
                confidence=0.0,
                alternative_agents=[],
            )

    async def _get_reasoning(
        self,
        objective: str,
        agent: AgentType,
    ) -> str:
        """Get reasoning for agent choice."""
        reasons = {
            AgentType.RESEARCH: f"Research best practices for: {objective}",
            AgentType.CONTEXT: f"Check codebase for similar implementations",
            AgentType.PR: f"Simple task - implement directly",
        }
        return reasons.get(agent, "Routing decision")

    async def _get_next_reasoning(
        self,
        state: TaskState,
        next_agent: Optional[AgentType],
    ) -> str:
        """Get reasoning for next agent choice."""
        if next_agent is None:
            if state.pr_results and state.pr_results.success:
                return "PR created successfully - task complete"
            else:
                return "Unable to complete task - finalizing with current state"

        if next_agent == AgentType.RESEARCH and not state.research_results:
            return "Need research findings before proceeding"

        if next_agent == AgentType.CONTEXT and not state.context_results:
            return "Check for prior work and patterns"

        if next_agent == AgentType.PR:
            return "Ready to implement with available context"

        return f"Routing to {next_agent.value}"

    def get_decision_history(self) -> List[RoutingDecision]:
        """Get history of routing decisions."""
        return self.decision_history.copy()

    def clear_history(self) -> None:
        """Clear decision history."""
        self.decision_history.clear()

    async def should_retry(
        self,
        state: TaskState,
        failed_agent: AgentType,
    ) -> bool:
        """
        Determine if failed agent should be retried.

        Args:
            state: Current task state
            failed_agent: Agent that failed

        Returns:
            True if should retry
        """
        # Check retry count
        if state.retry_count >= state.max_retries:
            logger.warning(f"Max retries reached for {failed_agent}")
            return False

        # Check if error is retryable
        if state.errors:
            last_error = state.errors[-1].lower()

            # Don't retry validation errors
            if "validation" in last_error or "invalid input" in last_error:
                return False

            # Retry connection/timeout errors
            if any(x in last_error for x in ["timeout", "connection", "unavailable"]):
                logger.info(f"Retryable error detected for {failed_agent}")
                return True

        return True
