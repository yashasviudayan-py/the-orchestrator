# Phase 2 Guide: The Router

Complete guide for using Phase 2 (Enhanced Routing & Context Management).

## What's New in Phase 2

Phase 2 builds on Phase 1 with intelligent routing and context management:

### 1. **Context Summarization** 🎯
- Prevents context window overflow
- Intelligent compression of agent outputs
- Preserves key information while reducing tokens
- Ollama-powered summarization

### 2. **Enhanced Supervisor** 🧠
- Multiple routing strategies (research-first, context-first, adaptive)
- LLM-powered routing decisions
- Decision history tracking
- Confidence scoring

### 3. **Smart Context Management** 📦
- Agent-specific context optimization
- Automatic summarization between transitions
- Token estimation and management
- Tailored context for each agent

### 4. **Routing Strategies** 🎲

#### Research-First
Best for: New features, unfamiliar technologies
```python
strategy = RoutingStrategy.RESEARCH_FIRST
```

#### Context-First
Best for: Similar past work, refactoring
```python
strategy = RoutingStrategy.CONTEXT_FIRST
```

#### Adaptive (Recommended)
LLM decides best approach based on objective
```python
strategy = RoutingStrategy.ADAPTIVE
```

## Quick Start

### Basic Usage

```python
from orchestrator import EnhancedOrchestratorGraph, RoutingStrategy
from agents import (
    ResearchAgentInterface,
    ContextCoreInterface,
    PRAgentInterface,
)

# Initialize with Phase 2 graph
orchestrator = EnhancedOrchestratorGraph(
    research_agent=ResearchAgentInterface(),
    context_agent=ContextCoreInterface(path),
    pr_agent=PRAgentInterface(path),
    routing_strategy=RoutingStrategy.ADAPTIVE,  # Choose strategy
)

# Run with automatic routing
result = await orchestrator.run(
    objective="Add email verification to signup",
    user_context={"repo_path": "."},
)

# View routing decisions
stats = orchestrator.get_supervisor_stats()
print(f"Total decisions: {stats['total_decisions']}")
print(f"Average confidence: {stats['avg_confidence']:.2f}")
```

## Routing Strategies Explained

### 1. Research-First Strategy

**When to use:**
- Implementing new features
- Unfamiliar technologies
- Need for best practices

**Flow:**
```
Objective → Research → Context → PR
```

**Example:**
```python
result = await orchestrator.run(
    objective="Add OAuth2 authentication",
    routing_strategy=RoutingStrategy.RESEARCH_FIRST,
)
```

### 2. Context-First Strategy

**When to use:**
- Similar work done before
- Code refactoring
- Pattern replication

**Flow:**
```
Objective → Context → Research (if needed) → PR
```

**Example:**
```python
result = await orchestrator.run(
    objective="Update existing login flow",
    routing_strategy=RoutingStrategy.CONTEXT_FIRST,
)
```

### 3. Adaptive Strategy (Recommended)

**How it works:**
- Ollama analyzes the objective
- Decides best first agent
- Adapts routing based on results

**Example:**
```python
result = await orchestrator.run(
    objective="Fix typo in button text",  # Simple → Direct to PR
    routing_strategy=RoutingStrategy.ADAPTIVE,
)

result = await orchestrator.run(
    objective="Implement WebSocket real-time updates",  # Complex → Research first
    routing_strategy=RoutingStrategy.ADAPTIVE,
)
```

## Context Summarization

### Automatic Summarization

Phase 2 automatically summarizes agent outputs:

```python
# Research results summarized before passing to Context
research_summary = """
Key Findings:
- JWT tokens preferred for stateless auth
- Use httpOnly cookies for security
- Implement refresh token rotation

Recommended: OAuth2 with PKCE flow
"""

# Context results summarized before PR
context_summary = """
Prior Work: Similar auth implementation in user-service
Confidence: 0.85
Recommendation: Follow existing pattern
"""
```

### Manual Summarization

You can also use the summarizer directly:

```python
from orchestrator import ContextSummarizer

summarizer = ContextSummarizer(llm=ollama_llm)

# Summarize custom content
summary = await summarizer.summarize_research_results(
    research_result,
    objective="Add authentication",
)

# Estimate tokens
token_count = await summarizer.estimate_token_count(long_text)

# Check if should summarize
if await summarizer.should_summarize(text):
    summary = await llm.summarize(text)
```

