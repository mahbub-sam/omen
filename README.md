# OMEN

A local-first CLI for orchestrating multi-agent AI job pipelines — no database, no cloud, no dashboard server. Everything lives in a plain JSON state file in your project folder.

```
omen project create website
omen run "add input validation" --role coder --project website
omen chain "build a login form" --roles coder,reviewer --project website
omen jobs --project website
```

## Why

Running one AI agent on a task is easy. Running a *pipeline* — one agent writes code, another reviews it, output flows from one to the next — usually means gluing scripts together by hand. OMEN gives you that pipeline as a couple of commands, with every job's status and output tracked locally so you can inspect what happened later. As you work on multiple things at once, `project` grouping keeps their jobs separate instead of one long undifferentiated list.

## Install

Zero dependencies — just Python 3 stdlib (`urllib`, `json`). No `pip install` needed.

```bash
git clone https://github.com/yourname/omen.git
cd omen
chmod +x omen.py
sudo ln -s "$(pwd)/omen.py" /usr/local/bin/omen   # optional, puts it on PATH
```

## Setup

```bash
cd your-project/
omen init                                  # creates omen.config.json
export ANTHROPIC_API_KEY=sk-ant-...        # or edit omen.config.json for a different provider
```

## Usage

```bash
omen project create <name>                       # register a project to group jobs under
omen project list                                 # list projects with job counts

omen run "<task>" --role coder [--project <name>]                    # run a single job
omen chain "<task>" --roles coder,reviewer [--project <name>]        # run a sequential pipeline

omen jobs [--project <name>]              # list jobs, optionally filtered by project
omen show <job-id>                        # see full output of one job
omen stop <job-id>                        # mark a job as stopped
```

`--project` is optional everywhere — you can use OMEN without ever creating a project, and jobs without one just show `-` in listings.

## How chaining works

`omen chain "task" --roles coder,reviewer` runs the `coder` role first, then passes its output as context into the `reviewer` role. Each role only sees the immediately preceding output, not the full history — this keeps prompts small and roles focused.

## Config

`omen.config.json` defines your provider, model, and the roles available to you. Roles are just a name + a system prompt — add your own:

```json
{
  "provider": "claude",
  "api_key_env": "ANTHROPIC_API_KEY",
  "model": "claude-sonnet-4-6",
  "base_url": null,
  "roles": {
    "coder": { "system_prompt": "..." },
    "reviewer": { "system_prompt": "..." },
    "researcher": { "system_prompt": "..." },
    "tester": { "system_prompt": "..." }
  }
}
```

The default config ships with four roles: `coder`, `reviewer`, `researcher`, `tester`. Edit or add to these freely.

### Supported providers

- `"provider": "claude"` — Anthropic API
- `"provider": "openai"` — OpenAI API
- `"provider": "compatible"` — any OpenAI-compatible endpoint (Groq, Together, local Ollama, etc.) — set `"base_url"` accordingly

## State

All job and project data lives in `.omen-state.json` in your project folder. Delete it to reset. Add it to `.gitignore` unless you specifically want job history versioned.

## What OMEN doesn't do (yet)

- Parallel job execution (jobs run one at a time, synchronously)
- More than 2 roles wired into `chain` at once (you can still define more roles and call `omen run` on each manually, or chain them in separate steps)
- True background/async job stopping — `omen stop` marks state but a synchronous run can't be interrupted mid-call yet

These are left out deliberately to keep this version reliable. Contributions welcome.

## License

MIT
