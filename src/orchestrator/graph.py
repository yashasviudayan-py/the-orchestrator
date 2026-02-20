"""
LangGraph state graph for the orchestrator.
Defines the complete workflow from objective to completion.
"""

import logging
from typing import Optional

from langgraph.graph import StateGraph, END
from langchain_ollama import ChatOllama

from ..state.schemas import TaskState
from ..agents import (
    ResearchAgentInterface,
    ContextCoreInterface,
    PRAgentInterface,
)
from .nodes import OrchestratorNodes
from .edges import (
    route_after_parse,
    route_after_agent,
    route_after_decision,
)

logger = logging.getLogger(__name__)


class OrchestratorGraph:
    """LangGraph-based orchestrator for multi-agent workflows."""

    def __init__(
        self,
        research_agent: ResearchAgentInterface,
        context_agent: ContextCoreInterface,
        pr_agent: PRAgentInterface,
        llm_base_url: str = "http://localhost:11434",
        llm_model: str = "llama3.1:8b-instruct-q8_0",
    ):
        """
        Initialize orchestrator graph.

        Args:
            research_agent: Research agent interface
            context_agent: Context Core interface
            pr_agent: PR-Agent interface
            llm_base_url: Ollama base URL
            llm_model: Ollama model name
        """
        self.research_agent = research_agent
        self.context_agent = context_agent
        self.pr_agent = pr_agent

        # Initialize LLM for routing decisions
        self.llm = ChatOllama(
            base_url=llm_base_url,
            model=llm_model,
            temperature=0.7,
        )

        # Initialize nodes
        self.nodes = OrchestratorNodes(
            research_agent=research_agent,
            context_agent=context_agent,
            pr_agent=pr_agent,
            llm=self.llm,
        )

        # Build graph
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """
        Build the LangGraph state graph.

        Returns:
            Compiled StateGraph
        """
        logger.info("Building orchestrator graph")

        # Create graph with TaskState schema
        workflow = StateGraph(dict)

        # Add nodes
        workflow.add_node("parse_objective", self.nodes.parse_objective)
        workflow.add_node("call_research", self.nodes.call_research_agent)
        workflow.add_node("call_context", self.nodes.call_context_agent)
        workflow.add_node("call_pr", self.nodes.call_pr_agent)
        workflow.add_node("decide_next", self.nodes.decide_next_agent)
        workflow.add_node("finalize", self.nodes.finalize)

        # Set entry point
        workflow.set_entry_point("parse_objective")

        # Add edges
        # After parsing -> route to first agent
        workflow.add_conditional_edges(
            "parse_objective",
            route_after_parse,
            {
                "call_research": "call_research",
                "call_context": "call_context",
                "call_pr": "call_pr",
                "finalize": "finalize",   # conversational / direct reply
            },
        )

        # After each agent -> decide what's next
        for agent_node in ["call_research", "call_context", "call_pr"]:
            workflow.add_conditional_edges(
                agent_node,
                route_after_agent,
                {
                    "decide_next": "decide_next",
                    "finalize": "finalize",
                },
            )

        # After decision -> route to next agent or finalize
        workflow.add_conditional_edges(
            "decide_next",
            route_after_decision,
            {
                "call_research": "call_research",
                "call_context": "call_context",
                "call_pr": "call_pr",
                "finalize": "finalize",
            },
        )

        # Finalize leads to END
        workflow.add_edge("finalize", END)

        # Compile graph
        compiled = workflow.compile()

        logger.info("Graph compiled successfully")

        return compiled

    async def run(
        self,
        objective: str,
        user_context: Optional[dict] = None,
        max_iterations: int = 10,
    ) -> TaskState:
        """
        Run the orchestrator on a task.

        Args:
            objective: Task objective
            user_context: Optional user context dict
            max_iterations: Maximum iterations

        Returns:
            Final TaskState

        Raises:
            Exception: If orchestration fails
        """
        logger.info(f"Starting orchestration: {objective}")

        try:
            # Create initial state
            initial_state = TaskState(
                objective=objective,
                user_context=user_context or {},
                max_iterations=max_iterations,
            )

            # Run graph
            final_state_dict = await self.graph.ainvoke(initial_state.model_dump())

            # Convert back to TaskState
            final_state = TaskState(**final_state_dict)

            logger.info(
                f"Orchestration completed - Status: {final_state.status}, "
                f"Iterations: {final_state.iteration}"
            )

            return final_state

        except Exception as e:
            logger.error(f"Orchestration failed: {e}")
            raise

    async def stream(
        self,
        objective: str,
        user_context: Optional[dict] = None,
        max_iterations: int = 10,
    ):
        """
        Stream orchestrator execution with progress updates.

        Args:
            objective: Task objective
            user_context: Optional user context dict
            max_iterations: Maximum iterations

        Yields:
            State updates as they occur

        Raises:
            Exception: If orchestration fails
        """
        logger.info(f"Starting streaming orchestration: {objective}")

        try:
            # Create initial state
            initial_state = TaskState(
                objective=objective,
                user_context=user_context or {},
                max_iterations=max_iterations,
            )

            # Stream graph execution
            # astream() yields {node_name: state_update} chunks
            async for chunk in self.graph.astream(initial_state.model_dump()):
                for _node_name, state_update in chunk.items():
                    state = TaskState(**state_update)
                    yield state

        except Exception as e:
            logger.error(f"Streaming orchestration failed: {e}")
            raise

    def get_graph_visualization(self) -> str:
        """
        Get Mermaid diagram of the graph.

        Returns:
            Mermaid diagram string
        """
        return self.graph.get_graph().draw_mermaid()
