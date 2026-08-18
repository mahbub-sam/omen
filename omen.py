#!/usr/bin/env python3
"""
omen - OMEN: local-first multi-agent job orchestration

Usage:
    omen init                              Create a starter omen.config.json in this folder
    omen project create <name>             Register a new project to group jobs under
    omen project list                      List all projects with job counts
    omen run "<task>" --role coder [--project <name>]
                                            Run a single job with one role
    omen chain "<task>" --roles coder,reviewer [--project <name>]
                                            Run a sequential chain: each role's output
                                            feeds into the next role as context
    omen jobs [--project <name>]           List all jobs (running/waiting/done/failed)
    omen show <job-id>                     Show full output of a job
    omen stop <job-id>                     Mark a running job as stopped (best-effort)

State is stored locally in .omen-state.json - no database, no cloud.
"""

import sys
import os
import json
import time
import uuid
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from providers import call_provider, ProviderError

CONFIG_FILE = "omen.config.json"
STATE_FILE = ".omen-state.json"

DEFAULT_CONFIG = {
    "provider": "claude",
    "api_key_env": "ANTHROPIC_API_KEY",
    "model": "claude-sonnet-4-6",
    "base_url": None,
    "roles": {
        "coder": {
            "system_prompt": "You are a focused software engineer. Given a task, write clean, working code with brief explanations. Do not pad your response with unnecessary commentary. If the task is ambiguous, state your assumption in one line and proceed."
        },
        "reviewer": {
            "system_prompt": "You are a strict but fair code reviewer. Given code, identify bugs, security issues, unclear logic, and missing edge cases. Be specific: reference exact lines or functions. If the code is genuinely fine, say so briefly rather than inventing issues."
        },
        "researcher": {
            "system_prompt": "You are a research assistant. Given a task, gather relevant facts, options, or prior art needed to complete it well. Present findings as a short, organized summary with the most decision-relevant points first. Flag anything uncertain rather than guessing."
        },
        "tester": {
            "system_prompt": "You are a QA engineer. Given code, write test cases covering normal use, edge cases, and failure modes. Prefer concrete test code over descriptions when a testing framework is implied or specified; otherwise, list clear test scenarios."
        }
    }
}

_state_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config():
    if not Path(CONFIG_FILE).exists():
        print(f"❌ No {CONFIG_FILE} found. Run 'omen init' first.")
        sys.exit(1)
    try:
        return json.loads(Path(CONFIG_FILE).read_text())
    except json.JSONDecodeError as e:
        print(f"❌ {CONFIG_FILE} is not valid JSON: {e}")
        sys.exit(1)


def cmd_init():
    if Path(CONFIG_FILE).exists():
        print(f"⚠️  {CONFIG_FILE} already exists. Not overwriting.")
        return
    Path(CONFIG_FILE).write_text(json.dumps(DEFAULT_CONFIG, indent=2) + "\n")
    print(f"✅ Created {CONFIG_FILE}")
    print("   Edit it to set your provider, model, and API key env var name.")
    print("   Then export your key, e.g.: export ANTHROPIC_API_KEY=sk-...")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def load_state():
    if not Path(STATE_FILE).exists():
        return {"jobs": {}, "projects": {}}
    try:
        state = json.loads(Path(STATE_FILE).read_text())
        state.setdefault("jobs", {})
        state.setdefault("projects", {})
        return state
    except (json.JSONDecodeError, OSError):
        return {"jobs": {}, "projects": {}}


def save_state(state):
    with _state_lock:
        Path(STATE_FILE).write_text(json.dumps(state, indent=2))


def update_job(job_id, **fields):
    state = load_state()
    if job_id not in state["jobs"]:
        state["jobs"][job_id] = {}
    state["jobs"][job_id].update(fields)
    save_state(state)