## Supervisor Decisions

### Decision History

Track all routing decisions:

```python
# Run orchestration
result = await orchestrator.run(objective="...")

# Get decision history
history = orchestrator.supervisor.get_decision_history()

for decision in history:
    print(f"Agent: {decision.next_agent}")
    print(f"Strategy: {decision.strategy_used}")
    print(f"Reasoning: {decision.reasoning}")
    print(f"Confidence: {decision.confidence:.2f}")
```

### Decision Structure

```python
@dataclass
class RoutingDecision:
    next_agent: Optional[AgentType]      # Which agent to call
    strategy_used: RoutingStrategy        # Strategy that made decision
    reasoning: str                        # Why this agent was chosen
    confidence: float                     # Confidence (0.0-1.0)
    alternative_agents: List[AgentType]   # Other options considered
```

## Advanced Features

### Custom Context for Agents

```python
# Create optimized context for specific agent
context = await summarizer.create_agent_context(
    state=task_state,
    target_agent="pr",
)

# Context is tailored:
# - PR agent gets research + context summaries
# - Research agent gets minimal context (just objective)
# - Context agent gets research findings
```

### Retry Logic

```python
# Supervisor decides if failed agent should retry
should_retry = await supervisor.should_retry(
    state=task_state,
    failed_agent=AgentType.RESEARCH,
)

if should_retry:
    # Retry with same agent
    pass
else:
    # Move to next agent or finalize
    pass
```

### Performance Monitoring

```python
# Get supervisor statistics
stats = orchestrator.get_supervisor_stats()

{
    "total_decisions": 5,
    "strategies_used": {
        "adaptive": 5,
        "research_first": 0,
    },
    "avg_confidence": 0.78,
}
```

## Comparison: Phase 1 vs Phase 2

| Feature | Phase 1 | Phase 2 |
|---------|---------|---------|
| Routing | Basic LLM decisions | Multiple strategies + history |
| Context Management | Raw pass-through | Intelligent summarization |
| Token Management | None | Automatic estimation & compression |
| Decision Tracking | None | Full history with reasoning |
| Error Recovery | Basic retry | Smart retry decisions |
| Strategy Selection | Fixed | Adaptive + selectable |

## Best Practices

### 1. Choose Right Strategy

```python
# New feature with unfamiliar tech
strategy = RoutingStrategy.RESEARCH_FIRST

# Refactoring existing code
strategy = RoutingStrategy.CONTEXT_FIRST

# Not sure? Let LLM decide
strategy = RoutingStrategy.ADAPTIVE  # ✅ Recommended default
```

### 2. Monitor Context Size

```python
# Check summary effectiveness
result = await orchestrator.run(objective="...")

# Review summaries in messages
for msg in result.messages:
    if msg.message_type == "info" and "summary" in msg.content:
        print(f"Summary created: {len(msg.content['summary'])} chars")
```

### 3. Review Routing Decisions

```python
# After completion, analyze routing
history = orchestrator.supervisor.get_decision_history()

# Were decisions optimal?
for decision in history:
    if decision.confidence < 0.5:
        print(f"⚠️  Low confidence decision: {decision.reasoning}")
```

## Troubleshooting

### Issue: Context Still Too Large

```python
# Reduce max summary tokens
summarizer = ContextSummarizer(
    llm=llm,
    max_summary_tokens=300,  # Reduced from 500
)
```

### Issue: Wrong Routing Strategy

```python
# Override default strategy
result = await orchestrator.run(
    objective="...",
    routing_strategy=RoutingStrategy.RESEARCH_FIRST,  # Force research first
)
```

### Issue: Too Many Iterations

```python
# Reduce max iterations
result = await orchestrator.run(
    objective="...",
    max_iterations=5,  # Reduced from 10
)
```

## Migration from Phase 1

Simple! Just swap the graph class:

```python
# Phase 1
from orchestrator import OrchestratorGraph
orchestrator = OrchestratorGraph(...)

# Phase 2
from orchestrator import EnhancedOrchestratorGraph
orchestrator = EnhancedOrchestratorGraph(...)

# Same interface, enhanced features!
```

## Next Steps

- **Phase 3**: Human-in-the-Loop (HITL) gate with FastAPI
- **Phase 4**: Commander CLI with Click + Rich

## Examples

See [`examples/phase2_demo.py`](../examples/phase2_demo.py) for complete examples.
