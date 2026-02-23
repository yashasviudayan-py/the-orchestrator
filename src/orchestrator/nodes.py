"""
LangGraph nodes for the orchestrator.
Each node represents a step in the orchestration workflow.
"""

import logging
from typing import Any

from langchain_ollama import ChatOllama

from ..state.schemas import (
    TaskState,
    TaskStatus,
    AgentType,
    MessageType,
    ResearchResult,
    ContextResult,
    PRResult,
)
from ..agents import (
    ResearchAgentInterface,
    ContextCoreInterface,
    PRAgentInterface,
    AgentError,
)

logger = logging.getLogger(__name__)


class OrchestratorNodes:
    """Collection of node functions for the orchestrator graph."""

    def __init__(
        self,
        research_agent: ResearchAgentInterface,
        context_agent: ContextCoreInterface,
        pr_agent: PRAgentInterface,
        llm: ChatOllama,
    ):
        """
        Initialize nodes with agent interfaces.

        Args:
            research_agent: Research agent interface
            context_agent: Context Core interface
            pr_agent: PR-Agent interface
            llm: Ollama LLM for routing decisions
        """
        self.research_agent = research_agent
        self.context_agent = context_agent
        self.pr_agent = pr_agent
        self.llm = llm

    # ── Conversational patterns that need NO agents ──────────────────────
    _CONVERSATIONAL = {
        'hi', 'hey', 'hello', 'howdy', 'sup', 'yo', 'hiya',
        'thanks', 'thank you', 'thx', 'ty', 'thank u',
        'bye', 'goodbye', 'cya', 'see you', 'later',
        'ok', 'okay', 'k', 'cool', 'got it', 'nice', 'great',
        'awesome', 'perfect', 'sounds good', 'alright',
        'lol', 'haha', 'hehe', ':)', '👍',
        'good morning', 'good night', 'good evening', 'good afternoon',
        'how are you', "how r u", "what's up", 'whats up',
        'who are you', 'what are you', 'what can you do',
    }
    # Words that always mean a real task even in short messages
    _TASK_WORDS = {
        'fix', 'add', 'create', 'implement', 'build', 'write', 'debug',
        'update', 'delete', 'remove', 'test', 'deploy', 'refactor',
        'install', 'setup', 'configure', 'migrate', 'generate', 'push',
        'commit', 'pr', 'pull', 'merge', 'branch', 'diff', 'review',
        'research', 'find', 'search', 'analyze', 'analyse', 'explain',
        'show', 'list', 'get', 'fetch', 'run', 'execute', 'start',
    }

    def _is_conversational(self, text: str) -> bool:
        """Return True if the message is conversational and needs no agents."""
        t = text.strip().lower().rstrip('!?.,')
        # Exact match
        if t in self._CONVERSATIONAL:
            return True
        # Starts-with match (e.g. "hi there", "hey how are you")
        for p in self._CONVERSATIONAL:
            if t == p or t.startswith(p + ' '):
                return True
        # Very short (≤3 words) and no task keywords
        words = t.split()
        if len(words) <= 3 and not any(w in self._TASK_WORDS for w in words):
            return True
        return False

    async def parse_objective(self, state: dict) -> dict:
        """
        Parse user objective and determine initial routing strategy.
        Conversational messages are answered directly without agents.

        Args:
            state: Current task state

        Returns:
            Updated state with routing decision
        """
        task_state = TaskState(**state)
        objective = task_state.objective

        logger.info(f"Parsing objective: {objective}")

        task_state.status = TaskStatus.RUNNING

        # ── Phase 1: Direct conversational reply (no agents needed) ──────
        if self._is_conversational(objective):
            logger.info("Conversational message detected — skipping agents")
            try:
                prompt = (
                    "You are The Orchestrator, a friendly AI project manager. "
                    "Reply naturally and concisely to this message "
                    f"(1-3 sentences max): {objective}"
                )
                resp = await self.llm.ainvoke(prompt)
                task_state.final_output = resp.content.strip()
            except Exception as e:
                logger.warning(f"Direct reply failed: {e}")
                task_state.final_output = "Hello! How can I help you today?"

            task_state.next_agent = None   # → finalize directly
            return task_state.model_dump()

        # ── Phase 2: Task routing — decide which agent to call first ─────
        try:
            prompt = f"""You are a routing assistant. Decide the FIRST agent to call for this task.

Task: {objective}

Agents:
- research: find best practices, new technology, external knowledge
- context: check existing codebase, prior work, project history
- pr: write/edit code, create pull requests

Rules:
- Greetings or simple questions that need no code → NONE
- Questions about this specific project/codebase → context
- Questions requiring external knowledge/research → research
- Code changes, bug fixes, new features → pr or research first

Respond with ONLY one word: research, context, pr, or NONE
"""
            response = await self.llm.ainvoke(prompt)
            next_agent = response.content.strip().lower().split()[0]  # take first word only

            if next_agent == "none":
                # LLM says no agents needed — generate direct reply
                try:
                    direct_prompt = (
                        "You are The Orchestrator, an AI project manager. "
                        f"Answer this directly and concisely: {objective}"
                    )
                    resp = await self.llm.ainvoke(direct_prompt)
                    task_state.final_output = resp.content.strip()
                except Exception:
                    task_state.final_output = f"Here is my response to: {objective}"
                task_state.next_agent = None
            elif next_agent in ("research", "context", "pr"):
                task_state.next_agent = AgentType(next_agent)
                task_state.add_message(
                    AgentType.CONTEXT,
                    MessageType.INFO,
                    {"action": "parsed_objective", "next_agent": next_agent},
                )
                logger.info(f"Routing to: {next_agent}")
            else:
                # Unknown response → default to research
                task_state.next_agent = AgentType.RESEARCH
                logger.warning(f"Unexpected routing response '{next_agent}' — defaulting to research")

        except Exception as e:
            logger.error(f"Failed to parse objective: {e}")
            task_state.add_error(f"Objective parsing failed: {str(e)}")
            task_state.next_agent = AgentType.RESEARCH

        return task_state.model_dump()

    async def call_research_agent(self, state: dict) -> dict:
        """
        Call Research Agent to find best practices.

        Args:
            state: Current task state

        Returns:
            Updated state with research results
        """
        task_state = TaskState(**state)

        logger.info("Calling Research Agent")

        try:
            task_state.mark_agent_called(AgentType.RESEARCH)

            # Prepare input
            research_input = {"topic": task_state.objective}

            # Call agent
            result = await self.research_agent.execute(research_input)

            # Filter secrets (CRITICAL SECURITY) — both summary and content
            summary = result.get("summary", "")
            content = result.get("content", "")
            filtered_summary, summary_had_secrets = self.context_agent.filter_secrets(summary)
            filtered_content, content_had_secrets = self.context_agent.filter_secrets(content)

            had_secrets = summary_had_secrets or content_had_secrets
            if had_secrets:
                task_state.secrets_detected = True
                task_state.add_error("Secrets detected in research results - filtered")

            # Apply filtered values before constructing ResearchResult
            result["summary"] = filtered_summary
            result["content"] = filtered_content

            # Store results
            task_state.research_results = ResearchResult(**result)

            task_state.add_message(
                AgentType.RESEARCH,
                MessageType.RESPONSE,
                {"summary": filtered_summary[:500], "urls_count": len(result.get("urls", []))},
            )

            logger.info("Research completed successfully")

        except AgentError as e:
            logger.warning(f"Research Agent unavailable ({e}) — falling back to Ollama")
            task_state = await self._ollama_research_fallback(task_state)

        return task_state.model_dump()

    async def _ollama_research_fallback(self, task_state: TaskState) -> TaskState:
        """
        Fallback when Research Agent is down — use Ollama directly to answer.
        Not as thorough as the full Research Agent (no web search, no sources)
        but keeps the pipeline working.
        """
        logger.info("Using Ollama as research fallback")

        prompt = f"""You are a knowledgeable assistant. Answer the following question thoroughly and accurately.

Question: {task_state.objective}

Provide a well-structured answer covering:
1. Direct answer to the question
2. Key concepts and best practices
3. Practical examples where relevant
4. Important considerations or caveats

Answer:"""

        try:
            response = await self.llm.ainvoke(prompt)
            content = response.content.strip()

            task_state.research_results = ResearchResult(
                topic=task_state.objective,
                summary=content[:500],
                content=content,
                key_findings=[],
                urls=[],
            )

            task_state.add_message(
                AgentType.RESEARCH,
                MessageType.RESPONSE,
                {
                    "summary": content[:500],
                    "source": "ollama_fallback",
                    "note": "Research Agent was unavailable — answered directly by Ollama",
                },
            )

            logger.info("Ollama fallback research completed")

        except Exception as e:
            logger.error(f"Ollama fallback also failed: {e}")
            task_state.add_error(f"Research failed (both agent and fallback): {str(e)}")
            task_state.retry_count += 1

        return task_state

    async def call_context_agent(self, state: dict) -> dict:
        """
        Call Context Core to check for prior work and relevant context.

        Args:
            state: Current task state

        Returns:
            Updated state with context results
        """
        task_state = TaskState(**state)

        logger.info("Calling Context Core")

        try:
            task_state.mark_agent_called(AgentType.CONTEXT)

            # Prepare input
            context_input = {
                "query": task_state.objective,
                "n_results": 10,
                "min_similarity": 0.5,
            }

            # Call agent
            result = await self.context_agent.execute(context_input)

            # Store results
            task_state.context_results = ContextResult(**result)

            task_state.add_message(
                AgentType.CONTEXT,
                MessageType.RESPONSE,
                {
                    "has_prior_work": result.get("has_prior_work", False),
                    "docs_found": len(result.get("relevant_docs", [])),
                    "confidence": result.get("confidence", 0.0),
                },
            )

            logger.info(f"Context search completed - found {len(result.get('relevant_docs', []))} docs")

        except AgentError as e:
            logger.error(f"Context agent failed: {e}")
            task_state.add_error(str(e))
            task_state.retry_count += 1

        return task_state.model_dump()

    async def call_pr_agent(self, state: dict) -> dict:
        """
        Call PR-Agent to write code and create PR.

        Args:
            state: Current task state

        Returns:
            Updated state with PR results
        """
        task_state = TaskState(**state)

        logger.info("Calling PR-Agent")

        try:
            task_state.mark_agent_called(AgentType.PR)

            # Build PR description from research + context
            pr_body = self._build_pr_description(task_state)

            # Prepare input
            pr_input = {
                "title": task_state.objective,
                "body": pr_body,
                "repo_path": task_state.user_context.get("repo_path", "."),
            }

            # Call agent
            result = await self.pr_agent.execute(pr_input)

            # Store results
            task_state.pr_results = PRResult(**result)

            task_state.add_message(
                AgentType.PR,
                MessageType.RESPONSE,
                {
                    "success": result.get("success", False),
                    "pr_url": result.get("pr_url"),
                    "files_changed": len(result.get("files_changed", [])),
                },
            )

            logger.info(f"PR creation {'succeeded' if result.get('success') else 'failed'}")

        except AgentError as e:
            logger.error(f"PR agent failed: {e}")
            task_state.add_error(str(e))
            task_state.retry_count += 1

        return task_state.model_dump()

    def _build_pr_description(self, task_state: TaskState) -> str:
        """Build PR description from research and context."""
        parts = []

        if task_state.research_results:
            parts.append("## Research Findings")
            if task_state.research_results.summary:
                parts.append(task_state.research_results.summary)
            if task_state.research_results.key_findings:
                parts.append("\n### Key Findings:")
                for finding in task_state.research_results.key_findings[:3]:
                    parts.append(f"- {finding}")

        if task_state.context_results and task_state.context_results.has_prior_work:
            parts.append("\n## Prior Work")
            parts.append("Similar implementations found in codebase - see context docs")

        return "\n\n".join(parts)

    async def decide_next_agent(self, state: dict) -> dict:
        """
        Decide which agent to call next based on current state.

        Args:
            state: Current task state

        Returns:
            Updated state with next agent decision
        """
        task_state = TaskState(**state)

        logger.info(f"Deciding next agent (iteration {task_state.iteration})")

        try:
            # Build context of what's been done
            agents_called_str = ", ".join([a.value for a in task_state.agents_called])

            # Use LLM to decide
            prompt = f"""Given the current task state, decide the next agent to call.

Objective: {task_state.objective}
Agents called: {agents_called_str}
Iteration: {task_state.iteration}/{task_state.max_iterations}

Current results:
- Research: {'✓' if task_state.research_results else '✗'}
- Context: {'✓' if task_state.context_results else '✗'}
- PR: {'✓' if task_state.pr_results else '✗'}

Rules:
- If all agents called and PR successful -> DONE
- If research not done -> research
- If context not checked -> context
- If PR not created -> pr
- If errors and retries available -> retry failed agent
- Otherwise -> DONE

Respond with ONLY: research, context, pr, or DONE
"""

            response = await self.llm.ainvoke(prompt)
            decision = response.content.strip().upper()

            if decision == "DONE" or task_state.pr_results and task_state.pr_results.success:
                task_state.next_agent = None
            elif decision in ["RESEARCH", "CONTEXT", "PR"]:
                task_state.next_agent = AgentType(decision.lower())
            else:
                # Default logic
                if not task_state.research_results:
                    task_state.next_agent = AgentType.RESEARCH
                elif not task_state.context_results:
                    task_state.next_agent = AgentType.CONTEXT
                elif not task_state.pr_results:
                    task_state.next_agent = AgentType.PR
                else:
                    task_state.next_agent = None

            task_state.increment_iteration()

            logger.info(f"Next agent: {task_state.next_agent}")

        except Exception as e:
            logger.error(f"Failed to decide next agent: {e}")
            task_state.add_error(str(e))
            task_state.next_agent = None

        return task_state.model_dump()

    async def finalize(self, state: dict) -> dict:
        """
        Finalize task and generate summary.

        Args:
            state: Current task state

        Returns:
            Final state with summary
        """
        task_state = TaskState(**state)

        logger.info("Finalizing task")

        try:
            # Short-circuit: direct reply was already generated (conversational / NONE route)
            if task_state.final_output:
                task_state.complete(task_state.final_output)
                return task_state.model_dump()

            # Build final output from agent results
            output_parts = []

            output_parts.append(f"# Task Completed: {task_state.objective}\n")

            if task_state.research_results:
                output_parts.append("## Answer\n")

                # Generate readable summary using LLM
                if task_state.research_results.content:
                    # Use LLM to create concise, readable answer
                    summary_prompt = f"""Based on this research about "{task_state.objective}", provide a concise, well-structured answer.

Research content (first 3000 chars):
{task_state.research_results.content[:3000]}

Provide a clear answer (300-500 words) that:
1. Directly answers: {task_state.objective}
2. Includes key facts
3. Is well-organized and readable
4. Uses plain language

Answer:"""

                    try:
                        response = await self.llm.ainvoke(summary_prompt)
                        readable_answer = response.content.strip()
                        output_parts.append(readable_answer)
                    except Exception as e:
                        logger.warning(f"Failed to generate answer: {e}")
                        # Fallback to first 1000 chars
                        output_parts.append(task_state.research_results.content[:1000] + "\n\n[Content truncated]")

                    # Add sources
                    if task_state.research_results.urls:
                        output_parts.append("\n\n### Sources:")
                        for url in task_state.research_results.urls[:5]:
                            output_parts.append(f"- {url}")
                else:
                    # Fallback
                    if task_state.research_results.summary:
                        output_parts.append(task_state.research_results.summary)

            if task_state.context_results:
                output_parts.append("\n## Context")
                if task_state.context_results.has_prior_work:
                    output_parts.append("Found relevant prior work in codebase")
                else:
                    output_parts.append("No prior work found")

            if task_state.pr_results:
                output_parts.append("\n## Pull Request")
                if task_state.pr_results.success and task_state.pr_results.pr_url:
                    output_parts.append(f"✓ PR created: {task_state.pr_results.pr_url}")
                else:
                    output_parts.append("✗ PR creation failed")

            if task_state.errors:
                output_parts.append(f"\n## Errors ({len(task_state.errors)})")
                for error in task_state.errors[:3]:
                    output_parts.append(f"- {error}")

            final_output = "\n".join(output_parts)

            task_state.complete(final_output)

            # ── Persist task result to Context Core vault ──────────────
            try:
                import sys
                from pathlib import Path as _Path
                from dotenv import load_dotenv as _load
                import os as _os
                _load()
                _cc_path = _Path(_os.getenv("CONTEXT_CORE_PATH", ""))
                _src = str(_cc_path / "src")
                if _src not in sys.path:
                    sys.path.insert(0, _src)
                from context_core.vault import Vault as _Vault
                from context_core.ingest import create_manual_document as _make_doc
                _vault = _Vault()
                _content = (
                    f"# Task: {task_state.objective}\n\n"
                    f"**Task ID:** {task_state.task_id}\n\n"
                    f"{final_output}"
                )
                _doc = _make_doc(
                    _content,
                    tags=["task_result", task_state.task_id],
                    source_type="task_result",
                )
                _vault.add([_doc])
                logger.info(f"Task result saved to Context Core vault: {task_state.task_id}")
            except Exception as _ve:
                logger.warning(f"Could not save task result to vault: {_ve}")
            # ───────────────────────────────────────────────────────────

            logger.info("Task finalized successfully")

        except Exception as e:
            logger.error(f"Failed to finalize task: {e}")
            task_state.fail(str(e))

        return task_state.model_dump()
