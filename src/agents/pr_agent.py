"""
PR-Agent interface - integrates with PR-Agent via subprocess.
"""

import asyncio
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
        Execute PR creation task (full mode).

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
        """Run agent.py subprocess (full mode)."""
        process = await asyncio.create_subprocess_exec(
            "python",
            str(self.agent_script),
            title,
            body,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=repo_path,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=self.timeout,
        )

        output = stdout.decode("utf-8") if stdout else ""
        error_output = stderr.decode("utf-8") if stderr else ""

        if process.returncode != 0:
            raise AgentError(
                self.name,
                f"Agent exited with code {process.returncode}: {error_output}",
            )

        result = self._parse_output(output, title)
        return result

    async def generate_preview(self, task_input: dict[str, Any]) -> dict[str, Any]:
        """
        Phase 1: Generate code changes and return diff without committing.

        Args:
            task_input: Must contain 'title', 'body', 'repo_path'

        Returns:
            Dict with: diff, branch_name, target_file, files_changed, success, error
        """
        try:
            await self.validate_input(task_input)

            title = task_input["title"]
            body = task_input["body"]
            repo_path = task_input["repo_path"]

            self.logger.info(f"Generating preview for: {title}")

            process = await asyncio.create_subprocess_exec(
                "python",
                str(self.agent_script),
                title,
                body,
                "--mode", "generate",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=repo_path,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout,
            )

            output = stdout.decode("utf-8") if stdout else ""
            error_output = stderr.decode("utf-8") if stderr else ""

            if process.returncode != 0:
                return {
                    "diff": None,
                    "branch_name": None,
                    "target_file": None,
                    "files_changed": [],
                    "success": False,
                    "error": f"Generate failed (exit {process.returncode}): {error_output}",
                }

            return self._parse_generate_output(output)

        except asyncio.TimeoutError:
            return {
                "diff": None,
                "branch_name": None,
                "target_file": None,
                "files_changed": [],
                "success": False,
                "error": f"Generate timed out after {self.timeout}s",
            }
        except Exception as e:
            return {
                "diff": None,
                "branch_name": None,
                "target_file": None,
                "files_changed": [],
                "success": False,
                "error": str(e),
            }

    def _parse_generate_output(self, output: str) -> dict[str, Any]:
        """Parse generate mode output to extract diff and metadata."""
        branch_name = None
        target_file = None
        files_changed = []
        diff_lines = []
        in_diff = False

        for line in output.split("\n"):
            stripped = line.strip()

            if stripped == "DIFF_START":
                in_diff = True
                continue
            elif stripped == "DIFF_END":
                in_diff = False
                continue

            if in_diff:
                diff_lines.append(line)
                continue

            if "TARGET_FILE:" in stripped:
                target_file = stripped.split("TARGET_FILE:", 1)[1].strip()
            elif "BRANCH:" in stripped:
                branch_name = stripped.split("BRANCH:", 1)[1].strip()
            elif "FILES_CHANGED:" in stripped:
                files = stripped.split("FILES_CHANGED:", 1)[1].strip()
                files_changed.extend(f.strip() for f in files.split(",") if f.strip())

        diff_text = "\n".join(diff_lines).strip()
        success = bool(diff_text and branch_name and target_file)

        return {
            "diff": diff_text if diff_text else None,
            "branch_name": branch_name,
            "target_file": target_file,
            "files_changed": list(set(files_changed)),
            "success": success,
            "error": None if success else "No diff generated",
        }

    async def commit_and_push(self, task_input: dict[str, Any]) -> dict[str, Any]:
        """
        Phase 2: Commit, push, and create PR on an existing branch.

        Args:
            task_input: Must contain 'title', 'body', 'repo_path', 'branch_name', 'target_file'

        Returns:
            Standard PR result dict
        """
        try:
            title = task_input["title"]
            body = task_input["body"]
            repo_path = task_input["repo_path"]
            branch_name = task_input["branch_name"]
            target_file = task_input["target_file"]

            self.logger.info(f"Committing and pushing: {title} on {branch_name}")

            process = await asyncio.create_subprocess_exec(
                "python",
                str(self.agent_script),
                title,
                body,
                "--mode", "commit",
                "--branch", branch_name,
                "--file", target_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=repo_path,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout,
            )

            output = stdout.decode("utf-8") if stdout else ""
            error_output = stderr.decode("utf-8") if stderr else ""

            if process.returncode != 0:
                raise AgentError(
                    self.name,
                    f"Commit failed (exit {process.returncode}): {error_output}",
                )

            return self._parse_output(output, title)

        except asyncio.TimeoutError:
            raise AgentTimeoutError(
                self.name,
                f"Commit/push timed out after {self.timeout}s",
            )
        except AgentError:
            raise
        except Exception as e:
            raise AgentError(self.name, f"Commit/push failed: {str(e)}", e)

    async def cleanup_branch(self, repo_path: str, branch_name: str, target_file: str) -> None:
        """
        Clean up after a rejected preview: restore file and delete branch.

        Args:
            repo_path: Path to git repo
            branch_name: Branch to delete
            target_file: File to restore
        """
        try:
            # Restore the file to its original state
            restore_proc = await asyncio.create_subprocess_exec(
                "git", "checkout", "--", target_file,
                cwd=repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await restore_proc.communicate()

            # Switch back to main/master
            for main_branch in ("main", "master"):
                checkout_proc = await asyncio.create_subprocess_exec(
                    "git", "checkout", main_branch,
                    cwd=repo_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await checkout_proc.communicate()
                if checkout_proc.returncode == 0:
                    break

            # Delete the feature branch
            delete_proc = await asyncio.create_subprocess_exec(
                "git", "branch", "-D", branch_name,
                cwd=repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await delete_proc.communicate()

            self.logger.info(f"Cleaned up branch {branch_name}")

        except Exception as e:
            self.logger.warning(f"Branch cleanup failed: {e}")

    def _parse_output(self, output: str, title: str) -> dict[str, Any]:
        """Parse agent output to extract PR details."""
        pr_url = None
        branch_name = None
        files_changed = []
        errors = []

        for line in output.split("\n"):
            stripped = line.strip()

            # Structured tags emitted by agent.py
            if "PR_URL:" in stripped:
                pr_url = stripped.split("PR_URL:", 1)[1].strip()
            elif "BRANCH:" in stripped:
                branch_name = stripped.split("BRANCH:", 1)[1].strip()
            elif "FILES_CHANGED:" in stripped:
                files = stripped.split("FILES_CHANGED:", 1)[1].strip()
                files_changed.extend(f.strip() for f in files.split(",") if f.strip())

            # Fallback: pick up GitHub PR URLs anywhere in output
            elif not pr_url and "github.com" in stripped and "/pull/" in stripped:
                for part in stripped.split():
                    if "github.com" in part and "/pull/" in part:
                        pr_url = part.strip()
                        break

            # Capture error lines
            if stripped.startswith("Failed") or stripped.startswith("Error"):
                errors.append(stripped)

        success = pr_url is not None
        error_msg = None
        if not success:
            if errors:
                error_msg = "; ".join(errors)
            else:
                error_msg = "PR creation failed — no PR URL found in agent output"

        return {
            "title": title,
            "pr_url": pr_url,
            "branch_name": branch_name,
            "files_changed": list(set(files_changed)),
            "success": success,
            "error": error_msg,
        }

    async def health_check(self) -> bool:
        """Check if PR-Agent is accessible and dependencies are available."""
        try:
            if not self.agent_script.exists():
                self.logger.warning("PR-Agent script not found")
                return False

            # Check git is available
            git_proc = await asyncio.create_subprocess_exec(
                "git", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await git_proc.communicate()
            if git_proc.returncode != 0:
                self.logger.warning("git CLI not available")
                return False

            # Check gh is available
            gh_proc = await asyncio.create_subprocess_exec(
                "gh", "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await gh_proc.communicate()
            if gh_proc.returncode != 0:
                self.logger.warning("GitHub CLI (gh) not available")
                return False

            return True
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

        # Verify git CLI is available
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "status",
                cwd=str(repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            if proc.returncode != 0:
                raise ValueError(f"git is not functional in {repo_path}")
        except FileNotFoundError:
            raise ValueError("git CLI is not installed or not in PATH")

        # Verify gh CLI is available
        try:
            proc = await asyncio.create_subprocess_exec(
                "gh", "auth", "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            if proc.returncode != 0:
                raise ValueError("GitHub CLI (gh) is not authenticated — run 'gh auth login'")
        except FileNotFoundError:
            raise ValueError("GitHub CLI (gh) is not installed — install with 'brew install gh'")

        return True
