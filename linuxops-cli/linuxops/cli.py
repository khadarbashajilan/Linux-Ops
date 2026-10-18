"""LinuxOps CLI — Typer app for interacting with the backend."""

import typer
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table
from rich.panel import Panel

from linuxops.client import LinuxOpsClient
from linuxops.config import get_config
from linuxops.ui import spinner_context, print_tool_calls, print_risk_badge

app = typer.Typer(
    name="linuxops",
    help="LinuxOps AI assistant CLI — natural language Linux operations.",
    add_completion=False,
)
console = Console()


@app.command()
def chat(
    message: str = typer.Argument(None, help="One-shot message (omit for REPL mode)"),
    server: str = typer.Option(None, "--server", "-s", help="Backend URL override"),
):
    """Chat with the LinuxOps agent (REPL or one-shot)."""
    cfg = get_config()
    base_url = server or cfg.get("server_url", "http://localhost:8000")
    client = LinuxOpsClient(base_url=base_url, token=cfg.get("api_token"))

    if message:
        _handle_message(client, message)
        return

    # REPL mode
    console.print(
        Panel.fit(
            "[bold cyan]LinuxOps Chat[/bold cyan]\n"
            f"Backend: {base_url}\n"
            "Type your message (Ctrl+C to exit)",
            border_style="cyan",
        )
    )

    try:
        while True:
            try:
                user_input = Prompt.ask("\n[bold green]You[/bold green]")
            except (KeyboardInterrupt, EOFError):
                console.print("\n[yellow]Exiting...[/yellow]")
                break

            if not user_input.strip():
                continue

            _handle_message(client, user_input)
    except KeyboardInterrupt:
        console.print("\n[yellow]Exiting...[/yellow]")


def _handle_message(client: LinuxOpsClient, message: str) -> None:
    """Process one message through the agent and display the result."""
    try:
        with spinner_context("Thinking..."):
            result = client.chat(message)

        # Show tool calls if any
        if result.get("tool_calls"):
            print_tool_calls(result["tool_calls"])

        # Show the response
        console.print(
            Panel(
                result.get("response", "[dim]No response[/dim]"),
                title="[bold blue]Agent[/bold blue]",
                border_style="blue",
                padding=(1, 2),
            )
        )
    except Exception as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")


@app.command()
def health():
    """Check backend health."""
    cfg = get_config()
    base_url = cfg.get("server_url", "http://localhost:8000")
    client = LinuxOpsClient(base_url=base_url, token=cfg.get("api_token"))

    try:
        status = client.health()
        table = Table(title="Backend Health", show_header=False)
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Status", status.get("status", "unknown"))
        table.add_row("Ollama", status.get("ollama", "unknown"))
        if status.get("ollama_latency_ms"):
            table.add_row("Latency", f"{status['ollama_latency_ms']:.1f}ms")
        if status.get("providers"):
            table.add_row("Providers", ", ".join(status["providers"]))

        console.print(table)
    except Exception as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(1)


@app.command()
def history(
    limit: int = typer.Option(20, "--limit", "-l", help="Max conversations to show"),
):
    """Show conversation history."""
    cfg = get_config()
    base_url = cfg.get("server_url", "http://localhost:8000")
    client = LinuxOpsClient(base_url=base_url, token=cfg.get("api_token"))

    try:
        conversations = client.list_conversations(limit=limit)
        if not conversations:
            console.print("[yellow]No conversations found.[/yellow]")
            return

        table = Table(title="Conversation History")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Created", style="green")
        table.add_column("Messages", justify="right")
        table.add_column("Last Message", style="dim")

        for conv in conversations:
            table.add_row(
                conv.get("id", "")[:8],
                conv.get("created_at", "")[:19],
                str(conv.get("message_count", 0)),
                (conv.get("last_message") or "")[:50],
            )

        console.print(table)
    except Exception as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")


@app.command()
def audit(
    limit: int = typer.Option(50, "--limit", "-l", help="Max entries to show"),
):
    """Show audit log (tool executions)."""
    cfg = get_config()
    base_url = cfg.get("server_url", "http://localhost:8000")
    client = LinuxOpsClient(base_url=base_url, token=cfg.get("api_token"))

    try:
        entries = client.get_audit_log(limit=limit)
        if not entries:
            console.print("[yellow]No audit entries found.[/yellow]")
            return

        table = Table(title="Audit Log")
        table.add_column("Time", style="cyan")
        table.add_column("Tool", style="green")
        table.add_column("Risk", justify="center")
        table.add_column("Status", justify="center")
        table.add_column("Args", style="dim")

        for entry in entries:
            risk = entry.get("risk_tier", "unknown")
            status = entry.get("status", "unknown")
            risk_display = print_risk_badge(risk)

            table.add_row(
                entry.get("timestamp", "")[:19],
                entry.get("tool_name", ""),
                risk_display,
                f"[{'green' if status == 'executed' else 'yellow' if status == 'confirmed' else 'red'}]{status}[/]",
                str(entry.get("arguments", ""))[:40],
            )

        console.print(table)
    except Exception as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")


@app.command()
def config(
    server_url: str = typer.Option(None, "--server", help="Set backend URL"),
    token: str = typer.Option(None, "--token", help="Set API token"),
    show: bool = typer.Option(False, "--show", help="Show current config"),
):
    """View or update CLI config (~/.linuxops/config.toml)."""
    from linuxops.config import CONFIG_PATH, set_config_value

    if show or (server_url is None and token is None):
        cfg = get_config()
        console.print(f"[cyan]Config file:[/cyan] {CONFIG_PATH}")
        console.print(f"[cyan]Server URL:[/cyan] {cfg.get('server_url', 'http://localhost:8000')}")
        console.print(f"[cyan]API Token:[/cyan] {cfg.get('api_token', '[not set]')}")
        return

    if server_url:
        set_config_value("server_url", server_url)
        console.print(f"[green]✓[/green] server_url = {server_url}")

    if token:
        set_config_value("api_token", token)
        console.print(f"[green]✓[/green] api_token = [dim]{token[:8]}...[/dim]")


if __name__ == "__main__":
    app()
