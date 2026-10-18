# LinuxOps CLI

Command-line interface for the LinuxOps AI assistant. A thin client that communicates with the FastAPI backend over HTTP.

## Installation

```bash
cd linuxops-cli
pip install -e .
```

## Usage

### Chat (REPL mode)

```bash
linuxops chat
```

### Chat (one-shot)

```bash
linuxops chat "what files are in my home folder?"
```

### Check backend health

```bash
linuxops health
```

### View conversation history

```bash
linuxops history
linuxops history --limit 10
```

### View audit log

```bash
linuxops audit
linuxops audit --limit 100
```

### Configure

```bash
# Set backend URL
linuxops config --server http://localhost:8000

# Set API token
linuxops config --token your-token-here

# Show current config
linuxops config --show
```

## Configuration

Config is stored in `~/.linuxops/config.toml`:

```toml
server_url = "http://localhost:8000"
api_token = ""
```

Environment variables override config file:

- `LINUXOPS_SERVER_URL` — backend URL
- `LINUXOPS_API_TOKEN` — API token

## Architecture

The CLI is a **thin client** — all agent logic lives in the backend. It just:

1. Sends HTTP requests to the FastAPI backend
2. Displays responses with Rich formatting
3. Handles tool approval prompts (when Phase 02 safety is enabled)

No LLM calls, no tool execution, no state management — that's all in the backend.
