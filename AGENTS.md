# AGENTS.md — LinuxOps Repo Memory

> Repository memory for AI agents + owner. Keep this file current. Append dated entries to the Progress Log at the end of every working session. If this file and the code disagree, the code wins — update this file.

---

## Project

**LinuxOps** — an AI-powered Linux system assistant. Natural language in, real system actions out (files, processes, monitoring, apps) — safely.

- Notebook project for portfolio / interview use (agentic tool-use + safety engineering).
- **Alternative codenames considered:** none in use. Blueprint says "rename freely".
- **Status:** greenfield — planning complete, **zero code written yet**.
- **Timeline target:** 4 weeks, phased.

## What this project is trying to prove (interview story)

1. **Agentic tool-use** — LLM *decides* which typed tool to call with what args; not a chatbot wrapper.
2. **Safety / guardrails engineering** — 3-tier risk classifier + human-in-the-loop confirmation + full audit log. The differentiator.
3. **Full-stack ownership** — CLI + FastAPI + Next.js, one shared backend ("same brain, two interfaces").
4. **Local-first LLM via Ollama** — `qwen3:4b` running locally in Docker, no external API keys, no rate limits.
5. **Observability** — audit trail of every agent action, replayable.

## Stack

| Layer | Choice | Notes |
|---|---|---|
| Backend | FastAPI | async, WebSocket streaming, moderate skill already |
| Agent loop | Plain Python, hand-rolled ReAct | NO LangChain/LangGraph in v1 — build the loop yourself, from scratch |
| CLI | Typer + `rich` | thin client, same HTTP/WS backend as web |
| Frontend | Next.js (App Router) + React + Tailwind | mostly `"use client"` components |
| LLM | Ollama `qwen3:4b` (local via Docker) | single `OllamaProvider`, no failover |
| DB | SQLite + SQLModel/SQLAlchemy + WAL | conversations, messages, tool_calls, audit_log |
| Memory (stretch) | ChromaDB (local, embedded) | do NOT build pre-MVP |
| System tools | psutil, subprocess (NO `shell=True` for LLM strings), shutil, pathlib | typed, validated tools only |

## Architecture map

```
CLI ──┐                         ┌─── Filesystem
Web ──┼── HTTP/WS ── FastAPI ── Agent Core ── Safety Middleware ── Tool Registry ──┼── Processes
      │               REST/WS      │     │        3-tier          (@tool + Pydantic)┼── System stats
      │                            │     └─ decide risk           ──────────────────┼── Apps (xdg-open)
      │                            └── LLM Provider Layer (Ollama qwen3:4b via Docker)
      │
      └── SQLite (conversations / audit)  ·  ChromaDB (stretch memory)
```

**Hard rules (do not violate):**
- The LLM **never** gets to build raw shell strings that hit `subprocess.run(shell=True)`. Only pre-defined, parameterized, schema-validated tools execute anything. This is the #1 interview talking point AND a safety invariant.
- Every tool call — executed, confirmed, or **denied** — is written to the audit log.
- Never touch denylisted paths without explicit typed override: `/etc`, `/boot`, `/sys`, `~/.ssh`.

## Folder structure (target, not built yet)

```
linuxops/
├── Backend/                # FastAPI app — agent core lives here (capital B; code wins over docs)
│   ├── .venv/              # local venv, Python 3.14, uv-managed — git-ignored
│   ├── .env                # API keys + model ids — git-ignored (see .env.example)
│   ├── pyproject.toml
│   └── app/
│       ├── main.py         # FastAPI app + routers
│       ├── core/           # config.py (pydantic-settings); agent.py + safety.py land in Phase 02
│       ├── llm/            # base.py (Protocol), groq/openrouter/gemini_provider.py, router.py
│       ├── tools/          # registry.py, file_tools.py (+ proc/system/app_tools in Phase 02)
│       ├── models/         # db.py (SQLModel), schemas.py — Phase 04
│       └── db/             # session.py (WAL) — Phase 04
├── frontend/               # Next.js — chat + approval modal + history/audit pages (Phase 03)
├── linuxops-cli/           # pip-installable CLI package (Typer) (Phase 03)
├── docs/linuxops/          # Obsidian vault — LOCAL ONLY, git-ignored, source of truth for plan
└── README.md
```

