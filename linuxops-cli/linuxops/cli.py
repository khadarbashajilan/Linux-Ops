"""LinuxOps CLI — Typer app that talks to the backend over HTTP."""

from typing import Annotated

import typer
from rich.prompt import Prompt

from linuxops import config, ui
from linuxops.client import BackendError, LinuxOpsClient

app = typer.Typer(
    name="linuxops",
    help="LinuxOps AI assistant — natural-language Linux operations.",
    add_completion=False,
    no_args_is_help=True,
)

ServerOption = Annotated[
    str | None,
    typer.Option("--server", "-s", help="Backend URL (overrides env and config)."),
]


def _client(server: str | None) -> LinuxOpsClient:
    """Build a client from the resolved server URL and token."""
    return LinuxOpsClient(config.resolve_server_url(server), token=config.resolve_api_token())


def _send(client: LinuxOpsClient, message: str) -> bool:
    """Send one message and render the reply.

    Returns:
        True on success, False if the backend reported an error.

    """
    try:
        with ui.spinner("Thinking..."):
            result = client.chat(message)
    except BackendError as exc:
        ui.print_error(str(exc))
        return False
    ui.print_answer(result.get("response", ""), result.get("tool_calls", []))
    return True


@app.command()
def chat(
    message: Annotated[
        str | None, typer.Argument(help="One-shot message (omit for interactive mode).")
    ] = None,
    server: ServerOption = None,
) -> None:
    """Chat with the LinuxOps agent (interactive or one-shot)."""
    with _client(server) as client:
        if message:
            if not _send(client, message):
                raise typer.Exit(1)
            return

        ui.console.print(f"[bold cyan]LinuxOps chat[/] · {client.base_url} · Ctrl+C to exit")
        while True:
            try:
                user_input = Prompt.ask("\n[bold green]You[/bold green]").strip()
            except (KeyboardInterrupt, EOFError):
                ui.console.print("\n[yellow]Bye.[/yellow]")
                return
            if user_input:
                _send(client, user_input)


@app.command()
def health(server: ServerOption = None) -> None:
    """Check backend and Ollama health."""
    with _client(server) as client:
        try:
            status = client.health()
        except BackendError as exc:
            ui.print_error(str(exc))
            raise typer.Exit(1) from exc
        ui.print_health(status, client.base_url)


@app.command("config")
def config_cmd(
    server_url: Annotated[str | None, typer.Option("--server", help="Save backend URL.")] = None,
    token: Annotated[str | None, typer.Option("--token", help="Save API token.")] = None,
) -> None:
    """Show the effective config, or save new values to ~/.linuxops/config.toml."""
    if server_url is None and token is None:
        ui.console.print(f"[cyan]Config file:[/cyan] {config.CONFIG_PATH}")
        ui.console.print(f"[cyan]Server URL:[/cyan]  {config.resolve_server_url()}")
        ui.console.print(
            f"[cyan]API token:[/cyan]   {config.mask_token(config.resolve_api_token())}"
        )
        return
    if server_url:
        config.save_config_value("server_url", server_url)
        ui.print_success(f"server_url = {server_url}")
    if token:
        config.save_config_value("api_token", token)
        ui.print_success(f"api_token = {config.mask_token(token)}")
