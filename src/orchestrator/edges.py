"""
LangGraph edge logic for conditional routing.
Determines which node to execute next based on state.
"""

import logging
from typing import Literal

from ..state.schemas import TaskState, AgentType

logger = logging.getLogger(__name__)


def route_after_parse(state: dict) -> Literal["call_research", "call_context", "call_pr"]:
    """
    Route after parsing objective.

    Args:
        state: Current task state

    Returns:
        Next node name
    """
    task_state = TaskState(**state)

    if task_state.next_agent == AgentType.RESEARCH:
        return "call_research"
    elif task_state.next_agent == AgentType.CONTEXT:
        return "call_context"
    elif task_state.next_agent == AgentType.PR:
        return "call_pr"
    else:
        # Default to research
        return "call_research"


def route_after_agent(state: dict) -> Literal["decide_next", "finalize"]:
    """
    Route after an agent completes.

    Args:
        state: Current task state

    Returns:
        Next node name
    """
    task_state = TaskState(**state)

    # Check iteration limit (CRITICAL SAFEGUARD)
    if task_state.iteration >= task_state.max_iterations:
        logger.warning(f"Max iterations ({task_state.max_iterations}) reached - finalizing")
        return "finalize"

    # Check if too many errors
    if len(task_state.errors) >= task_state.max_retries:
        logger.warning(f"Max errors ({task_state.max_retries}) reached - finalizing")
        return "finalize"

    # Continue to decide next agent
    return "decide_next"


def route_after_decision(
    state: dict,
) -> Literal["call_research", "call_context", "call_pr", "finalize"]:
    """
    Route after deciding next agent.

    Args:
        state: Current task state

    Returns:
        Next node name
    """
    task_state = TaskState(**state)

    # If no next agent, finalize
    if task_state.next_agent is None:
        return "finalize"

    # Route to appropriate agent
    if task_state.next_agent == AgentType.RESEARCH:
        return "call_research"
    elif task_state.next_agent == AgentType.CONTEXT:
        return "call_context"
    elif task_state.next_agent == AgentType.PR:
        return "call_pr"
    else:
        # Safety fallback
        return "finalize"


def should_require_approval(state: dict) -> bool:
    """
    Determine if human approval is required before proceeding.

    Args:
        state: Current task state

    Returns:
        True if approval required
    """
    task_state = TaskState(**state)

    # Require approval before PR creation if:
    # - About to call PR agent
    # - Not already approved
    if (
        task_state.next_agent == AgentType.PR
        and not task_state.approved
        and task_state.requires_approval == False
    ):
        return True

    return False
