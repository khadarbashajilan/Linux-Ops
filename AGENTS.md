# AGENTS.md — LinuxOps Repo Memory

> Repository memory for AI agents + owner. Keep this file current. Append dated entries to the Progress Log at the end of every working session. If this file and the code disagree, the code wins — update this file.

---

## Project

**LinuxOps** — a local AI Linux system assistant. It checks system state by running read-only commands itself (allowlisted catalog, no shell), **suggests** anything that changes the system (Phase 01), then **asks permission** before running it (Phase 02). Replanned 2026-10-26 (v2) — see vault blueprint.

- Notebook project for portfolio / interview use (agentic tool-use + safety engineering).
- **Alternative codenames considered:** none in use. Blueprint says "rename freely".
- **Status:** Phase 00 (foundation) done + cleaned up 2026-10-26; Phase 01 next.
- **Timeline target:** ~3.5 weeks remaining, phased.

## What this project is trying to prove (interview story)

1. **Agentic tool-use** — LLM *decides* which typed tool to call with what args; not a chatbot wrapper.
2. **Safety / guardrails engineering** — 3-tier risk classifier + human-in-the-loop confirmation + full audit log. The differentiator.
3. **Clean architecture** — thin CLI client + FastAPI backend owning all agent logic (optional Next.js later).
4. **Local-first LLM via Ollama** — `qwen3:4b` running locally in Docker, no external API keys, no rate limits.
5. **Observability** — audit trail of every agent action, replayable.

## Stack

| Layer | Choice | Notes |
|---|---|---|
| Backend | FastAPI | async, `api/` package, `create_app()` |
| Agent loop | Plain Python, hand-rolled ReAct | NO LangChain/LangGraph in v1 — build the loop yourself, from scratch |
| CLI | Typer + `rich` | thin HTTP client, primary interface |
| Frontend | Next.js (App Router) + Tailwind | **optional**, Phase 03 |
| LLM | Ollama `qwen3:4b` (local via Docker) | single `OllamaProvider`, no failover |
| DB | SQLite + SQLModel + WAL | pending actions + audit log (Phase 02) |
| Memory (stretch) | ChromaDB (local, embedded) | do NOT build pre-MVP |
| System tools | psutil + allowlisted `run_command` (`create_subprocess_exec`, never a shell) | typed, validated tools only |

## Architecture map

```
CLI ── HTTP ── FastAPI (api/) ── Agent loop (core/agent.py) ── LLMProvider (Ollama qwen3:4b, Docker)
                                      │
                                      └── Tool registry ── list_dir / read_file (3-layer fs scope)
                                                     + Phase 01: psutil status tools
                                                     + Phase 01: run_command → classifier → executor (no shell)
                                                     + Phase 02: confirm gate + SQLite audit log
```

**Hard rules (do not violate):**
- The LLM **never** gets to build raw shell strings that hit `subprocess.run(shell=True)`. Only pre-defined, parameterized, schema-validated tools execute anything. This is the #1 interview talking point AND a safety invariant.
- Every tool call — executed, confirmed, or **denied** — is written to the audit log.
- Never touch denylisted paths without explicit typed override: `/etc`, `/boot`, `/sys`, `~/.ssh`.

## Folder structure (current; `+` = planned)

```
Linux-Ops/
├── Backend/                # FastAPI app — agent core (capital B; code wins over docs)
│   ├── .venv/              # uv-managed, Python 3.14 (.python-version) — git-ignored
│   ├── .env                # Ollama + scope config — git-ignored (see .env.example)
│   ├── pyproject.toml      # deps, ruff, pytest config
│   ├── app/
│   │   ├── main.py         # create_app(): lifespan + error handling + routes. No logic.
│   │   ├── api/            # schemas.py, deps.py (get_agent), errors.py (request id + handlers), routes.py
│   │   ├── core/           # config.py (settings + fs scope), agent.py (tool loop)
│   │   │                   #   + prompts.py, commands.py, safety.py, executor.py (Phase 01)
│   │   ├── llm/            # base.py (Protocol + TypedDicts), ollama_provider.py, errors.py
│   │   ├── tools/          # registry.py (@tool), file_tools.py (list_dir, read_file)
│   │   │                   #   + system_tools.py, command_tools.py (Phase 01)
│   │   └── db/             # + SQLite audit / pending actions (Phase 02)
│   └── tests/              # pytest — scope, registry, agent, provider, api
├── linuxops-cli/           # Typer thin client — own uv .venv (Python 3.14), own tests
├── frontend/               # + optional Next.js (Phase 03)
└── docs/linuxops/          # Obsidian vault — LOCAL ONLY, git-ignored, source of truth for plan
```

