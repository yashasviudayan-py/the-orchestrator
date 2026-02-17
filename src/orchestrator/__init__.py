"""Orchestrator module - LangGraph-based multi-agent coordination."""

# Phase 1 (Basic Orchestration)
from .graph import OrchestratorGraph
from .nodes import OrchestratorNodes

# Phase 2 (Enhanced Routing & Context Management)
from .graph_v2 import EnhancedOrchestratorGraph
from .supervisor import EnhancedSupervisor, RoutingStrategy, RoutingDecision
from .summarizer import ContextSummarizer

# Phase 3 (HITL Integration)
from .hitl_integration import (
    HITLGate,
    HITLEnhancedNodes,
    HITLConfig,
    create_hitl_enabled_graph,
)

__all__ = [
    # Phase 1
    "OrchestratorGraph",
    "OrchestratorNodes",
    # Phase 2
    "EnhancedOrchestratorGraph",
    "EnhancedSupervisor",
    "RoutingStrategy",
    "RoutingDecision",
    "ContextSummarizer",
    # Phase 3
    "HITLGate",
    "HITLEnhancedNodes",
    "HITLConfig",
    "create_hitl_enabled_graph",
]
