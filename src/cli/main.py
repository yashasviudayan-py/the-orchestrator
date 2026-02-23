"""
Phase 4: Commander CLI - Unified terminal interface for The Orchestrator.
"""

import asyncio
import logging
import sys
from typing import Optional

import click
import uvicorn
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

console = Console()


def setup_logging(verbose: bool) -> None:
    """Configure logging with Rich handler."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
    )


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging.")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """The Orchestrator - Local AI agent coordination system."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    setup_logging(verbose)


@cli.command()
@click.option("--host", default="0.0.0.0", show_default=True, help="Host to bind to.")
@click.option("--port", default=8080, show_default=True, help="Port to listen on.")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development.")
@click.pass_context
def serve(ctx: click.Context, host: str, port: int, reload: bool) -> None:
    """Start the Command Center web server."""
    banner = r"""[bold white]
       /\
      /  \        ___  ____   ____ _   _ _____ ____ _____ ____      _  _____ ___  ____
     / /\ \      / _ \|  _ \ / ___| | | | ____/ ___|_   _|  _ \   / \|_   _/ _ \|  _ \
    / /__\ \    | | | | |_) | |   | |_| |  _| \___ \ | | | |_) | / _ \ | || | | | |_) |
   /  ____  \   | |_| |  _ <| |___|  _  | |___ ___) || | |  _ < / ___ \| || |_| |  _ <
  / /      \ \   \___/|_| \_\\____|_| |_|_____|____/ |_| |_| \_/_/   \_|_| \___/|_| \_\
 /_/        \_\
[/bold white]"""
    console.print(banner)
    console.print(f"[bold green]Starting Command Center on http://{host}:{port}[/bold green]")
    if reload:
        # String form required for reload mode (uvicorn watches files)
        uvicorn.run(
            "src.web.server:app",
            host=host,
            port=port,
            reload=True,
            log_level="debug" if ctx.obj.get("verbose") else "info",
        )
    else:
        from ..web.server import app
        uvicorn.run(
            app,
            host=host,
            port=port,
            reload=False,
            log_level="debug" if ctx.obj.get("verbose") else "info",
        )


@cli.command()
@click.argument("objective")
@click.option("--max-iterations", default=10, show_default=True, help="Max agent iterations.")
@click.option(
    "--strategy",
    type=click.Choice(["adaptive", "research_first", "context_first"], case_sensitive=False),
    default="adaptive",
    show_default=True,
    help="Routing strategy.",
)
@click.pass_context
def run(ctx: click.Context, objective: str, max_iterations: int, strategy: str) -> None:
    """Run an orchestration task directly from the terminal."""
    asyncio.run(_run_task(objective, max_iterations, strategy))


async def _run_task(objective: str, max_iterations: int, strategy: str) -> None:
    """Execute a task using the orchestrator."""
    try:
        from ..config import get_settings
        from ..agents import ResearchAgentInterface, ContextCoreInterface, PRAgentInterface
        from ..orchestrator.graph_v2 import EnhancedOrchestratorGraph
        from ..orchestrator.supervisor import RoutingStrategy

        settings = get_settings()

        console.print(f"[bold]Objective:[/bold] {objective}")
        console.print(f"[bold]Strategy:[/bold] {strategy}")
        console.print(f"[bold]Max iterations:[/bold] {max_iterations}")
        console.rule()

        # Initialize agents
        research_agent = ResearchAgentInterface(settings.research_agent_url)
        context_agent = ContextCoreInterface(settings.context_core_path)
        pr_agent = PRAgentInterface(settings.pr_agent_path)

        # Map strategy string to enum
        strategy_map = {
            "adaptive": RoutingStrategy.ADAPTIVE,
            "research_first": RoutingStrategy.RESEARCH_FIRST,
            "context_first": RoutingStrategy.CONTEXT_FIRST,
        }
        routing_strategy = strategy_map[strategy.lower()]

        # Build and run graph
        graph = EnhancedOrchestratorGraph(
            research_agent=research_agent,
            context_agent=context_agent,
            pr_agent=pr_agent,
            llm_base_url=settings.ollama_base_url,
            llm_model=settings.ollama_model,
            routing_strategy=routing_strategy,
        )

        async def progress_callback(state_dict: dict) -> None:
            current = state_dict.get("current_agent")
            iteration = state_dict.get("iteration", 0)
            if current:
                console.print(f"  [cyan]Iteration {iteration}:[/cyan] calling [bold]{current}[/bold]")

        final_state = await graph.run(
            objective=objective,
            max_iterations=max_iterations,
            routing_strategy=routing_strategy,
            progress_callback=progress_callback,
        )

        console.rule()
        console.print(f"[bold]Status:[/bold] {final_state.status.value}")
        if final_state.final_output:
            console.print("\n[bold green]Result:[/bold green]")
            console.print(final_state.final_output)
        if final_state.errors:
            console.print("\n[bold red]Errors:[/bold red]")
            for err in final_state.errors:
                console.print(f"  - {err}")

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)


@cli.command()
def status() -> None:
    """Check health of all system components."""
    asyncio.run(_check_status())


async def _check_status() -> None:
    """Run health checks and display results."""
    try:
        from ..web.health_monitor import get_health_monitor

        monitor = get_health_monitor()
        console.print("[bold]Checking system health...[/bold]")

        health = await monitor.check_all()
        overall = monitor.get_overall_status(health)

        table = Table(title="System Health")
        table.add_column("Service", style="bold")
        table.add_column("Status")

        status_colors = {
            "healthy": "green",
            "degraded": "yellow",
            "down": "red",
        }

        for service, agent_status in health.items():
            color = status_colors.get(agent_status.value, "white")
            table.add_row(service, f"[{color}]{agent_status.value.upper()}[/{color}]")

        console.print(table)

        overall_color = status_colors.get(overall, "white")
        console.print(f"\n[bold]Overall:[/bold] [{overall_color}]{overall.upper()}[/{overall_color}]")

    except Exception as e:
        console.print(f"[bold red]Health check failed:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
