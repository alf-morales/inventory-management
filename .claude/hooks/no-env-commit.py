#!/usr/bin/env python3
"""PreToolUse hook: block any Bash command that would stage or commit a .env file.

This repository is public, so a committed .env is an immediate credential leak.
`.gitignore` already lists `.env`, but that is bypassed by `git add -f` and does
not help once a file has been staged some other way. This hook is the backstop.

Two checks run against every git segment of the command:
  1. An env-file path passed directly to `git add` / `stage` / `commit` / `mv`.
  2. A `git commit` while an env file is already staged (or, with -a, modified).

Template files (.env.example and friends) are explicitly allowed - the repo
tracks .env.example on purpose.

Registered in .claude/settings.json under hooks.PreToolUse, matcher "Bash".
Always exits 0; blocking is communicated through the permissionDecision payload.
"""
import json
import os
import re
import shlex
import subprocess
import sys

# Basenames matching an env-file shape: `.env`, `.env.local`, `production.env`
ENV_BASENAME = re.compile(r"^\.env(\..+)?$|^.+\.env$")

# ...but these are templates checked into the repo on purpose, not secrets
SAFE_MARKERS = ("example", "sample", "template", "dist")

# Rough command-segment split so `cd server && git commit` is seen as git
SEGMENT_SPLIT = re.compile(r"\|\||&&|[;|&\n]")

# Wrappers to look past when deciding whether a segment invokes git
WRAPPERS = ("command", "sudo", "nohup", "time", "exec")

# git *global* options that consume the following token as their value
GLOBAL_OPTS_WITH_VALUE = {
    "-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env",
}

# Subcommand options that consume the following token, so it is never a path.
# Without this, `git commit -m "update .env"` would trip the path check.
OPTS_WITH_VALUE = {
    "-m", "--message", "-F", "--file", "-C", "--reuse-message", "-c", "--reedit-message",
    "--author", "--date", "--fixup", "--squash", "-S", "--gpg-sign", "-t", "--template",
    "--cleanup", "--pathspec-from-file",
}

STAGING_SUBCOMMANDS = {"add", "stage", "commit", "mv"}

ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def is_env_path(token):
    """True if the token names a real env file (not a committable template)."""
    base = os.path.basename(token.rstrip("/")).lower()
    if not ENV_BASENAME.match(base):
        return False
    return not any(marker in base for marker in SAFE_MARKERS)


def git_subcommand(tokens):
    """Return (subcommand, remaining_tokens) for a git call, else (None, [])."""
    i = 0
    while i < len(tokens) and (tokens[i] in WRAPPERS or ENV_ASSIGNMENT.match(tokens[i])):
        i += 1

    if i >= len(tokens) or os.path.basename(tokens[i]) not in ("git", "git.exe"):
        return None, []
    i += 1

    while i < len(tokens):
        token = tokens[i]
        if token in GLOBAL_OPTS_WITH_VALUE:
            i += 2
            continue
        if token.startswith("-"):
            i += 1
            continue
        return token, tokens[i + 1:]
    return None, []


def path_arguments(tokens):
    """Yield tokens that are genuine path arguments, skipping options and values."""
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        if token.startswith("-"):
            skip_next = token in OPTS_WITH_VALUE
            continue
        yield token


def tracked_env_files(cwd, include_unstaged):
    """Env files already staged, plus modified-and-tracked ones when -a is used."""
    commands = [["git", "diff", "--cached", "--name-only"]]
    if include_unstaged:
        commands.append(["git", "diff", "--name-only"])

    found = []
    for command in commands:
        try:
            result = subprocess.run(
                command, cwd=cwd, capture_output=True, text=True, timeout=5
            )
        except Exception:
            continue
        if result.returncode == 0:
            found.extend(p for p in result.stdout.splitlines() if p and is_env_path(p))
    return sorted(set(found))


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if "git" not in command:
        sys.exit(0)

    cwd = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()

    for segment in SEGMENT_SPLIT.split(command):
        segment = segment.strip()
        if not segment:
            continue

        try:
            tokens = shlex.split(segment)
        except ValueError:
            tokens = segment.split()

        subcommand, rest = git_subcommand(tokens)
        if subcommand not in STAGING_SUBCOMMANDS:
            continue

        flagged = [t for t in path_arguments(rest) if is_env_path(t)]
        if flagged:
            deny(
                "Blocked: this repository is public and `%s` would put %s into git "
                "history. Env files must never be committed - commit .env.example "
                "with placeholder values instead."
                % (subcommand, ", ".join(flagged))
            )

        if subcommand == "commit":
            include_unstaged = any(
                token == "--all" or re.match(r"^-[a-zA-Z]*a", token) for token in rest
            )
            staged = tracked_env_files(cwd, include_unstaged)
            if staged:
                deny(
                    "Blocked: %s is staged for commit and this repository is public. "
                    "Unstage it with `git rm --cached %s`, confirm it is listed in "
                    ".gitignore, then commit again."
                    % (", ".join(staged), staged[0])
                )

    sys.exit(0)


if __name__ == "__main__":
    main()
