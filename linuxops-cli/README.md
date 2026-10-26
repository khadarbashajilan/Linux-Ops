# LinuxOps CLI

Thin command-line client for the LinuxOps backend. All agent logic lives in the
backend; the CLI only sends HTTP requests and renders the replies.

## Setup

Uses its own uv-managed virtualenv (`linuxops-cli/.venv`, Python 3.14):

```bash
cd linuxops-cli
uv sync                 # creates .venv and installs the CLI + dev tools
uv run linuxops --help
```

Or install it as a global command: `uv tool install ./linuxops-cli`.

The backend must be running (`cd Backend && uv run uvicorn app.main:app`).

## Usage

```bash
linuxops chat                                  # interactive
linuxops chat "what's in my home folder?"      # one-shot (exit code 1 on error)
linuxops health                                # backend + Ollama status
linuxops config                                # show effective config
linuxops config --server http://localhost:8000 # save backend URL
linuxops config --token <token>                # save API token
```

`chat` and `health` accept `--server/-s` to override the backend URL.

## Configuration

Precedence: `--server` flag > environment > `~/.linuxops/config.toml` > default.

| Setting | Env var | Default |
|---|---|---|
| `server_url` | `LINUXOPS_SERVER_URL` | `http://localhost:8000` |
| `api_token` | `LINUXOPS_API_TOKEN` | not set |

The config file is written with `0600` permissions and tokens are masked on display.

## Development

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest
```