**Endpoints:** now `GET /health`, `POST /chat`. Planned: `POST /tools/approve`, `GET /audit-log` (Phase 02), `GET /system/stats` (Phase 03, optional).

## Phases (build order, gated)

Vault notes (`docs/linuxops/`) are the detailed source of truth. These are the repo-level tracker.

| Phase | File in vault | Focus | Status | Milestone = done when |
|---|---|---|---|---|
| 00 — Foundation | `docs/linuxops/Phase 00 — Foundation.md` | FastAPI + Ollama provider + `@tool` registry + file tools (was v1 "Phase 01 — Pipeline") | ✅ done | `curl POST /chat` "what's in my home folder?" returns a real `list_dir` result; `GET /health` 200 |
| 01 — Observe & Suggest | `docs/linuxops/Phase 01 — Observe & Suggest.md` | carry-over fixes + psutil status tools + allowlisted `run_command` + classifier/executor + suggestions + tests | ⬜ todo | "why is my system slow?" chains 2+ real tool calls; "free up disk space" returns suggestions, nothing unsafe executed; pytest green |
| 02 — Permission Gate | `docs/linuxops/Phase 02 — Permission Gate.md` | 🟡 confirm / 🔴 block tiers + agent pause/resume + `POST /tools/approve` + SQLite audit + CLI y/n | ⬜ todo | kill CPU hog only after y/n; "delete /etc/passwd" blocked + audit row; tested in VM/Docker |
| 03 — Interfaces & Polish | `docs/linuxops/Phase 03 — Interfaces & Polish.md` | CLI polish + packaging + README + demo; Next.js optional | ⬜ todo | stranger installs from README and understands safety model from demo |

Rule: **finish a phase's milestone before starting the next one.** Do not touch stretch features before Phase 03. v1 phase notes archived in `docs/linuxops/_archive/2026-10-26-v1-plan/`.

## Key decisions (locked)

1. CLI is a **thin client** — calls the FastAPI backend over HTTP/WS exactly like the web UI. No agent logic in the CLI. One source of truth.
2. Tool definitions via `@tool` decorator + Pydantic models; JSON schemas auto-generated from the models (DRY).
3. LLM via **Ollama** (local, `qwen3:4b`) — no external API keys, no rate limits, no cost. `LLMProvider` Protocol kept for clean abstraction; swapping models is a one-line env var change.
4. Risk is classified by code on the parsed argv (catalog + per-command validators, default deny), never by the LLM. Phase 01: 🟢 safe runs / everything else **suggested**. Phase 02: 🟢 auto / 🟡 confirm (y/n) / 🔴 block. Denials and suggestions get logged too.
5. v2 scope (2026-10-26): diagnose-first — system status (CPU/mem/disk/procs → network → services/logs → hardware) + suggestions + permission gate. CLI first; Next.js optional (Phase 03). No sudo executed by the agent. No generic file readers (`cat`/`grep`/…) in the command catalog — file reads go through `read_file` scope checks.
6. Design the safety layer as a distinct module, not an afterthought.

## Vault note

- Obsidian vault lives in `docs/linuxops/` — **git-ignored on purpose, never commit it** (decision 2026-09-21).
- Vault = plan source of truth: `index.md` hub → blueprint (v2) + learning topics + phase notes 00–03.
- Keep coordination between this file and vault phase notes / status fields in sync.

