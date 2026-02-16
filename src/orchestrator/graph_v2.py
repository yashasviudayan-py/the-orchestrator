"""
Phase 2 Enhanced Orchestrator Graph.

Integrates supervisor and summarizer for intelligent routing and context management.
"""

import logging
from typing import Optional

from langgraph.graph import StateGraph, END
from langchain_ollama import ChatOllama

from ..state.schemas import TaskState, TaskStatus, AgentType, MessageType
from ..agents import (
    ResearchAgentInterface,
    ContextCoreInterface,
    PRAgentInterface,
)
from .nodes import OrchestratorNodes
from .supervisor import EnhancedSupervisor, RoutingStrategy
from .summarizer import ContextSummarizer
from .edges import route_after_agent

logger = logging.getLogger(__name__)


class EnhancedOrchestratorGraph:
    """
    Phase 2 Orchestrator with intelligent supervision and context management.

    Improvements over Phase 1:
    - Context summarization to prevent overflow
    - Multiple routing strategies
    - Decision history tracking
    - Better error recovery
    """

    def __init__(
        self,
        research_agent: ResearchAgentInterface,
        context_agent: ContextCoreInterface,
        pr_agent: PRAgentInterface,
        llm_base_url: str = "http://localhost:11434",
        llm_model: str = "llama3.1:8b-instruct-q8_0",
        routing_strategy: RoutingStrategy = RoutingStrategy.ADAPTIVE,
    ):
        """
        Initialize enhanced orchestrator.

        Args:
            research_agent: Research agent interface
            context_agent: Context Core interface
            pr_agent: PR-Agent interface
            llm_base_url: Ollama base URL
            llm_model: Ollama model name
            routing_strategy: Routing strategy to use
        """
        self.research_agent = research_agent
        self.context_agent = context_agent
        self.pr_agent = pr_agent
        self.routing_strategy = routing_strategy

        # Initialize LLM
        self.llm = ChatOllama(
            base_url=llm_base_url,
            model=llm_model,
            temperature=0.7,
        )

        # Initialize Phase 2 components
        self.summarizer = ContextSummarizer(
            llm=self.llm,
            max_summary_tokens=500,
        )

        self.supervisor = EnhancedSupervisor(
            llm=self.llm,
            summarizer=self.summarizer,
            default_strategy=routing_strategy,
        )

        # Initialize nodes (Phase 1)
        self.nodes = OrchestratorNodes(
            research_agent=research_agent,
            context_agent=context_agent,
            pr_agent=pr_agent,
            llm=self.llm,
        )

        # Build graph
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the enhanced state graph."""
        logger.info("Building Phase 2 enhanced orchestrator graph")

        workflow = StateGraph(dict)

        # Add nodes with Phase 2 enhancements
        workflow.add_node("supervisor_entry", self._supervisor_entry_node)
        workflow.add_node("call_research", self._enhanced_research_node)
        workflow.add_node("call_context", self._enhanced_context_node)
        workflow.add_node("call_pr", self._enhanced_pr_node)
        workflow.add_node("supervisor_route", self._supervisor_route_node)
        workflow.add_node("finalize", self._enhanced_finalize_node)

        # Set entry point
        workflow.set_entry_point("supervisor_entry")

        # After supervisor entry -> route to first agent
        workflow.add_conditional_edges(
            "supervisor_entry",
            self._route_from_supervisor_entry,
            {
                "call_research": "call_research",
                "call_context": "call_context",
                "call_pr": "call_pr",
            },
        )

        # After each agent -> supervisor decides next
        for agent_node in ["call_research", "call_context", "call_pr"]:
            workflow.add_conditional_edges(
                agent_node,
                route_after_agent,
                {
                    "decide_next": "supervisor_route",
                    "finalize": "finalize",
                },
            )

        # After supervisor routing -> next agent or finalize
        workflow.add_conditional_edges(
            "supervisor_route",
            self._route_after_supervisor,
            {
                "call_research": "call_research",
                "call_context": "call_context",
                "call_pr": "call_pr",
                "finalize": "finalize",
            },
        )

        # Finalize leads to END
        workflow.add_edge("finalize", END)

        # Compile
        compiled = workflow.compile()

        logger.info("Phase 2 graph compiled successfully")

        return compiled

    async def _supervisor_entry_node(self, state: dict) -> dict:
        """
        Supervisor entry node - decides first agent using strategy.
        """
        task_state = TaskState(**state)

        logger.info(f"Supervisor entry: {task_state.objective}")

        try:
            # Use supervisor to decide first agent
            decision = await self.supervisor.decide_initial_route(
                objective=task_state.objective,
                strategy=self.routing_strategy,
            )

            task_state.next_agent = decision.next_agent
            task_state.status = TaskStatus.RUNNING

            # Log decision
            logger.info(
                f"Initial routing decision: {decision.next_agent} "
                f"(strategy: {decision.strategy_used.value}, "
                f"confidence: {decision.confidence:.2f})"
            )
            logger.info(f"Reasoning: {decision.reasoning}")

            # Add decision to messages
            task_state.add_message(
                agent_type=AgentType.SUPERVISOR,
                message_type=MessageType.INFO,
                content={
                    "decision": "initial_route",
                    "next_agent": decision.next_agent.value if decision.next_agent else None,
                    "strategy": decision.strategy_used.value,
                    "reasoning": decision.reasoning,
                },
            )

        except Exception as e:
            logger.error(f"Supervisor entry failed: {e}")
            # Fallback to research
            task_state.next_agent = "research"
            task_state.add_error(f"Supervisor entry error: {str(e)}")

        return task_state.model_dump()

    async def _enhanced_research_node(self, state: dict) -> dict:
        """Enhanced research node with context summarization."""
        # Call original node
        state_dict = await self.nodes.call_research_agent(state)
        task_state = TaskState(**state_dict)

        # Summarize results for next agent
        if task_state.research_results:
            try:
                summary = await self.summarizer.summarize_research_results(
                    task_state.research_results,
                    task_state.objective,
                )
                # Store summary in user_context for next agent
                task_state.user_context["research_summary"] = summary

                logger.info(f"Research summary created: {len(summary)} chars")

            except Exception as e:
                logger.error(f"Failed to summarize research: {e}")

        return task_state.model_dump()

    async def _enhanced_context_node(self, state: dict) -> dict:
        """Enhanced context node with summarization."""
        # Call original node
        state_dict = await self.nodes.call_context_agent(state)
        task_state = TaskState(**state_dict)

        # Summarize results
        if task_state.context_results:
            try:
                summary = await self.summarizer.summarize_context_results(
                    task_state.context_results,
                    task_state.objective,
                )
                task_state.user_context["context_summary"] = summary

                logger.info(f"Context summary created: {len(summary)} chars")

            except Exception as e:
                logger.error(f"Failed to summarize context: {e}")

        return task_state.model_dump()

    async def _enhanced_pr_node(self, state: dict) -> dict:
        """Enhanced PR node with optimized context."""
        task_state = TaskState(**state)

        # Create optimized context for PR agent
        try:
            optimized_context = await self.summarizer.create_agent_context(
                task_state,
                "pr",
            )
            # Merge with existing context
            task_state.user_context.update(optimized_context)

            logger.info("Created optimized context for PR agent")

        except Exception as e:
            logger.error(f"Failed to create PR context: {e}")

        # Call original node
        return await self.nodes.call_pr_agent(task_state.model_dump())

    async def _supervisor_route_node(self, state: dict) -> dict:
        """Supervisor routing node - decides next agent."""
        task_state = TaskState(**state)

        logger.info("Supervisor routing decision")

        try:
            # Use supervisor to decide next agent
            decision = await self.supervisor.decide_next_route(task_state)

            task_state.next_agent = decision.next_agent
            task_state.increment_iteration()

            # Log decision
            logger.info(
                f"Routing decision: {decision.next_agent} "
                f"(confidence: {decision.confidence:.2f})"
            )
            logger.info(f"Reasoning: {decision.reasoning}")

            # Add decision to messages
            task_state.add_message(
                agent_type=AgentType.SUPERVISOR,
                message_type=MessageType.INFO,
                content={
                    "decision": "next_route",
                    "next_agent": decision.next_agent.value if decision.next_agent else None,
                    "reasoning": decision.reasoning,
                    "confidence": decision.confidence,
                },
            )

        except Exception as e:
            logger.error(f"Supervisor routing failed: {e}")
            task_state.next_agent = None
            task_state.add_error(f"Supervisor routing error: {str(e)}")

        return task_state.model_dump()

    async def _enhanced_finalize_node(self, state: dict) -> dict:
        """Enhanced finalize with comprehensive summary."""
        task_state = TaskState(**state)

        logger.info("Finalizing task with enhanced summary")

        try:
            # Get comprehensive state summary
            state_summary = await self.summarizer.summarize_task_state(task_state)

            # Use original finalize logic
            final_dict = await self.nodes.finalize(state)
            final_state = TaskState(**final_dict)

            # Enhance final output with summary
            if final_state.final_output:
                final_state.final_output = (
                    f"{final_state.final_output}\n\n"
                    f"## Task Summary\n\n{state_summary}"
                )

            # Add supervisor decision history
            history = self.supervisor.get_decision_history()
            if history:
                decisions_text = "\n".join([
                    f"- {d.next_agent.value if d.next_agent else 'DONE'}: {d.reasoning}"
                    for d in history
                ])
                final_state.final_output += f"\n\n## Routing Decisions\n\n{decisions_text}"

            logger.info("Task finalized with enhanced summary")

            return final_state.model_dump()

        except Exception as e:
            logger.error(f"Enhanced finalize failed: {e}")
            # Fallback to basic finalize
            return await self.nodes.finalize(state)

    def _route_from_supervisor_entry(self, state: dict):
        """Route from supervisor entry to first agent."""
        task_state = TaskState(**state)
        next_agent = task_state.next_agent

        if next_agent == "research":
            return "call_research"
        elif next_agent == "context":
            return "call_context"
        elif next_agent == "pr":
            return "call_pr"
        else:
            return "call_research"  # Default

    def _route_after_supervisor(self, state: dict):
        """Route after supervisor decision."""
        task_state = TaskState(**state)
        next_agent = task_state.next_agent

        if next_agent is None:
            return "finalize"
        elif next_agent == "research":
            return "call_research"
        elif next_agent == "context":
            return "call_context"
        elif next_agent == "pr":
            return "call_pr"
        else:
            return "finalize"

    async def run(
        self,
        objective: str,
        user_context: Optional[dict] = None,
        max_iterations: int = 10,
        routing_strategy: Optional[RoutingStrategy] = None,
    ) -> TaskState:
        """
        Run the enhanced orchestrator.

        Args:
            objective: Task objective
            user_context: Optional user context
            max_iterations: Maximum iterations
            routing_strategy: Optional strategy override

        Returns:
            Final TaskState
        """
        logger.info(f"Starting Phase 2 orchestration: {objective}")

        # Override strategy if specified
        if routing_strategy:
            self.supervisor.default_strategy = routing_strategy

        try:
            # Create initial state
            initial_state = TaskState(
                objective=objective,
                user_context=user_context or {},
                max_iterations=max_iterations,
            )

            # Run graph
            final_state_dict = await self.graph.ainvoke(initial_state.model_dump())
            final_state = TaskState(**final_state_dict)

            logger.info(
                f"Phase 2 orchestration completed - "
                f"Status: {final_state.status}, Iterations: {final_state.iteration}"
            )

            return final_state

        except Exception as e:
            logger.error(f"Phase 2 orchestration failed: {e}")
            raise
        finally:
            # Clear supervisor history for next run
            self.supervisor.clear_history()

    def get_supervisor_stats(self) -> dict:
        """Get supervisor statistics."""
        history = self.supervisor.get_decision_history()

        stats = {
            "total_decisions": len(history),
            "strategies_used": {},
            "avg_confidence": 0.0,
        }

        if history:
            # Count strategies
            for decision in history:
                strategy = decision.strategy_used.value
                stats["strategies_used"][strategy] = stats["strategies_used"].get(strategy, 0) + 1

            # Average confidence
            stats["avg_confidence"] = sum(d.confidence for d in history) / len(history)

        return stats

    def get_graph_visualization(self) -> str:
        """Get Mermaid diagram of the graph."""
        return self.graph.get_graph().draw_mermaid()
