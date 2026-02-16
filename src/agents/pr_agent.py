"""
PR-Agent interface - integrates with PR-Agent via subprocess.
"""

import asyncio
import os
from pathlib import Path
from typing import Any

from .base import (
    AgentInterface,
    AgentError,
    AgentTimeoutError,
)


class PRAgentInterface(AgentInterface):
    """Interface to PR-Agent via subprocess."""

    def __init__(
        self,
        agent_path: str,
        timeout: float = 300.0,  # 5 minutes for PR creation
    ):
        """
        Initialize PR-Agent interface.

        Args:
            agent_path: Path to PR-Agent project
            timeout: Execution timeout in seconds
        """
        super().__init__("pr")
        self.agent_path = Path(agent_path)
        self.agent_script = self.agent_path / "agent.py"
        self.timeout = timeout

        if not self.agent_script.exists():
            raise AgentError(
                self.name,
                f"PR-Agent script not found at {self.agent_script}",
            )

    async def execute(self, task_input: dict[str, Any]) -> dict[str, Any]:
        """
        Execute PR creation task.

        Args:
            task_input: Must contain:
                - 'title': str (PR title)
                - 'body': str (PR description)
                - 'repo_path': str (path to git repo)

        Returns:
            PR results dict with:
                - title: str
                - pr_url: str
                - branch_name: str
                - files_changed: list[str]
                - success: bool

        Raises:
            AgentError: If PR creation fails
        """
        try:
            await self.validate_input(task_input)

            title = task_input["title"]
            body = task_input["body"]
            repo_path = task_input["repo_path"]

            self.logger.info(f"Creating PR: {title}")

            # Execute agent.py as subprocess
            result = await self._run_agent(title, body, repo_path)

            self._log_execution(task_input, result)
            return result

        except asyncio.TimeoutError:
            raise AgentTimeoutError(
                self.name,
                f"PR creation timed out after {self.timeout}s",
            )
        except AgentError:
            raise
        except Exception as e:
            raise AgentError(self.name, f"PR creation failed: {str(e)}", e)

    async def _run_agent(self, title: str, body: str, repo_path: str) -> dict[str, Any]:
        """Run agent.py subprocess."""
        # Change to repo directory
        original_cwd = os.getcwd()

        try:
            os.chdir(repo_path)

            # Run agent.py
            process = await asyncio.create_subprocess_exec(
                "python",
                str(self.agent_script),
                title,
                body,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Wait with timeout
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout,
            )

            # Parse output
            output = stdout.decode("utf-8") if stdout else ""
            error_output = stderr.decode("utf-8") if stderr else ""

            if process.returncode != 0:
                raise AgentError(
                    self.name,
                    f"Agent exited with code {process.returncode}: {error_output}",
                )

            # Parse result from output
            result = self._parse_output(output, title)
            return result

        finally:
            # Restore working directory
            os.chdir(original_cwd)

    def _parse_output(self, output: str, title: str) -> dict[str, Any]:
        """Parse agent output to extract PR details."""
        # Look for PR URL in output
        pr_url = None
        branch_name = None
        files_changed = []

        for line in output.split("\n"):
            # Look for GitHub PR URL
            if "github.com" in line and "/pull/" in line:
                # Extract URL
                parts = line.split()
                for part in parts:
                    if "github.com" in part and "/pull/" in part:
                        pr_url = part.strip()
                        break

            # Look for branch name
            if "branch" in line.lower() and "fix-" in line:
                parts = line.split()
                for part in parts:
                    if part.startswith("fix-"):
                        branch_name = part.strip()
                        break

            # Look for file changes
            if ".py" in line or ".js" in line or ".ts" in line:
                # Simple heuristic - file paths usually have extensions
                parts = line.split()
                for part in parts:
                    if "." in part and "/" in part:
                        files_changed.append(part.strip())

        success = pr_url is not None

        return {
            "title": title,
            "pr_url": pr_url,
            "branch_name": branch_name,
            "files_changed": list(set(files_changed)),  # Deduplicate
            "success": success,
            "error": None if success else "Failed to create PR",
        }

    async def health_check(self) -> bool:
        """Check if PR-Agent is accessible."""
        try:
            # Check if agent.py exists and is executable
            return self.agent_script.exists()
        except Exception as e:
            self.logger.warning(f"Health check failed: {e}")
            return False

    async def validate_input(self, task_input: dict[str, Any]) -> bool:
        """Validate PR task input."""
        required = ["title", "body", "repo_path"]
        for field in required:
            if field not in task_input:
                raise ValueError(f"PR task input must contain '{field}'")

        # Validate repo path exists
        repo_path = Path(task_input["repo_path"])
        if not repo_path.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")

        # Check if it's a git repo
        git_dir = repo_path / ".git"
        if not git_dir.exists():
            raise ValueError(f"Not a git repository: {repo_path}")

        return True
