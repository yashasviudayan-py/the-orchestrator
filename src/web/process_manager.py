"""
Process Manager for The Orchestrator

Provides async start/stop control over local services (Ollama, Redis).
External agent projects are not controllable from here.
"""

import asyncio
import logging
import shutil
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# Service Configuration
# ═══════════════════════════════════════════════════════════════════════

_SERVICE_CONFIGS = {
    "ollama": {
        "start": ["ollama", "serve"],
        "stop": ["pkill", "-f", "ollama serve"],
        "controllable": True,
        "long_running": True,  # daemon process — don't wait for exit
    },
    "redis": {
        "start": ["brew", "services", "start", "redis"],
        "stop": ["brew", "services", "stop", "redis"],
        "controllable": True,
        "long_running": False,
    },
    "research": {"controllable": False},
    "context": {"controllable": False},
    "pr": {"controllable": False},
}


# ═══════════════════════════════════════════════════════════════════════
# Exceptions
# ═══════════════════════════════════════════════════════════════════════

class ServiceNotControllableError(Exception):
    """Raised when trying to start/stop a service that cannot be managed here."""


# ═══════════════════════════════════════════════════════════════════════
# ProcessManager
# ═══════════════════════════════════════════════════════════════════════

class ProcessManager:
    """Manages local service lifecycle (Ollama, Redis)."""

    def __init__(self):
        self._handles: dict = {}  # store subprocess handles for long-running daemons

    def is_controllable(self, service: str) -> bool:
        """Return True if the service can be started/stopped by this manager."""
        cfg = _SERVICE_CONFIGS.get(service)
        return bool(cfg and cfg.get("controllable"))

    async def start_service(self, service: str) -> Tuple[bool, str]:
        """
        Start a service.

        Returns:
            (success, message)

        Raises:
            ServiceNotControllableError: if the service is not controllable.
        """
        cfg = _SERVICE_CONFIGS.get(service)
        if not cfg or not cfg.get("controllable"):
            raise ServiceNotControllableError(
                f"Service '{service}' cannot be started from the web UI. "
                "Start it manually from the terminal."
            )

        cmd = cfg["start"]
        binary = cmd[0]

        # Verify the binary exists
        if not shutil.which(binary):
            return False, f"Command '{binary}' not found. Is it installed?"

        try:
            if cfg.get("long_running"):
                # For daemons (e.g. ollama serve) — start detached, don't await
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                self._handles[service] = proc
                logger.info(f"Started {service} (pid {proc.pid})")
                return True, f"{service} started (pid {proc.pid})"
            else:
                # Short-lived management commands (e.g. brew services start redis)
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15.0)
                except asyncio.TimeoutError:
                    proc.kill()
                    return False, f"Timed out starting {service}"

                if proc.returncode == 0:
                    logger.info(f"Started {service}")
                    return True, f"{service} started successfully"
                else:
                    err = stderr.decode().strip() if stderr else "unknown error"
                    logger.warning(f"Failed to start {service}: {err}")
                    return False, f"Failed to start {service}: {err}"

        except Exception as e:
            logger.error(f"Error starting {service}: {e}", exc_info=True)
            return False, f"Error: {str(e)}"

    async def stop_service(self, service: str) -> Tuple[bool, str]:
        """
        Stop a service.

        Returns:
            (success, message)

        Raises:
            ServiceNotControllableError: if the service is not controllable.
        """
        cfg = _SERVICE_CONFIGS.get(service)
        if not cfg or not cfg.get("controllable"):
            raise ServiceNotControllableError(
                f"Service '{service}' cannot be stopped from the web UI."
            )

        cmd = cfg["stop"]
        binary = cmd[0]

        # If we have a stored handle (for long-running daemons), terminate it
        if service in self._handles:
            proc = self._handles.pop(service)
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5.0)
                logger.info(f"Terminated {service} subprocess")
                return True, f"{service} stopped"
            except Exception:
                proc.kill()
                return True, f"{service} force-killed"

        # Otherwise run the stop command
        if not shutil.which(binary):
            return False, f"Command '{binary}' not found."

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            except asyncio.TimeoutError:
                proc.kill()
                return False, f"Timed out stopping {service}"

            if proc.returncode == 0:
                logger.info(f"Stopped {service}")
                return True, f"{service} stopped successfully"
            else:
                err = stderr.decode().strip() if stderr else "unknown error"
                # pkill returns 1 if no process found — treat as "already stopped"
                if "no process" in err.lower() or proc.returncode == 1:
                    return True, f"{service} was not running"
                logger.warning(f"Failed to stop {service}: {err}")
                return False, f"Failed to stop {service}: {err}"

        except Exception as e:
            logger.error(f"Error stopping {service}: {e}", exc_info=True)
            return False, f"Error: {str(e)}"


# ═══════════════════════════════════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════════════════════════════════

_process_manager: Optional[ProcessManager] = None


def get_process_manager() -> ProcessManager:
    """Get the global ProcessManager instance."""
    global _process_manager
    if _process_manager is None:
        _process_manager = ProcessManager()
    return _process_manager
