"""Rich rendering helpers for CLI output."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

_HEALTH_STYLE = {"ok": "green", "degraded": "yellow"}


@contextmanager
def spinner(message: str) -> Iterator[None]:
    """Show a transient spinner while the wrapped block runs."""
    with console.status(message, spinner="dots"):
        yield


def print_answer(answer: str, tool_calls: list[str]) -> None:
    """Render the tools the agent used, then its answer."""
    if tool_calls:
        console.print(f"[dim]tools used:[/dim] [cyan]{', '.join(tool_calls)}[/cyan]")
    body = Text(answer) if answer else Text("No response", style="dim")
    console.print(Panel(body, title="[bold blue]Agent[/bold blue]"))


def print_health(health: dict[str, Any], base_url: str) -> None:
    """Render the backend health payload as a table."""
    status = health.get("status", "unknown")
    table = Table(title="Backend Health", show_header=False)
    table.add_column("Key", style="cyan")
    table.add_column("Value")
    table.add_row("Backend", base_url)
    table.add_row("Status", f"[{_HEALTH_STYLE.get(status, 'red')}]{status}[/]")
    table.add_row("Ollama", health.get("ollama", "unknown"))
    table.add_row("Model", health.get("model", "unknown"))
    latency = health.get("ollama_latency_ms")
    if latency is not None:
        table.add_row("Latency", f"{latency:.1f} ms")
    console.print(table)


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold red]✗[/bold red] {message}")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold green]✓[/bold green] {message}")
