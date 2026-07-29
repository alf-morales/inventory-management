# Claude Code Hooks

This directory contains hooks for Claude Code that automate tasks during development.

## Available Hooks

### 1. Post Tool Use Logger (`post-tool-use.sh`)

**Purpose**: Logs all tool usage to help with debugging and tracking Claude's actions.

**Trigger**: Runs after every tool call (Read, Write, Edit, Bash, etc.)

**Configuration**: Enabled in `.claude/settings.local.json` under the `hooks.PostToolUse` section.

**Log Location**: `.claude/logs/tool-usage-YYYY-MM-DD.log`

**Log Format**:
```
=== Tool Usage: 2025-10-16 09:15:23 ===
Tool: Read
Session: abc123
Input: {"file_path": "/path/to/file.js"}
Response: {"content": "..."}
```

**Features**:
- Creates daily log files with timestamps
- Uses `jq` for clean JSON parsing (falls back to raw logging if jq is not installed)
- Logs tool name, session ID, input parameters, and response
- Never blocks tool execution

**Usage**:
The hook runs automatically once configured. To view logs:
```bash
# View today's log
cat .claude/logs/tool-usage-$(date +%Y-%m-%d).log

# View logs with live updates
tail -f .claude/logs/tool-usage-$(date +%Y-%m-%d).log

# Search logs for specific tool
grep "Tool: Bash" .claude/logs/*.log
```

**Requirements**:
- Optional: `jq` for better JSON formatting (`brew install jq` on macOS)

### 2. User Prompt Submit Hook (`user-prompt-submit.sh`)

**Purpose**: Runs pre-commit linting checks when Claude creates commits.

**Trigger**: Runs when the user's prompt contains "commit" or "git commit"

**Features**:
- Lints Python files with `ruff`
- Lints JavaScript/Vue files with `eslint`
- Blocks commits if linting fails

### 3. Env File Commit Guard (`no-env-commit.py`)

**Purpose**: Prevents `.env` files from ever entering git history. This repository
is public, so a committed `.env` is an immediate credential leak.

**Trigger**: Runs before every Bash tool call (`PreToolUse`, matcher `Bash`).

**Configuration**: Enabled in `.claude/settings.json` (project level, committed so
the guard applies to everyone on the team).

**What it blocks**:
- An env file passed to `git add` / `git stage` / `git commit` / `git mv`, including
  `git add -f .env`, which bypasses `.gitignore`
- Any `git commit` while an env file is already staged
- `git commit -a` while a tracked env file has been modified

It sees through common command shapes: `cd server && git add .env`,
`git -C /repo add .env`, `command git add .env`, and `echo hi; git add .env`.

**What it allows**:
- `.env.example`, `.env.sample`, `.env.template`, `.env.dist` - templates are meant
  to be committed, and this repo tracks `.env.example` on purpose
- Reading or writing env files (`cat .env`, `echo FOO=1 > .env`)
- Commit messages that merely mention `.env`, e.g. `git commit -m "update .env handling"`
- Cleanup commands: `git rm --cached .env`, `git restore --staged .env`

**Note**: `.gitignore` already lists `.env`. This hook is the backstop for the cases
`.gitignore` does not cover - force-adds and files that were already staged.

## Disabling Hooks

To temporarily disable a hook, you can:

1. **Comment out in settings**: Edit `.claude/settings.local.json` and remove the hook configuration
2. **Remove execute permission**: `chmod -x .claude/hooks/post-tool-use.sh`
3. **Delete the hook file**: `rm .claude/hooks/post-tool-use.sh`

## Creating Custom Hooks

See the [Claude Code Hooks Documentation](https://docs.claude.com/en/docs/claude-code/hooks.md) for more information on creating custom hooks.

### Available Hook Events:
- `PreToolUse` - Before tool execution
- `PostToolUse` - After tool execution
- `UserPromptSubmit` - When user submits a prompt
- `Stop` - When agent finishes responding
- `SubagentStop` - When subagent finishes
- `SessionStart` - When session starts
- `SessionEnd` - When session ends

### Hook Exit Codes:
- `0` - Success, allow action to proceed
- `2` - Block action and show error message
- Other non-zero - Error occurred

## Troubleshooting

**Hook not running?**
- Check that the hook file is executable: `ls -l .claude/hooks/`
- Verify configuration in `.claude/settings.local.json`
- Check Claude Code logs for errors

**Permission errors?**
- Ensure the hook script has execute permissions: `chmod +x .claude/hooks/*.sh`

**Can't find logs?**
- Logs are created in `.claude/logs/` directory
- Check that `CLAUDE_PROJECT_DIR` environment variable is set correctly
- Try running the hook manually to test: `./.claude/hooks/post-tool-use.sh`
