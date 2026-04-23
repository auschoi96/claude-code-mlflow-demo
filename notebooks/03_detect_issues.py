# Databricks notebook source
# MAGIC %md
# MAGIC # 03 — Automatic issue detection on Claude Code traces
# MAGIC
# MAGIC Runs MLflow's **CLEARS** issue detection across the accumulated traces:
# MAGIC
# MAGIC - **C**orrectness — hallucinations, factual errors
# MAGIC - **L**atency — slow responses, timeouts
# MAGIC - **E**xecution — tool-call failures, API errors
# MAGIC - **A**dherence — instruction-following / formatting failures
# MAGIC - **R**elevance — unhelpful or off-topic responses
# MAGIC - **S**afety — harmful or policy-breaching content
# MAGIC
# MAGIC Refs:
# MAGIC - https://mlflow.org/docs/latest/genai/eval-monitor/ai-insights/detect-issues/
# MAGIC - https://mlflow.org/blog/issue-detection
# MAGIC
# MAGIC Two entry points are shown: a **UI walkthrough** (primary for the live demo)
# MAGIC and a **programmatic API** path for automation / CI.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade "mlflow[databricks]>=3.8" databricks-sdk
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import os
import mlflow
from mlflow import MlflowClient

EXPERIMENT_PATH = "/Users/austin.choi@databricks.com/claude-code-demo"
JUDGE_ENDPOINT = os.environ.get("JUDGE_ENDPOINT", "databricks-claude-sonnet-4")

mlflow.set_tracking_uri("databricks")
experiment = MlflowClient().get_experiment_by_name(EXPERIMENT_PATH)
EXPERIMENT_ID = experiment.experiment_id
WORKSPACE_HOST = os.environ.get("DATABRICKS_HOST", "https://e2-demo-field-eng.cloud.databricks.com").rstrip("/")

print(f"Experiment: {EXPERIMENT_PATH}  (id={EXPERIMENT_ID})")
print(f"Open in UI:  {WORKSPACE_HOST}/ml/experiments/{EXPERIMENT_ID}?compareRunsMode=TRACES")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Path A — UI walkthrough (demo this live)
# MAGIC
# MAGIC 1. Open the experiment URL printed above.
# MAGIC 2. Click the **Traces** tab.
# MAGIC 3. Select a set of traces (Shift-click or "Select all") → the **Detect issues** button lights up.
# MAGIC 4. In the dialog:
# MAGIC    - Pick the CLEARS categories you care about (default: all six).
# MAGIC    - Pick the LLM endpoint — use the **Databricks AI Gateway** entry for your workspace,
# MAGIC      or a Model Serving endpoint such as `databricks-claude-sonnet-4`.
# MAGIC 5. Click **Run detection**. A background job kicks off the multi-stage pipeline:
# MAGIC    sample → analyze → cluster → annotate → summarize.
# MAGIC 6. When it finishes, the **Insights** panel shows:
# MAGIC    - Clustered issues (e.g. _"3 traces: agent hardcoded catalog name despite 'parameterize' constraint"_).
# MAGIC    - Per-cluster root-cause summaries.
# MAGIC    - Trace-level annotations you can click through.
# MAGIC    - A triage state per cluster: **Pending / Resolved / Rejected**.
# MAGIC
# MAGIC This is the view to screenshot for customer conversations — it demonstrates MLflow's
# MAGIC value better than any single-trace screenshot.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Path B — Programmatic detection
# MAGIC
# MAGIC For automation (e.g. nightly CI, scheduled monitoring, or integrating issue detection
# MAGIC results into a DBSQL dashboard) call the detection API directly.
# MAGIC
# MAGIC The function below tries `mlflow.genai.detect_issues` first; if the installed
# MAGIC MLflow build exposes only the REST surface, it falls back to the Databricks
# MAGIC `/api/2.0/mlflow/issue-detection/analyze` endpoint.

# COMMAND ----------

CATEGORIES = ["correctness", "latency", "execution", "adherence", "relevance", "safety"]

def run_issue_detection(experiment_id: str, categories: list[str], endpoint: str):
    """Kick off issue detection and return a job / run handle."""
    genai = getattr(mlflow, "genai", None)
    detect_fn = getattr(genai, "detect_issues", None) if genai else None

    if callable(detect_fn):
        print("Using mlflow.genai.detect_issues()")
        return detect_fn(
            experiment_id=experiment_id,
            categories=categories,
            judge_model=f"databricks:/{endpoint}",
        )

    # Fallback: REST.
    print("Falling back to REST: POST /api/2.0/mlflow/issue-detection/analyze")
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient()
    return w.api_client.do(
        method="POST",
        path="/api/2.0/mlflow/issue-detection/analyze",
        body={
            "experiment_id": experiment_id,
            "categories": [c.upper() for c in categories],
            "judge_endpoint": endpoint,
        },
    )

result = run_issue_detection(EXPERIMENT_ID, CATEGORIES, JUDGE_ENDPOINT)
print(result)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Expected findings for this demo
# MAGIC
# MAGIC The three sample tasks are intentionally seeded to produce issues an
# MAGIC un-skilled Claude Code session tends to hit:
# MAGIC
# MAGIC | Task | Likely CLEARS hit | Why |
# MAGIC |---|---|---|
# MAGIC | `task_1_delta_etl.md` | **Adherence** | agent hardcodes `main.demo` instead of honoring the `CATALOG` variable constraint |
# MAGIC | `task_2_dbsql_query.md` | **Execution** | agent generates Spark-only syntax that fails on the SQL warehouse |
# MAGIC | `task_3_fix_bug.md` | **Correctness** | agent fixes the obvious mutable-state bug but misses the country-code edge case |
# MAGIC
# MAGIC These findings become the target for Section 4 (mlflow/skills) — the skills
# MAGIC `searching-mlflow-docs` and `instrumenting-with-mlflow-tracing` give the agent
# MAGIC the missing context to avoid these patterns on the re-run.

# COMMAND ----------

# MAGIC %md
# MAGIC ## After installing skills (Section 4)
# MAGIC
# MAGIC Re-run this notebook end-to-end on the **new** traces. In the UI:
# MAGIC - Filter traces by `skills_installed=true` tag (set by the UserPromptSubmit hook).
# MAGIC - Re-run issue detection on just those traces.
# MAGIC - Compare the Pending/Resolved count vs the pre-skills baseline.
# MAGIC
# MAGIC That before/after is the money shot of the demo.
