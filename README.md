# OMEN (mc)

A local-first CLI for orchestrating AI agent jobs — no database, no cloud, no dashboard server. Everything lives in a plain JSON state file in your project folder.

```
mc run "add input validation" --role coder
mc chain "build a login form" --roles coder,reviewer
mc jobs
```

## Why

Running one AI agent on a task is easy. Running a *pipeline* — one agent writes code, another reviews it, output flows from one to the next — usually means gluing scripts together by hand. OMEN gives you that pipeline as two commands, with every job's status and output tracked locally so you can inspect what happened later.

## Install

Zero dependencies — just Python 3 stdlib (`urllib`, `json`). No `pip install` needed.

```bash
git clone https://github.com/yourname/omen.git
cd omen
chmod +x omen.py
sudo ln -s "$(pwd)/omen.py" /usr/local/bin/mc   # optional, puts it on PATH
```

## Setup

```bash
cd your-project/
mc init                                   # creates mc.config.json
export ANTHROPIC_API_KEY=sk-ant-...       # or edit mc.config.json for a different provider
```

## Usage

```bash
mc run "<task>" --role coder              # run a single job
mc chain "<task>" --roles coder,reviewer  # run a sequential pipeline
mc jobs                                   # list all jobs and their status
mc show <job-id>                          # see full output of one job
mc stop <job-id>                          # mark a job as stopped
```

## How chaining works

`mc chain "task" --roles coder,reviewer` runs the `coder` role first, then passes its output as context into the `reviewer` role. Each role only sees the immediately preceding output, not the full history — this keeps prompts small and roles focused.

## Config

`mc.config.json` defines your provider, model, and the roles available to you. Roles are just a name + a system prompt — add your own:

```json
{
  "provider": "claude",
  "api_key_env": "ANTHROPIC_API_KEY",
  "model": "claude-sonnet-4-6",
  "base_url": null,
  "roles": {
    "coder": { "system_prompt": "..." },
    "reviewer": { "system_prompt": "..." },
    "tester": { "system_prompt": "You write test cases for the given code..." }
  }
}
```

### Supported providers

- `"provider": "claude"` — Anthropic API
- `"provider": "openai"` — OpenAI API
- `"provider": "compatible"` — any OpenAI-compatible endpoint (Groq, Together, local Ollama, etc.) — set `"base_url"` accordingly

## State

All job history lives in `.mc-state.json` in your project folder. Delete it to reset. Add it to `.gitignore` unless you specifically want job history versioned.

## What v1 doesn't do (yet)

- Parallel job execution (jobs run one at a time, synchronously)
- More than 2 roles wired into `chain` at once (you can still define more roles and call `mc run` on each manually)
- True background/async job stopping — `mc stop` marks state but a synchronous run can't be interrupted mid-call yet

These are left out deliberately to keep this version reliable. Contributions welcome.

## License

MIT
