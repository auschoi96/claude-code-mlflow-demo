#!/usr/bin/env bash
# Install the mlflow/skills collection into Claude Code and wire up the
# UserPromptSubmit hook so skills are surfaced contextually.
#
# Idempotent: re-running updates the skills repo and leaves existing
# tracing hooks in .claude/settings.json untouched.
#
# Ref: https://github.com/mlflow/skills

set -euo pipefail

SKILLS_DIR="${HOME}/.claude/skills/mlflow-skills"
SETTINGS_FILE="${HOME}/.claude/settings.json"

echo "==> Installing mlflow/skills into ${SKILLS_DIR}"
mkdir -p "$(dirname "${SKILLS_DIR}")"
if [ -d "${SKILLS_DIR}/.git" ]; then
  git -C "${SKILLS_DIR}" pull --ff-only
else
  git clone https://github.com/mlflow/skills.git "${SKILLS_DIR}"
fi

echo
echo "==> Available skills:"
ls -1 "${SKILLS_DIR}" | grep -v -E '^(\.|hooks|tests|README|LICENSE)' | sed 's/^/   - /'

echo
echo "==> Wiring up the UserPromptSubmit hook in ${SETTINGS_FILE}"
mkdir -p "$(dirname "${SETTINGS_FILE}")"

HOOK_SCRIPT="${SKILLS_DIR}/hooks/user_prompt_submit.py"
if [ ! -f "${HOOK_SCRIPT}" ]; then
  echo "WARN: expected hook at ${HOOK_SCRIPT} not found. Repo layout may have changed."
  echo "      See https://github.com/mlflow/skills for the current hook path."
  exit 0
fi

python3 - "$SETTINGS_FILE" "$HOOK_SCRIPT" <<'PY'
import json, os, sys, pathlib
settings_path = pathlib.Path(sys.argv[1])
hook_script = sys.argv[2]

if settings_path.exists():
    settings = json.loads(settings_path.read_text())
else:
    settings = {}

settings.setdefault("hooks", {})
ups = settings["hooks"].setdefault("UserPromptSubmit", [])

already = any(
    isinstance(h, dict) and "mlflow-skills" in json.dumps(h)
    for h in ups
)
if not already:
    ups.append({
        "type": "command",
        "command": f"python3 {hook_script}",
        "timeout": 10000,
    })
    settings_path.write_text(json.dumps(settings, indent=2))
    print(f"Added UserPromptSubmit hook to {settings_path}")
else:
    print(f"UserPromptSubmit hook already present in {settings_path} — skipping")
PY

echo
echo "==> Done. Start a new Claude Code session to pick up the skills."
echo "    Try:  claude \"add mlflow tracing to this python script\""
