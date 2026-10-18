"""Rich UI helpers for CLI output."""

from rich.console import Console
from rich.spinner import Spinner
from rich.live import Live
from rich.table import Table
from rich.text import Text
import time
from contextlib import contextmanager

console = Console()


@contextmanager
def spinner_context(message: str):
    """Context manager for a spinner with a message.

    Args:
        message: Text to display next to the spinner.
    """
    with Live(Spinner("dots", text=message), console=console, transient=True):
        yield


def print_tool_calls(tool_calls: list[dict]) -> None:
    """Display tool calls in a formatted table.

    Args:
        tool_calls: List of tool call dicts from the API response.
    """
    if not tool_calls:
        return

    table = Table(title="Tool Calls", show_header=True, header_style="bold magenta")
    table.add_column("Tool", style="cyan")
    table.add_column("Arguments", style="dim")

    for call in tool_calls:
        name = call.get("name", "unknown")
        args = call.get("arguments", {})
        args_str = ", ".join(f"{k}={v!r}" for k, v in args.items())[:60]
        table.add_row(name, args_str)

    console.print(table)


def print_risk_badge(risk: str) -> str:
    """Return a colored badge for a risk tier.

    Args:
        risk: Risk tier string (safe, confirm, block).

    Returns:
        Rich-formatted string with colored badge.
    """
    badges = {
        "safe": "[bold green]🟢 safe[/bold green]",
        "confirm": "[bold yellow]🟡 confirm[/bold yellow]",
        "block": "[bold red]🔴 block[/bold red]",
    }
    return badges.get(risk.lower(), f"[dim]{risk}[/dim]")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold green]✓[/bold green] {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[bold red]✗[/bold red] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold yellow]⚠[/bold yellow] {message}")
