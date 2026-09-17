# Ponytail — Full Repo Details

Repo: https://github.com/DietrichGebert/ponytail
Site: https://ponytail.dev
License: MIT

## What it is

Ponytail is a rule/skill set that makes an AI coding agent behave like a lazy, minimalist senior developer: "he says nothing, he writes one line, it works." Instead of over-building (installing packages, adding wrapper components, starting design discussions) it walks a fixed decision ladder before writing any code, so the diff stays as small as the problem allows — without cutting corners on safety.

**Example (before/after):**
Ask for a date picker → a normal agent installs `flatpickr`, writes a wrapper component, adds a stylesheet, and debates timezones.
With ponytail:
```html
<!-- ponytail: browser has one -->
<input type="date">
```

## Stats

- ~134k GitHub stars, ~7.2k forks, 329 watchers, 222 commits
- Works with 20+ agent hosts
- Measured results (headless Claude Code session on a real FastAPI + React repo, 12 feature tickets, n=4, Haiku 4.5), vs. no-skill baseline:

| Arm | LOC | Tokens | Cost | Time | Safe |
|---|---|---|---|---|---|
| **ponytail** | **-54%** | **-22%** | **-20%** | **-27%** | **100%** |
| caveman (terse-prose control) | -20% | +7% | +3% | +2% | 100% |
| "YAGNI + one-liners" prompt | -33% | -14% | -21% | -30% | 95% |

- Biggest cuts happen where agents over-build (date picker: 404 → 23 lines; color picker: 287 → 23 lines) by reaching for a native `<input>` instead of a component.
- An earlier single-shot benchmark reported 80–94% less code; the agentic numbers above are the corrected, fairer comparison (the earlier baseline padded its answers with prose/options).

## How it works (the ladder)

Before writing code, the agent stops at the first rung that holds:

1. Does this need to exist? → no: skip it (YAGNI)
2. Already in this codebase? → reuse it, don't rewrite
3. Stdlib does it? → use it
4. Native platform feature? → use it
5. Installed dependency? → use it
6. One line? → one line
7. Only then: the minimum that works

The ladder runs *after* the agent understands the problem (reads the touched code, traces the real flow) — lazy about the solution, never about reading. It is never lazy about: trust-boundary input validation, data-loss handling, security, or accessibility.

## Repo structure (top level)

- `.agents/`, `.claude-plugin/`, `.clinerules/`, `.codex-plugin/`, `.cursor/rules/`, `.devin-plugin/`, `.github/`, `.grok-plugin/`, `.kiro/steering/`, `.openclaw/skills/`, `.opencode/`, `.qoder-plugin/`, `.qoder/rules/`, `.windsurf/rules/` — per-agent adapter/config folders
- `assets/` — logos, benchmark SVGs, banners
- `benchmarks/` — benchmark configs and results (`benchmarks/results/2026-06-18-agentic.md`)
- `commands/` — slash-command definitions
- `docs/` — includes `agent-portability.md` (which files map to which agent)
- `examples/` — "survivor" before/after code samples
- `hooks/` — lifecycle hook scripts (e.g. `qoder-hooks.json`)
- `pi-extension/`, `ponytail-mcp/` — Pi harness and MCP integration
- `scripts/` — `uninstall.js`, `check-rule-copies.js`, `build-openclaw-skills.js`, `publish-openclaw-skills.js`
- `skills/` — the six ponytail skills, source for generated adapters
- `tests/`
- Root files: `AGENTS.md` (the core rule text), `README.md` (+ `.es`, `.ko` translations), `LICENSE`, `package.json`, `plugin.json` / `plugin.yaml`, `gemini-extension.json`, `opencode.json`, `after-install.md`, `.env.example`

## Commands

| Command | What it does |
|---|---|
| `/ponytail [lite\|full\|ultra\|off]` | Set intensity or turn off. No argument reports current level. |
| `/ponytail-review` | Review the current diff for over-engineering; returns a delete-list. |
| `/ponytail-audit` | Audit the whole repo for over-engineering, not just the diff. |
| `/ponytail-debt` | Harvest deferred `ponytail:` shortcut comments into a ledger. |
| `/ponytail-gain` | Show the measured impact scoreboard from the benchmark. |
| `/ponytail-help` | Quick command reference. |

Commands require a skill-capable host (Claude Code, Codex, Devin CLI, OpenCode, Gemini, Pi, Swival, Hermes Agent, Qoder, Grok Build). In Codex they're invoked with `@` (e.g. `@ponytail-review`). Instruction-only adapters (Cursor, Windsurf, Cline, Copilot, Kiro, Antigravity) load the always-on ruleset without these commands.

Default mode is **full**. Set a default via `PONYTAIL_DEFAULT_MODE` env var or `defaultMode` in `~/.config/ponytail/config.json` (`%APPDATA%\ponytail\config.json` on Windows).

Subagents spawned via the Agent tool also get the ruleset injected; scope this with `PONYTAIL_SUBAGENT_MATCHER` (regex against `agent_type`, unanchored/case-insensitive).

## Install by agent host

Requires `node` on PATH for the Claude Code / Codex lifecycle hooks (skills still work without it; only always-on auto-injection needs it).

- **Claude Code**
  ```
  /plugin marketplace add DietrichGebert/ponytail
  /plugin install ponytail@ponytail
  ```
  (two separate prompts required)

- **Codex**
  ```
  codex plugin marketplace add DietrichGebert/ponytail
  codex plugin add ponytail@ponytail
  ```
  Then run `codex`, open `/hooks`, trust the two lifecycle hooks, start a new thread.