**Target endpoints:** `POST /chat`, `WS /ws/chat`, `POST /auth/token`, `GET /conversations(/id)`, `GET /audit-log`, `POST /tools/approve`, `GET /system/stats`, `GET /health`.

## Phases (build order, gated)

Vault notes (`docs/linuxops/`) are the detailed source of truth. These are the repo-level tracker.

| Phase | File in vault | Focus | Status | Milestone = done when |
|---|---|---|---|---|
| 01 — Pipeline | `docs/linuxops/Phase 01 — Pipeline.md` | repo + FastAPI + LLM provider + `@tool` registry + `list_dir`/`read_file` | ✅ done | `curl POST /chat` "what's in my home folder?" returns a real `list_dir` tool result, not a hallucination; `GET /health` 200 |
| 02 — Safety | `docs/linuxops/Phase 02 — Safety.md` | ReAct loop + Safety 3-tier + confirm gate + audit + rest of tools | ⬜ todo | "kill any process >80% CPU" chains 2+ tool calls; "delete /etc/passwd" hard-blocked with audit entry |
| 03 — Interfaces | `docs/linuxops/Phase 03 — Interfaces.md` | Typer CLI (`linuxops chat`) + Next.js chat + approval modal | ⬜ todo | same request works via `linuxops chat` y/n AND browser modal |
| 04 — Polish | `docs/linuxops/Phase 04 — Polish.md` | SQLite persistence + safety/injection tests + README + demo video | ⬜ todo | stranger runs from README + demo, data survives restart, injection test green |

Rule: **finish a phase's milestone before starting the next one.** Do not touch stretch features before Phase 04.

## Key decisions (locked)

1. CLI is a **thin client** — calls the FastAPI backend over HTTP/WS exactly like the web UI. No agent logic in the CLI. One source of truth.
2. Tool definitions via `@tool` decorator + Pydantic models; JSON schemas auto-generated from the models (DRY).
3. LLM via **Ollama** (local, `qwen3:4b`) — no external API keys, no rate limits, no cost. `LLMProvider` Protocol kept for clean abstraction; swapping models is a one-line env var change.
4. Safety in 3 tiers: 🟢 auto / 🟡 confirm (user y/n or modal) / 🔴 block (typed confirm or hard deny). Denials get logged too.
5. MVP hard-lock — file ops, process mgmt, system stats, app launch, guarded shell. Stretch (memory/voice/multi-LLM/planning/scheduling/docker) only after MVP demo is solid.
6. Design the safety layer as a distinct module, not an afterthought.

## Vault note

- Obsidian vault lives in `docs/linuxops/` — **git-ignored on purpose, never commit it** (decision 2026-09-21).
- Vault = plan source of truth: `index.md` hub → blueprint + learning topics + 4 phase notes.
- Keep coordination between this file and vault phase notes / status fields in sync.

## How to run

> Built from Phase 01 (work in progress). From `Backend/`:
> - Backend: `uv run uvicorn app.main:app --reload` (or `.venv/bin/uvicorn app.main:app --reload`)
> - CLI: `pip install -e ./linuxops-cli` then `linuxops chat` (Phase 03)
> - Frontend: `npm run dev` in `frontend/` (Phase 03)

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

## Current state (2026-09-21)

- Git: `main` branch, repo `https://github.com/khadarbashajilan/Linux-Ops.git`. Tracked: `LICENSE` only. Single commit `dc96195 Initial commit`.
- `.gitignore` — covers `docs/`, `.env`, `.venv`, `.opencode/`, Python/Node/DB/OS artifacts.
- `AGENTS.md` — this file, untracked.
- `.opencode/` — project opencode config (local): `opencode.json`, `safety-reviewer` agent, `progress`/`phase` commands. Git-ignored.
- Vault fully authored (index + blueprint + learning topics + 4 phases) but **not** git-tracked by decision.
- `Backend/` — Phase 01 **DONE**. FastAPI app + `LLMProvider` Protocol + single `OllamaProvider` + `@tool` registry + `list_dir`/`read_file` (allowlist config-driven: `LINUXOPS_ALLOWED_PATHS`, default `~:/tmp` + server cwd). External providers (Groq/OpenRouter/Gemini) removed 2026-10-01. `.env` has Ollama config (git-ignored).

---

## Progress Log

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