## How to run

> Each package has its own uv-managed `.venv` (Python 3.14). Never `pip install` into system Python.
> - Backend: `cd Backend && uv sync && uv run uvicorn app.main:app` (avoid `--reload` once write tools return)
> - CLI: `cd linuxops-cli && uv sync && uv run linuxops chat` (or `uv tool install ./linuxops-cli`)
> - Verify gate (both packages): `uv run ruff check . && uv run ruff format --check . && uv run pytest`

## Environment variables

> Set in `Backend/.env` (git-ignored; template in `Backend/.env.example`):
> - `OLLAMA_BASE_URL` (default `http://localhost:11434`)
> - `OLLAMA_MODEL=qwen3:4b`
> - `LINUXOPS_ALLOWED_PATHS` (extra read/write/exec scope on top of implicit defaults; `:`/`,`-separated; `~`-expanded)
> - `LINUXOPS_DENIED_PATHS` (extra hard-deny on top of seeded list)
> - `LINUXOPS_API_TOKEN` (local auth, single-user — Phase 03)
> - `LINUXOPS_DB_PATH` (SQLite location, default local — Phase 04)

### Filesystem scope model (3 layers, deny wins)

| Capability | Implicit scope | Hard deny (always on) | Env can override? |
|---|---|---|---|
| read (`list_dir`, `read_file`) | `~` + cwd + `LINUXOPS_ALLOWED_PATHS` | `~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.config/gh`, `/etc`, `/boot`, `/sys`, `/proc`, `.env*`, + `LINUXOPS_DENIED_PATHS` | deny: no — allow: yes |
| write (`write_file`) | cwd + `/tmp` + `LINUXOPS_ALLOWED_PATHS` | same | deny: no — allow: yes |
| exec (Phase 02 `run_shell`) | cwd + `LINUXOPS_ALLOWED_PATHS` | same | deny: no — allow: yes |

Realpath resolved before each check (symlinks cannot bypass). `.env*` filenames blocked at any depth. Defense in depth — Phase 02 risk classifier + audit log layers on top.

## Conventions & rules for agents

- **Caveman mode** active (per `~/.config/opencode/AGENTS.caveman.md`). Terse replies, technical exactness, no fluff.
- No code comments unless the user asks.
- Never run destructive Linux operations on the real host — use a disposable VM/Docker for `delete`/`kill`/`run_shell` dev testing.
- Never commit secrets, `.env`, or the docs vault.
- Commit in small Conventional-Commits-style messages, only when asked.
- Phase-gated: do not build a later phase's component before the prior milestone passes.

## Code standards (enforced on every file, esp. `Backend/`)

- PEP 8, 4-space indent, ~100 col soft limit.
- Type hints on every function signature (params + return). No bare `Any` without reason.
- **Docstrings on every module, class, and function — Google style** (`Args:` / `Returns:` / `Raises:` / `Yields:`). Public API never ships without one. This overrides the generic "no comments" rule above — docstrings are required, comments stay minimal.
- Async-first for all I/O (LLM calls, file ops); no blocking calls on async paths.
- Pydantic models at every boundary (requests, tool args, provider responses).
- Small single-purpose functions; no dead code, no commented-out code, no orphan TODO.
- Logging via `logging` (structured), never `print`.
- Secrets via `pydantic.SecretStr`; never logged, never echoed in errors.
- Comments only for non-obvious "why" — the docstring carries the "what".
- Hard safety rules override style (no `shell=True`, typed tools only).
- Enforced with `ruff` (`ruff check` + `ruff format`) at every verify gate.

## Current state (2026-10-26)

