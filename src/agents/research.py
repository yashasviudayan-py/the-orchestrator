"""
Research Agent interface - integrates with local-research-agent via HTTP API.
"""

import asyncio
from typing import Any
import httpx

from .base import (
    AgentInterface,
    AgentError,
    AgentConnectionError,
    AgentTimeoutError,
)


class ResearchAgentInterface(AgentInterface):
    """Interface to Research Agent HTTP API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 300.0,  # 5 minutes for research
    ):
        """
        Initialize Research Agent interface.

        Args:
            base_url: Base URL for Research Agent API
            timeout: Request timeout in seconds
        """
        super().__init__("research")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def execute(self, task_input: dict[str, Any]) -> dict[str, Any]:
        """
        Execute research task.

        Args:
            task_input: Must contain 'topic' key

        Returns:
            Research results dict with:
                - topic: str
                - summary: str
                - urls: list[str]
                - key_findings: list[str]
                - report_path: str
                - elapsed_ms: float

        Raises:
            AgentError: If research fails
        """
        try:
            await self.validate_input(task_input)

            topic = task_input["topic"]
            self.logger.info(f"Starting research on: {topic}")

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Start research job
                response = await client.post(
                    f"{self.base_url}/api/research",
                    json={"topic": topic},
                )

                # Handle 409 (job already running) - try to get existing job
                if response.status_code == 409:
                    self.logger.warning("Research job already running - checking for latest job")
                    result = await self._get_latest_job_result(client, topic)
                    if result:
                        self.logger.info("Retrieved results from existing job")
                        self._log_execution(task_input, result)
                        return result
                    else:
                        raise AgentError(
                            self.name,
                            "Research job already running and no completed results available",
                        )

                if response.status_code != 200:
                    raise AgentError(
                        self.name,
                        f"Research API returned {response.status_code}: {response.text}",
                    )

                data = response.json()
                job_id = data.get("job_id")  # API returns "job_id", not "id"

                if not job_id:
                    raise AgentError(self.name, "No job ID returned from research API")

                # Poll for completion (simplified - could use SSE in future)
                result = await self._poll_for_completion(client, job_id)

                self._log_execution(task_input, result)
                return result

        except httpx.ConnectError as e:
            raise AgentConnectionError(
                self.name,
                f"Cannot connect to Research Agent at {self.base_url}",
                e,
            )
        except httpx.TimeoutException as e:
            raise AgentTimeoutError(
                self.name,
                f"Research timed out after {self.timeout}s",
                e,
            )
        except AgentError:
            raise
        except Exception as e:
            raise AgentError(self.name, f"Unexpected error: {str(e)}", e)

    async def _get_latest_job_result(
        self,
        client: httpx.AsyncClient,
        topic: str,
    ) -> dict[str, Any] | None:
        """
        Try to get results from the latest completed research job.

        When a job is already running (409), we can either wait for it or
        retrieve results from a recently completed job with the same topic.
        """
        try:
            # Get list of all reports
            response = await client.get(f"{self.base_url}/api/reports")

            if response.status_code == 200:
                reports = response.json()

                # Find most recent report (reports should be sorted by timestamp)
                if reports and len(reports) > 0:
                    # Get the most recent report
                    latest = reports[0]
                    report_id = latest.get("id")

                    if report_id:
                        self.logger.info(f"Found latest completed report {report_id}")
                        # Get the full report
                        report_response = await client.get(
                            f"{self.base_url}/api/reports/{report_id}"
                        )

                        if report_response.status_code == 200:
                            data = report_response.json()
                            return {
                                "topic": data.get("topic", topic),
                                "summary": self._extract_summary(data.get("content", "")),
                                "urls": data.get("urls", []),
                                "key_findings": self._extract_key_findings(
                                    data.get("content", "")
                                ),
                                "report_path": f"reports/{report_id}.md",
                                "elapsed_ms": data.get("elapsed_ms", 0.0),
                            }

            return None

        except Exception as e:
            self.logger.warning(f"Could not retrieve latest report: {e}")
            return None

    async def _poll_for_completion(
        self,
        client: httpx.AsyncClient,
        job_id: str,
        poll_interval: float = 2.0,
    ) -> dict[str, Any]:
        """Poll for job completion."""
        max_polls = int(self.timeout / poll_interval)

        for _ in range(max_polls):
            response = await client.get(f"{self.base_url}/api/reports/{job_id}")

            if response.status_code == 200:
                # Job complete - get report
                data = response.json()
                return {
                    "topic": data.get("topic", ""),
                    "summary": self._extract_summary(data.get("content", "")),
                    "urls": data.get("urls", []),
                    "key_findings": self._extract_key_findings(
                        data.get("content", "")
                    ),
                    "report_path": f"reports/{job_id}.md",
                    "elapsed_ms": data.get("elapsed_ms", 0.0),
                }
            elif response.status_code == 404:
                # Still processing
                await asyncio.sleep(poll_interval)
                continue
            else:
                raise AgentError(
                    self.name,
                    f"Unexpected status {response.status_code} while polling",
                )

        raise AgentTimeoutError(
            self.name,
            f"Research did not complete within {self.timeout}s",
        )

    def _extract_summary(self, content: str, max_length: int = 500) -> str:
        """Extract summary from research report."""
        # Simple extraction - take first paragraph or N characters
        lines = content.split("\n\n")
        summary = lines[0] if lines else content[:max_length]
        return summary.strip()

    def _extract_key_findings(self, content: str, max_findings: int = 5) -> list[str]:
        """Extract key findings from research report."""
        # Look for bullet points or numbered lists
        findings = []
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("-") or stripped.startswith("*"):
                findings.append(stripped[1:].strip())
            elif len(stripped) > 0 and stripped[0].isdigit() and "." in stripped:
                findings.append(stripped.split(".", 1)[1].strip())

            if len(findings) >= max_findings:
                break

        return findings

    async def health_check(self) -> bool:
        """Check if Research Agent API is accessible."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/health")
                return response.status_code == 200
        except Exception as e:
            self.logger.warning(f"Health check failed: {e}")
            return False

    async def validate_input(self, task_input: dict[str, Any]) -> bool:
        """Validate research task input."""
        if "topic" not in task_input:
            raise ValueError("Research task input must contain 'topic'")

        topic = task_input["topic"]
        if not isinstance(topic, str) or len(topic.strip()) == 0:
            raise ValueError("Topic must be a non-empty string")

        return True
