# Claude Code + MLflow on Databricks — End-to-End Demo

A ~20-minute demo that shows how to go from zero to a **trace → evaluate → detect issues → fix with skills** loop for Claude Code, all on Databricks MLflow.

**Target workspace:** `e2-demo-field-eng`
**Target audience:** Databricks field teams and customers who want to adopt Claude Code responsibly — with observability, regression testing, and a path to systematically reduce agent failure modes.

**The narrative loop this demo tells:**

> **Trace** every Claude Code session → **Judge** each trace against your bar → **Detect** systemic issues across many traces → **Install MLflow skills** to close the gap → **Re-run** and show the traces improve.

---

## Table of contents

- [Section 0 — Prereqs](#section-0--prereqs)
- [Section 1 — Trace Claude Code](#section-1--trace-claude-code-5-min)
- [Section 2 — Evaluate with MLflow judges](#section-2--evaluate-with-mlflow-judges-5-min)
- [Section 3 — Automatic issue detection](#section-3--automatic-issue-detection-4-min)
- [Section 4 — Fix with MLflow skills](#section-4--fix-with-mlflow-skills-4-min)
- [Section 5 — Takeaways](#section-5--takeaways)
- [Troubleshooting](#troubleshooting)

---

## Section 0 — Prereqs

### On your laptop

```bash
# Claude Code CLI
npm install -g @anthropic-ai/claude-code

# MLflow (>=3.8 covers all four features: tracing, genai.evaluate, detect_issues, skills)
pip install "mlflow[databricks]>=3.11"

# Databricks CLI (used in Task 2 and optional elsewhere)
pip install --upgrade databricks-cli databricks-sdk
```

### In the Databricks workspace

1. Generate a Personal Access Token: **User Settings → Developer → Access tokens → Generate new token**.
2. Create (or pick) the MLflow experiment:
   - In the workspace, navigate to **Experiments → Create experiment**.
   - Note the **numeric experiment ID** from the URL — you'll pass it to `mlflow autolog claude -e`.

### Clone & configure this repo

```bash
cd ~/claude-code-mlflow-demo
cp .env.template .env
# Edit .env — fill in DATABRICKS_HOST, DATABRICKS_TOKEN, and MLFLOW_EXPERIMENT_ID
set -a && source .env && set +a
```

> **Important:** `.claude/settings.json` is the source of truth for Claude Code — shell env vars do **not** reach the Stop hook subprocess. The top-level `env` block in `settings.json` must include `DATABRICKS_HOST` and `DATABRICKS_TOKEN` so the hook can authenticate to the workspace. This is a [documented footgun](https://docs.databricks.com/aws/en/mlflow3/genai/tracing/integrations/claude-code).

---

## Section 1 — Trace Claude Code (5 min)

📘 Reference: <https://docs.databricks.com/aws/en/mlflow3/genai/tracing/integrations/claude-code>

Two tracing paths are shown. **1a** is what most people want — tracing the real `claude` CLI. **1b** is for customers embedding Claude into a product.

### 1a. CLI tracing (hooks)

Scaffold the hooks. `mlflow autolog claude` writes `.claude/settings.json` for you — a single `Stop` hook that calls `mlflow autolog claude stop-hook` plus a top-level `env` block:

```bash
cd ~/claude-code-mlflow-demo
mlflow autolog claude -u databricks -e 1110749188719431    # use YOUR experiment ID
mlflow autolog claude --status                              # expect: ENABLED
```

Then — and this is the step that the docs bury — open `.claude/settings.json` and add `DATABRICKS_HOST` and `DATABRICKS_TOKEN` to the top-level `env` block. The stop-hook subprocess needs them to reach the workspace; the CLI scaffold does not add them for you:

```json
{
  "hooks": {
    "Stop": [
      { "hooks": [ { "type": "command", "command": "mlflow autolog claude stop-hook" } ] }
    ]
  },
  "env": {
    "MLFLOW_CLAUDE_TRACING_ENABLED": "true",
    "MLFLOW_TRACKING_URI": "databricks",
    "MLFLOW_EXPERIMENT_ID": "1110749188719431",
    "DATABRICKS_HOST": "https://e2-demo-field-eng.cloud.databricks.com",
    "DATABRICKS_TOKEN": "dapi-YOUR-PAT"
  }
}
```


Run the first sample task:

```bash
claude < sample_tasks/task_1_delta_etl.md
```

Open the experiment UI in Databricks — a new trace appears within seconds:

```
https://e2-demo-field-eng.cloud.databricks.com/ml/experiments/123456?compareRunsMode=TRACES
```

Click into the trace. You'll see a span tree containing:
- **User prompts** — the task markdown as the first message.
- **Tool calls** — `Read`, `Bash`, `Edit`, each as a child span with inputs, outputs, and timing.
- **AI responses** — assistant messages with token counts and latency.
- **Session metadata** — model, user, working directory.

**Run the other two tasks** so you have ≥3 traces (needed in Section 3 for clustering):

```bash
claude < sample_tasks/task_2_dbsql_query.md
claude < sample_tasks/task_3_fix_bug.md
```

### 1b. SDK tracing (embedded in an app)

For customers who want Claude inside their own Databricks App or service:

```python
import asyncio, mlflow.anthropic
from claude_agent_sdk import ClaudeSDKClient

mlflow.anthropic.autolog()
mlflow.set_experiment("/Users/austin.choi@databricks.com/claude-code-demo")

async def main():
    async with ClaudeSDKClient() as client:
        await client.query("What is the capital of France?")
        async for message in client.receive_response():
            print(message)

asyncio.run(main())
```

Same instrumentation, same trace shape — traces land in the same experiment.

---

## Section 2 — Evaluate with MLflow judges (5 min)

📘 Reference: <https://mlflow.org/blog/evaluating-skills-mlflow>

Tracing tells you *what happened*. Judges tell you *whether it was good*.

Open `notebooks/02_evaluate_traces.py` in Databricks (**Workspace → Import → File**, or drop into a Repo). Run all cells.

The notebook:

1. Loads the latest 50 traces from the experiment via `mlflow.search_traces()`.
2. Defines four **LLM judges** with `make_judge()` from `mlflow.genai.judges`, using a Databricks Model Serving endpoint (`databricks-claude-sonnet-4` by default — no external OpenAI key):
   - `followed_databricks_best_practices` — Delta, Spark APIs, no pandas-on-driver, no `.coalesce(1)`.
   - `used_correct_api` — `spark.read.table` vs path-based reads.
   - `produced_runnable_code` — did the final `Bash` span exit cleanly?
   - `followed_constraints` — did the agent honor explicit task constraints?
3. Defines one **rule-based judge** with `@scorer` from `mlflow.genai.scorers`:
   - `wrote_to_delta` — scans tool-call spans for `saveAsTable` / `CREATE TABLE ... USING DELTA`.
4. Runs `mlflow.genai.evaluate(data=traces_df, scorers=[...])`.

**In the UI, open the Evaluations tab.** You get a per-trace grid:

| Trace | followed_best_practices | used_correct_api | runnable | followed_constraints | wrote_to_delta |
|---|---|---|---|---|---|
| task_1 | ✅ | ✅ | ✅ | ❌ | ✅ |
| task_2 | ✅ | — | ❌ | ✅ | — |
| task_3 | ✅ | ✅ | ✅ | ❌ | — |

Click any ❌ cell → jumps to the span that triggered the failure, with the judge's rationale inline. This is the regression-testing view for agents: when you change a prompt, skill, or model, you can see immediately which traces flipped red.

---

## Section 3 — Automatic issue detection (4 min)

📘 References:
- <https://mlflow.org/docs/latest/genai/eval-monitor/ai-insights/detect-issues/>
- <https://mlflow.org/blog/issue-detection>

Judges answer a defined question. Issue detection **finds the questions you didn't think to ask** by clustering patterns across many traces.

MLflow uses the **CLEARS** taxonomy:

- **C**orrectness — hallucinations, factual errors
- **L**atency — slow responses, timeouts
- **E**xecution — tool-call failures, API errors
- **A**dherence — instruction-following / formatting failures
- **R**elevance — unhelpful or off-topic responses
- **S**afety — harmful or policy-breaching content

### Demo this live in the UI (primary path)

1. Open the experiment → **Traces** tab.
2. Select all three traces you generated → the **Detect issues** button lights up.
3. In the dialog:
   - Choose all six CLEARS categories.
   - Pick a judge LLM — use `databricks-claude-sonnet-4` (or your workspace's AI Gateway endpoint).
4. Click **Run detection**. MLflow runs a multi-stage pipeline: sample → analyze → cluster → annotate → summarize.
5. When it finishes, the **Insights** panel shows:
   - Clustered issues with counts (e.g. *"3 traces: agent hardcoded catalog name despite 'parameterize' constraint"*).
   - Per-cluster root-cause summaries.
   - Trace-level annotations linked to the specific spans.
   - Triage states: **Pending / Resolved / Rejected** — treat these as a Kanban board for agent quality.

### Programmatic path (for CI / automation)

Open `notebooks/03_detect_issues.py`, run all cells. The notebook tries `mlflow.genai.detect_issues` first and falls back to the REST endpoint `POST /api/2.0/mlflow/issue-detection/analyze` via `databricks-sdk`. This is the path you'd wire into a nightly job that runs over the last 24h of traces.

### Expected findings for this demo

The three seed tasks are chosen so a vanilla Claude Code session reliably hits:

| Task | Likely CLEARS hit | Why |
|---|---|---|
| `task_1_delta_etl.md` | **Adherence** | Agent hardcodes `main.demo` instead of honoring the `CATALOG` variable constraint |
| `task_2_dbsql_query.md` | **Execution** | Agent generates Spark-only syntax that fails on the SQL warehouse |
| `task_3_fix_bug.md` | **Correctness** | Agent fixes the obvious mutable-state bug but misses the country-code edge case |

These become the **exact targets** for Section 4.

---

## Section 4 — Fix with MLflow skills (4 min)

📘 Reference: <https://github.com/mlflow/skills>

Skills are versioned, installable knowledge packages that teach Claude Code how to use MLflow correctly. When an issue-detection cluster repeatedly surfaces the same root cause, a skill is how you codify the fix.

### Install

```bash
bash scripts/install_skills.sh
```

The script:
1. Clones <https://github.com/mlflow/skills> into `~/.claude/skills/mlflow-skills/`.
2. Merges the repo's `UserPromptSubmit` hook into `~/.claude/settings.json` **without clobbering** your tracing hooks from Section 1.

### Available skills (as of writing)

| Skill | What it gives Claude |
|---|---|
| `instrumenting-with-mlflow-tracing` | Adds tracing to Python/TypeScript code correctly |
| `analyze-mlflow-trace` | Debugs spans and identifies root causes |
| `analyze-mlflow-chat-session` | Analyzes multi-turn conversations |
| `retrieving-mlflow-traces` | Trace filtering and search |
| `agent-evaluation` | Dataset creation, scorer selection, execution, analysis |
| `querying-mlflow-metrics` | Token usage, latency, error rate analysis |
| `mlflow-onboarding` | Setup guidance for new users |
| `searching-mlflow-docs` | Authoritative doc search via `llms.txt` index |

The `UserPromptSubmit` hook watches each prompt. If it mentions MLflow tracing, evaluation, metrics, etc., the relevant skill is auto-surfaced into Claude's context — no user action required.

### Close the loop

Re-run the exact same tasks:

```bash
claude < sample_tasks/task_1_delta_etl.md
claude < sample_tasks/task_2_dbsql_query.md
claude < sample_tasks/task_3_fix_bug.md
```

Then re-run both notebooks:

```
notebooks/02_evaluate_traces.py    → new eval run, compare judge pass rates
notebooks/03_detect_issues.py      → new detection run, compare cluster counts
```

**The money shot:** open the Evaluations tab and pull up *both* eval runs side-by-side. Previously-failing judges should flip green. In the Insights panel, the clusters from the first run should shrink or move to **Resolved**. That before/after is what you screenshot for customer conversations.

---

## Section 5 — Takeaways

1. **Tracing is free observability.** A one-liner (`mlflow autolog claude .`) turns every agent session into an inspectable artifact — no code changes, no new infrastructure.
2. **Judges turn traces into regression tests.** The same agent change you'd normally evaluate by vibes can be evaluated with `mlflow.genai.evaluate()` and a handful of `make_judge` calls.
3. **Skills are the fix layer.** Issue detection surfaces the recurring problems; `mlflow/skills` is how you encode the fix so the next session doesn't repeat it. That's the full loop: **observe → measure → learn → remediate.**

---

## Troubleshooting

**Traces don't appear in the UI after running `claude`.**
- Nine times out of ten, `.claude/settings.json` is missing `DATABRICKS_HOST` / `DATABRICKS_TOKEN` in its top-level `env` block. The stop-hook subprocess can't authenticate without them, and Claude Code swallows the stderr. Add them and rerun.
- Check `.claude/mlflow/claude_tracing.log` for the actual error — if the log file doesn't exist, the Stop hook never fired (settings.json is malformed or `mlflow autolog claude stop-hook` isn't on `PATH`).
- Confirm the hook command is literally `mlflow autolog claude stop-hook`. If you see `python -m mlflow.anthropic.autolog.claude.*` anywhere in `settings.json`, that's a stale hand-edited scaffold from pre-3.11 — wipe it: `mlflow autolog claude --disable && mlflow autolog claude -u databricks -e <ID>`.
- Verify `mlflow autolog claude --status` returns `ENABLED` with `Tracking URI: databricks` (not `databricks-uc`).
- Verify `MLFLOW_EXPERIMENT_ID` points at an experiment that exists (`mlflow.get_experiment('<id>')` should return a result).

**Judge calls fail with 401 / endpoint not found.**
- The `JUDGE_ENDPOINT` in `.env` must resolve to a real Model Serving endpoint in your workspace. List them: `databricks serving-endpoints list`.
- The PAT needs `Can Query` on that endpoint.

**`mlflow.genai.detect_issues` raises `AttributeError`.**
- Expected on some MLflow builds — the notebook auto-falls-back to the REST endpoint. If even the REST path 404s, the feature may not be enabled on your workspace; use the UI path instead.

**Skills not surfacing in Claude Code sessions.**
- Start a new `claude` session (the `UserPromptSubmit` hook is read at session start).
- Confirm the hook script path in `~/.claude/settings.json` is absolute and points at an existing file in `~/.claude/skills/mlflow-skills/hooks/`.

**MLflow version mismatch.**
- Requires `mlflow[databricks]>=3.11` for all four sections. Older versions have tracing but not `detect_issues`, and pre-3.11 used a different hook scaffold.

---

## File map

```
claude-code-mlflow-demo/
├── README.md                      ← you are here
├── .env.template                  ← copy to .env, fill in secrets
├── .claude/
│   └── settings.json              ← tracing hooks for Claude Code CLI
├── sample_tasks/
│   ├── task_1_delta_etl.md        ← Delta Lake ETL
│   ├── task_2_dbsql_query.md      ← DBSQL + window function
│   └── task_3_fix_bug.md          ← Spark UDF bug fix
├── notebooks/
│   ├── 02_evaluate_traces.py      ← Databricks notebook: judges + evaluate
│   └── 03_detect_issues.py        ← Databricks notebook: CLEARS detection
└── scripts/
    └── install_skills.sh          ← clone mlflow/skills + wire up hook
```
