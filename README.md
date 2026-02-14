# The Orchestrator

An autonomous project manager that orchestrates multiple AI agents to accomplish complex software development tasks.

## Overview

The Orchestrator is a meta-agent system that coordinates three specialized agents:
- **Research Agent** (Project 1): Finds best practices and implementation patterns
- **Context Core** (Project 3): Manages memory and context with secret filtering
- **PR-Agent** (Project 2): Writes code and creates pull requests

## The Build Plan: 4 Phases to Autonomy

### Phase 1: The Blackboard
**Focus**: Creating a shared "State" where all three agents can read/write data.

**Tech Stack**: LangGraph, Redis (Local)

### Phase 2: The Router
**Focus**: Building a "Supervisor" node that decides which agent to call next.

**Tech Stack**: Claude Pro, Ollama

### Phase 3: The HITL Gate
**Focus**: Implementing "Human-in-the-Loop" for safety checks before code execution.

**Tech Stack**: FastAPI, Inquirer.py

### Phase 4: The Commander CLI
**Focus**: A unified terminal interface to manage your entire local AI ecosystem.

**Tech Stack**: Click (Python)

## The Workflow: How It Works

1. **Objective**: You tell the Commander: *"I want to add a dark-mode toggle to my React app using Tailwind."*

2. **Research (Project 1)**: The Commander triggers the Research Agent to find the best Tailwind dark-mode implementation.

3. **Memory (Project 3)**: It queries your Context Core to see if you've done this before or have specific styling rules saved.

4. **Action (Project 2)**: It passes the research and context to the PR-Agent to write the code and open the Pull Request.

## Important Things to Remember

- **Avoid "Infinite Loops"**: Agents can sometimes get stuck talking to each other. You must implement a "Max Iterations" safeguard in your LangGraph.

- **Shared Context is Key**: The Commander must be able to summarize the output of one agent before passing it to the next to keep the context window clean.

- **Security**: Since the Commander will have access to your terminal and GitHub, your Secret Filtering from Project 3 must be strictly enforced here.

## Project Structure

```
the-orchestrator/
├── src/
│   ├── orchestrator/       # Main orchestrator logic
│   ├── agents/             # Agent interfaces and wrappers
│   ├── state/              # Shared state management (Redis/LangGraph)
│   ├── cli/                # CLI interface (Phase 4)
│   └── api/                # FastAPI for HITL (Phase 3)
├── config/                 # Configuration files
├── tests/                  # Test files
└── docs/                   # Documentation
```

## Getting Started

Coming soon after Phase 1 implementation.

## License

MIT