- Git: single branch `main`, repo `https://github.com/khadarbashajilan/Linux-Ops.git`. Feature branches merged and deleted.
- `.gitignore` — covers `docs/`, `.env`, `.venv`, `.opencode/`, Python/Node/DB/OS artifacts.
- `.opencode/` — project opencode config (local, git-ignored).
- Vault (v2 plan: index + blueprint + learning topics + phases 00–03) **not** git-tracked by decision.
- `Backend/` — Phase 00 done: FastAPI (`api/` package) + `OllamaProvider` (shared client, working retry, `/api/version` health) + `@tool` registry + `list_dir`/`read_file` with 3-layer scope. `write_file` removed until the Phase 02 gate. 39 tests.
- `linuxops-cli/` — `chat` (one-shot + REPL), `health`, `config`; env/flag precedence; masked token; 0600 config file. 11 tests.

---

## Progress Log

### 2026-10-26 — Session 7: codebase review + v2 replan (docs only, no code changed)
- Review rated codebase 5/10. Verified against local Ollama 0.40.6: `agent.py` sends tool args as JSON string → Ollama rejects 2nd round (`"Value looks like object…"`); dict args work. Also: dead tenacity retry, `/health` runs full chat, ungated `write_file` can overwrite `Backend/app` under `--reload`, CLI `ui.py` crashes on `list[str]` tool_calls, no tests. Full list in vault `Phase 00 — Foundation.md`.
- Replanned to v2: observe (allowlisted `run_command` + psutil) → suggest (Phase 01) → permission gate (Phase 02) → interfaces & polish (Phase 03, Next.js optional).
- Vault rewritten: blueprint v2, `index.md`, new phase notes 00–03, Learning Topics links repointed. Old notes archived in `docs/linuxops/_archive/2026-10-26-v1-plan/`.
- **Next:** Phase 01 step 0 — carry-over fixes, then executor + classifier tests first.

### 2026-10-26 — Session 8: Phase 00 cleanup (readability, modularity, tests) + single-branch
- Backend: split `main.py` into `app/api/` (`schemas`, `deps`, `errors`, `routes`) + `create_app()`; `Agent` takes an `LLMProvider` (router + `ProviderError` removed); `app.state` + `get_agent` dependency replace the global; request-ID middleware echoes `X-Request-ID`; `RequestValidationError` handled.
- Ollama provider: one shared `AsyncClient` closed on shutdown; retry now actually fires (connection errors + 500/503/504); `/health` pings `/api/version`; tool args sent back as dicts (fixes 2nd-round 400); Ollama errors moved to `llm/errors.py`.
- Typing: `TypedDict` messages/tool schemas, `Risk = Literal[...]`. Config: `_unique` helper replaces 3 copy-pasted loops; seeded deny paths resolved (symlinked `$HOME` fix). `read_file`: bounded read, correct `truncated`. Loop cap returns an answer, not 503. `write_file` removed until Phase 02.
- CLI: rewritten typed + ruff-clean; `BackendError` with readable messages; `--server` on all commands; env > file precedence actually used; token masked; config 0600; `tomllib` + `tomli-w`; dropped commands for non-existent endpoints (history/audit/approve).
- Tests: Backend 39 (scope, registry, agent, provider w/ mock transport, api), CLI 11. Both packages own a uv `.venv` pinned to Python 3.14.
- Git: merged `feat/phase03-cli` into `main`, deleted the branch locally + on origin.
- **Next:** Phase 01 — executor + classifier tests first.

### 2026-10-24 — Session 6: draw.io MCP added to opencode config
- Added `mcp.drawio` (local stdio, `npx @drawio/mcp` v1.10.0) to `.opencode/opencode.json` — official jgraph/drawio tool server; diagrams open editable in browser via URL fragment (diagram stays local). `.opencode/` git-ignored, no repo impact.
- First npx run failed: `pako.esm.mjs` in npx cache was corrupted (truncated mid-statement → SyntaxError). Cleared `~/.npm/_npx/56d755bf05e5ecee`, fresh install fixed it.
- Verified standalone: MCP `initialize` + `tools/list` over stdio return serverInfo `drawio-mcp 1.10.0` and tools (`open_drawio_xml`, `open_drawio_mermaid`, `search_shapes`, `open_drawio_csv`, `get_drawio_reference`).
- To activate tools: start a new opencode session (MCP servers load at session start).