def new_job(role, task, project=None):
    job_id = str(uuid.uuid4())[:8]
    update_job(
        job_id,
        id=job_id,
        role=role,
        task=task,
        project=project,
        status="waiting",
        created_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        output=None,
        error=None,
    )
    return job_id


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def cmd_project_create(name):
    state = load_state()
    if name in state["projects"]:
        print(f"⚠️  Project '{name}' already exists.")
        return
    state["projects"][name] = {"created_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    save_state(state)
    print(f"✅ Project '{name}' created.")


def cmd_project_list():
    state = load_state()
    projects = state.get("projects", {})
    if not projects:
        print("No projects yet. Create one with: omen project create <name>")
        return

    jobs = state.get("jobs", {})
    print(f"{'PROJECT':<20} {'CREATED':<20} JOBS (running/waiting/done/failed)")
    print("-" * 80)
    for name, info in sorted(projects.items()):
        project_jobs = [j for j in jobs.values() if j.get("project") == name]
        counts = {"running": 0, "waiting": 0, "done": 0, "failed": 0, "stopped": 0}
        for j in project_jobs:
            s = j.get("status", "waiting")
            counts[s] = counts.get(s, 0) + 1
        summary = f"{counts['running']}/{counts['waiting']}/{counts['done']}/{counts['failed']}"
        print(f"{name:<20} {info.get('created_at', '?'):<20} {summary}")


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def get_api_key(config, job_id=None):
    env_var = config.get("api_key_env", "ANTHROPIC_API_KEY")
    key = os.environ.get(env_var)
    if not key:
        msg = f"Environment variable {env_var} is not set"
        if job_id:
            update_job(job_id, status="failed", error=msg,
                       finished_at=time.strftime("%Y-%m-%d %H:%M:%S"))
        print(f"❌ {msg}.")
        print(f"   export {env_var}=your-key-here")
        sys.exit(1)
    return key


def execute_job(job_id, config, extra_context=""):
    state = load_state()
    job = state["jobs"][job_id]
    role_name = job["role"]

    roles = config.get("roles", {})
    if role_name not in roles:
        update_job(job_id, status="failed", error=f"Unknown role '{role_name}' in config")
        print(f"❌ Unknown role '{role_name}'. Available: {list(roles.keys())}")
        return None

    system_prompt = roles[role_name]["system_prompt"]
    user_message = job["task"]
    if extra_context:
        user_message = f"{extra_context}\n\n---\n\nTask: {user_message}"

    update_job(job_id, status="running", started_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    print(f"🏃 [{job_id}] {role_name} running...")

    api_key = get_api_key(config, job_id=job_id)
    provider = config.get("provider", "claude")
    model = config.get("model", "claude-sonnet-4-6")
    base_url = config.get("base_url")

    try:
        kwargs = dict(
            api_key=api_key,
            model=model,
            system_prompt=system_prompt,
            user_message=user_message,
        )
        if provider in ("openai", "compatible") and base_url:
            kwargs["base_url"] = base_url

        output = call_provider(provider, **kwargs)
        update_job(job_id, status="done", output=output,
                   finished_at=time.strftime("%Y-%m-%d %H:%M:%S"))
        print(f"✅ [{job_id}] {role_name} done")
        return output

    except ProviderError as e:
        update_job(job_id, status="failed", error=str(e),
                   finished_at=time.strftime("%Y-%m-%d %H:%M:%S"))
        print(f"❌ [{job_id}] {role_name} failed: {e}")
        return None


def cmd_run(task, role, project=None):
    config = load_config()
    if role not in config.get("roles", {}):
        print(f"❌ Unknown role '{role}'. Available: {list(config.get('roles', {}).keys())}")
        sys.exit(1)
    if project and project not in load_state().get("projects", {}):
        print(f"❌ Unknown project '{project}'. Create it with: omen project create {project}")
        sys.exit(1)
    job_id = new_job(role, task, project=project)
    output = execute_job(job_id, config)
    if output:
        print(f"\n--- Output ({job_id}) ---\n{output}")


def cmd_chain(task, role_names, project=None):
    config = load_config()
    available = config.get("roles", {})
    for r in role_names:
        if r not in available:
            print(f"❌ Unknown role '{r}'. Available: {list(available.keys())}")
            sys.exit(1)
    if project and project not in load_state().get("projects", {}):
        print(f"❌ Unknown project '{project}'. Create it with: omen project create {project}")
        sys.exit(1)

    context = ""
    for role in role_names:
        job_id = new_job(role, task, project=project)
        output = execute_job(job_id, config, extra_context=context)
        if output is None:
            print(f"⛔ Chain stopped: '{role}' failed.")
            return
        context = f"Previous step ({role}) produced:\n{output}"
        print(f"\n--- {role} output ({job_id}) ---\n{output}\n")


# ---------------------------------------------------------------------------
# Inspection commands
# ---------------------------------------------------------------------------

def cmd_jobs(project=None):
    state = load_state()
    jobs = state.get("jobs", {})
    if project:
        jobs = {k: v for k, v in jobs.items() if v.get("project") == project}
    if not jobs:
        print(f"No jobs found" + (f" for project '{project}'." if project else "."))
        return

    status_icon = {
        "waiting": "⏳", "running": "🏃", "done": "✅", "failed": "❌", "stopped": "🛑"
    }

    print(f"{'ID':<10} {'PROJECT':<12} {'ROLE':<12} {'STATUS':<12} {'CREATED':<20} TASK")
    print("-" * 100)
    for job_id, job in sorted(jobs.items(), key=lambda kv: kv[1].get("created_at", "")):
        icon = status_icon.get(job.get("status"), "?")
        task_preview = (job.get("task", "") or "")[:35]
        proj = job.get("project") or "-"
        print(f"{job_id:<10} {proj:<12} {job.get('role', '?'):<12} {icon} {job.get('status', '?'):<9} "
              f"{job.get('created_at', '?'):<20} {task_preview}")


def cmd_show(job_id):
    state = load_state()
    job = state.get("jobs", {}).get(job_id)
    if not job:
        print(f"❌ No job found with id '{job_id}'")
        sys.exit(1)
    print(json.dumps(job, indent=2))


def cmd_stop(job_id):
    state = load_state()
    job = state.get("jobs", {}).get(job_id)
    if not job:
        print(f"❌ No job found with id '{job_id}'")
        sys.exit(1)
    if job.get("status") != "running":
        print(f"⚠️  Job '{job_id}' is not running (status: {job.get('status')}). Nothing to stop.")
        return
    # Best-effort: we mark it stopped in state. Since jobs run synchronously
    # in this version, this mainly matters for future async/background execution.
    update_job(job_id, status="stopped", finished_at=time.strftime("%Y-%m-%d %H:%M:%S"))
    print(f"🛑 Marked '{job_id}' as stopped.")


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "init":
        cmd_init()

    elif command == "project":
        if len(sys.argv) < 3:
            print("❌ Usage: omen project create <name>  |  omen project list")
            sys.exit(1)
        sub = sys.argv[2]
        if sub == "create":
            if len(sys.argv) < 4:
                print("❌ Usage: omen project create <name>")
                sys.exit(1)
            cmd_project_create(sys.argv[3])
        elif sub == "list":
            cmd_project_list()
        else:
            print(f"❌ Unknown project subcommand: {sub}")
            sys.exit(1)

    elif command == "run":
        if len(sys.argv) < 3:
            print("❌ Usage: omen run \"<task>\" --role <role> [--project <name>]")
            sys.exit(1)
        task = sys.argv[2]
        role = None
        project = None
        if "--role" in sys.argv:
            idx = sys.argv.index("--role")
            role = sys.argv[idx + 1]
        if "--project" in sys.argv:
            idx = sys.argv.index("--project")
            project = sys.argv[idx + 1]
        if not role:
            print("❌ Missing --role <role>")
            sys.exit(1)
        cmd_run(task, role, project=project)

    elif command == "chain":
        if len(sys.argv) < 3:
            print("❌ Usage: omen chain \"<task>\" --roles coder,reviewer [--project <name>]")
            sys.exit(1)
        task = sys.argv[2]
        roles = None
        project = None
        if "--roles" in sys.argv:
            idx = sys.argv.index("--roles")
            roles = sys.argv[idx + 1].split(",")
        if "--project" in sys.argv:
            idx = sys.argv.index("--project")
            project = sys.argv[idx + 1]
        if not roles:
            print("❌ Missing --roles role1,role2")
            sys.exit(1)
        cmd_chain(task, roles, project=project)

    elif command == "jobs":
        project = None
        if "--project" in sys.argv:
            idx = sys.argv.index("--project")
            project = sys.argv[idx + 1]
        cmd_jobs(project=project)

    elif command == "show":
        if len(sys.argv) < 3:
            print("❌ Usage: omen show <job-id>")
            sys.exit(1)
        cmd_show(sys.argv[2])

    elif command == "stop":
        if len(sys.argv) < 3:
            print("❌ Usage: omen stop <job-id>")
            sys.exit(1)
        cmd_stop(sys.argv[2])

    elif command in ("-h", "--help", "help"):
        print(__doc__)

    else:
        print(f"❌ Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