- **GitHub Copilot CLI**
  ```
  copilot plugin marketplace add DietrichGebert/ponytail
  copilot plugin install ponytail@ponytail
  ```
  Interactive slash equivalents also work. Commands namespaced as `/ponytail:ponytail`, `/ponytail:ponytail-review`, etc.

- **Pi agent harness**
  ```
  pi install git:github.com/DietrichGebert/ponytail
  ```

- **OpenCode** — add to `opencode.json`:
  ```json
  { "plugin": ["@dietrichgebert/ponytail"] }
  ```
  or, from a checkout: `{ "plugin": ["./.opencode/plugins/ponytail.mjs"] }`

- **Gemini CLI**
  ```
  gemini extensions install https://github.com/DietrichGebert/ponytail
  ```

- **Qoder** — auto-loads `AGENTS.md` from repo root (zero setup for a checkout). For per-project rules copy `.qoder/rules/ponytail.md` into your project. Full plugin-tier support needs hooks from `hooks/qoder-hooks.json` added to `.qoder/settings.json` (replace `PONYTAIL_DIR`).

- **Antigravity CLI** (Gemini CLI's rename, `agy` binary):
  ```
  agy plugin install https://github.com/DietrichGebert/ponytail
  ```
  Commands become skills typed as chat messages (e.g. `/ponytail-review`).

- **Hermes Agent**
  ```
  hermes plugins install DietrichGebert/ponytail --enable
  ```
  Restart Hermes after installing.

- **CodeWhale** — reads `AGENTS.md` from project root automatically; copy the file or run from a checkout.

- **Swival**
  ```
  swival skills add --global https://github.com/DietrichGebert/ponytail
  swival skills add ponytail
  swival skills add --global ponytail
  ```
  Also reads `AGENTS.md`. Explicit activation with `$ponytail-review`.

- **Devin CLI**
  ```
  devin plugins install DietrichGebert/ponytail
  ```

- **OpenClaw**
  ```
  clawhub install ponytail
  ```
  (plus `ponytail-review`, `ponytail-audit`, `ponytail-debt`, `ponytail-gain` the same way). Without ClawHub, copy `.openclaw/skills/ponytail` into `~/.openclaw/skills/`.

- **Grok Build**
  ```
  grok plugin install DietrichGebert/ponytail --trust
  ```
  Enable via `/plugins` or `~/.grok/config.toml`. No lifecycle hooks (SessionStart output can't inject instructions there).

- **Instruction-only / rule-file agents** (no plugin, just copy a file):
  - Cursor: `.cursor/rules/`
  - Windsurf: `.windsurf/rules/`
  - Cline: `.clinerules/`
  - GitHub Copilot Chat (VS Code/JetBrains/Visual Studio extension): `.github/copilot-instructions.md`
  - Kiro: `.kiro/steering/ponytail.md` (copy to `~/.kiro/steering/` for global, or project-local)
  - Aider, Zed, CodeWhale, Swival, Qoder: matching rules files as above
  - VS Code + Codex extension: reads `AGENTS.md` automatically (`~/.codex/AGENTS.md` for global)
  - JetBrains Junie: point Settings → Tools → Junie → Project Settings → Guidelines Path at `AGENTS.md` (legacy path: `.junie/guidelines.md`)
  - Amp (Sourcegraph): reads `AGENTS.md` from working dir up to `$HOME` automatically (`~/.config/amp/AGENTS.md` globally)
  - Jules (Google): reads `AGENTS.md` from repo root automatically

Full mapping of files → agents: `docs/agent-portability.md`.

## Uninstall

| Host | Command |
|---|---|
| Claude Code | `/plugin remove ponytail` |
| Codex | `codex plugin remove ponytail` |
| Devin CLI | `devin plugins remove ponytail` |
| Grok Build | `grok plugin uninstall ponytail` |
| Pi agent | `pi uninstall ponytail` |
| Cursor/Windsurf/Cline/Qoder/etc. | Delete the copied rule file |

These leave a little state behind (mode flag, `~/.config/ponytail/config.json`, and possibly a `statusLine` entry in `~/.claude/settings.json`). Run `node scripts/uninstall.js` **before** removing the plugin (the script itself lives inside the plugin folder) to clean those up too.

## Development notes

When editing the compact rule text, keep agent copies in sync:
```
node scripts/check-rule-copies.js
npm test
```
The OpenClaw skill package is generated from `skills/`; rerun `node scripts/build-openclaw-skills.js` after editing a skill (the test suite fails if it's stale). Publish to ClawHub with `clawhub login` then `node scripts/publish-openclaw-skills.js` (add `--dry-run` to preview).

The correctness benchmark spawns Python (`python3` tried before `python`); CSV checks need `pandas` installed locally.

## FAQ

- **Use it with [caveman](https://github.com/JuliusBrussee/caveman)?** Yes — caveman shrinks what the agent *says*, ponytail shrinks what it *builds*. No overlap.
- **Needs a config file?** No — it's optional (`~/.config/ponytail/config.json` or `PONYTAIL_DEFAULT_MODE`).
- **What about the 120-line cache class I actually need?** It'll get built — slowly, correctly, while judging you.
- **Does it scale?** "The code you never wrote scales infinitely. Zero bugs, zero CVEs, 100% uptime since forever."
- **Why "ponytail"?** You know exactly why.

## Sponsors

GreenPT (greenpt.com)

## Topics / Tags

`agent-skills`, `ai-agents`, `claude`, `claude-code`, `claude-code-plugin`, `cursor-rules`, `developer-tools`, `llm`, `prompt-engineering`, `yagni`