### 2026-09-21 — Session 3: Phase 01 complete
- Built `Backend/app`: `core/config.py` (pydantic-settings, `SecretStr`), `llm/` (base Protocol, groq/openrouter/gemini providers, `router.py` 3-tier failover), `tools/` (registry + file_tools), `main.py` (`GET /health`, `POST /chat` agent loop, 5-round cap).
- Sync'd docs: AGENTS.md (`Backend/` casing, fallback chain, Code standards section); vault blueprint/Phase 01/Learning Topics provider updates; opencode `instructions` now loads vault index by absolute path.
- Code standards enforced: Google docstrings everywhere, type hints, ruff clean (`check` + `format`).
- **Milestone passed:** `curl POST /chat "what's in my home folder?"` → real `list_dir` result (58 entries), tool loop logged; `/health` 200. Ran via OpenRouter tier (only key present).
- **Next:** Phase 02 — Safety: ReAct loop hardening, 3-tier risk classifier, confirm gate, audit log, remaining tools (proc/system/app/guarded shell).

### 2026-09-21 — Session 4: config-driven allowlist + auto-cwd
- Symptom: WSL user asked "list current files" → `list_dir` denied; cwd on `/mnt/f` (Windows mount) was outside the hardcoded `(Path.home(), Path("/tmp"))` allowlist.
- Fix: added `LINUXOPS_ALLOWED_PATHS` setting in `core/config.py` (parsed `:`/`,`-separated, `~`-expanded via `Settings.allowed_bases`); `file_tools._allowed_bases()` now returns config bases + `Path.cwd()`, so relative paths (`.`, `./x`) resolve against server cwd and are auto-allowed.
- `.env` set to `~:/tmp:/mnt/f`; `.env.example` documents `~:/tmp`.
- Verified: `/mnt/f` + cwd allowed, `/etc/passwd` still denied, `~/x` OK. `ruff check` + `ruff format` clean.

### 2026-10-16 — Session 5: filesystem scope model (3-layer, deny wins) + `write_file`
- Symptom: `LINUXOPS_ALLOWED_PATHS` was a single env-driven allowlist, no deny layer, no per-capability split. `~` was auto-included for writes — agent could `write_file ~/.ssh/...` if path resolved cleanly; `.env*` filenames were unprotected; user mistake in `.env` could expose `/etc` or `~/.ssh`.
- Fix: 3-layer scope model in `core/config.py` + `tools/file_tools.py`:
  - **Hard deny** (`Settings.denied_bases`) — seeded: `~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.config/gh`, `~/.config/git-credential-manager`, `/etc`, `/boot`, `/sys`, `/proc`. Env-additive only (`LINUXOPS_DENIED_PATHS`), cannot be removed.
  - **Capability allowlist** — `allowed_bases` (read: `~` + cwd + extras), `write_allowed_bases` (write: cwd + `/tmp` + extras, `~` NOT auto-included), `exec_allowed_bases` (exec: cwd only).
  - **Realpath + filename check** — symlinks resolved before either check; `.env*` blocked at any depth.
  - `_check_scope(raw, allowed_tuple)` is the single chokepoint; `_resolve_within_allowlist` deleted.
- Added `write_file` tool (`risk="confirm"`) — write-scoped, will be gated by Phase 02 confirm middleware.
- `.env` + `.env.example` updated; both now document the deny-wins/3-layer model.
- Verified: all 11 hard-deny cases blocked (incl. `~/.ssh`, `~/.aws`, `~/.gnupg`, `/etc`, `/proc`, `/boot`, `/sys`, `.env`, `.env.local`, `./.env`); home + cwd still readable; writes scoped to cwd + `/tmp`; exec scoped to cwd only. `ruff check` + `ruff format` clean.
- AGENTS.md env-vars section updated with scope table.
- **Next:** Phase 02 — risk classifier, confirm gate, audit log, remaining tools (`proc`, `system`, `app`, `run_shell`).