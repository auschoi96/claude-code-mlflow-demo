# Databricks notebook source
# MAGIC %md
# MAGIC # 02 — Evaluate Claude Code traces with MLflow judges
# MAGIC
# MAGIC Reads traces produced by Claude Code (Section 1 of the demo) and scores them
# MAGIC with a mix of **LLM judges** (`make_judge`) and **rule-based judges** (`@scorer`).
# MAGIC
# MAGIC Pattern reused verbatim from the MLflow blog:
# MAGIC https://mlflow.org/blog/evaluating-skills-mlflow
# MAGIC
# MAGIC Results render in the MLflow experiment UI with a per-trace pass/fail grid
# MAGIC and judge rationales.

# COMMAND ----------

# MAGIC %pip install --quiet --upgrade "mlflow[databricks]>=3.8"
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import os
import mlflow
from mlflow import MlflowClient

EXPERIMENT_PATH = "/Users/austin.choi@databricks.com/claude-code-demo"
JUDGE_ENDPOINT = os.environ.get("JUDGE_ENDPOINT", "databricks-claude-sonnet-4")

mlflow.set_tracking_uri("databricks")
mlflow.set_experiment(EXPERIMENT_PATH)
experiment = MlflowClient().get_experiment_by_name(EXPERIMENT_PATH)
EXPERIMENT_ID = experiment.experiment_id
print(f"Experiment: {EXPERIMENT_PATH}  (id={EXPERIMENT_ID})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load traces
# MAGIC
# MAGIC `mlflow.search_traces` returns a DataFrame where each row is one Claude Code
# MAGIC conversation. Each row includes the full span tree, which is what the judges
# MAGIC will reason over via the `{{ trace }}` template variable.

# COMMAND ----------

traces_df = mlflow.search_traces(
    experiment_ids=[EXPERIMENT_ID],
    max_results=50,
    order_by=["timestamp_ms DESC"],
)
print(f"Loaded {len(traces_df)} traces")
traces_df.head()

# COMMAND ----------

# MAGIC %md
# MAGIC ## LLM judges — semantic checks on the trace

# COMMAND ----------

from typing import Literal
from mlflow.genai.judges import make_judge

followed_databricks_best_practices = make_judge(
    name="followed_databricks_best_practices",
    instructions=(
        "Examine the {{ trace }} of a Claude Code session asked to produce "
        "Databricks code. Return 'yes' only if ALL of the following hold: "
        "(a) it uses Spark or DBSQL APIs (not pandas-on-driver for bulk data), "
        "(b) it writes to Delta / Unity Catalog tables via saveAsTable or CREATE TABLE, "
        "(c) it avoids anti-patterns like .coalesce(1) or .repartition(1) on large data, "
        "(d) it does not hardcode catalog/schema names where the task said to parameterize. "
        "Otherwise return 'no' with a rationale pointing at the specific violating span."
    ),
    feedback_value_type=Literal["yes", "no"],
    model=f"databricks:/{JUDGE_ENDPOINT}",
)

used_correct_api = make_judge(
    name="used_correct_api",
    instructions=(
        "Look at the {{ trace }}. Did the agent use idiomatic Databricks APIs "
        "(spark.read.table, saveAsTable, current_timestamp, etc.) rather than "
        "path-based reads/writes like spark.read.format('json').load('/path')? "
        "Return 'yes' or 'no' with a short rationale."
    ),
    feedback_value_type=Literal["yes", "no"],
    model=f"databricks:/{JUDGE_ENDPOINT}",
)

produced_runnable_code = make_judge(
    name="produced_runnable_code",
    instructions=(
        "Look at the {{ trace }}. Did the agent's final code actually run to "
        "completion without errors? Inspect Bash / tool-call spans for non-zero "
        "exit codes, tracebacks, or pytest failures. Return 'yes' if the last "
        "execution succeeded, 'no' otherwise."
    ),
    feedback_value_type=Literal["yes", "no"],
    model=f"databricks:/{JUDGE_ENDPOINT}",
)

followed_constraints = make_judge(
    name="followed_constraints",
    instructions=(
        "The user gave explicit constraints in the task prompt (visible at the "
        "start of {{ trace }}). Did the agent honor every one? Examples of "
        "violations to look for: using pandas when told not to; adding "
        ".coalesce(1); hardcoding names told to parameterize; converting a "
        "Python UDF to regexp_replace when told to keep a UDF. Return 'yes' "
        "or 'no' with the specific violated constraint in the rationale."
    ),
    feedback_value_type=Literal["yes", "no"],
    model=f"databricks:/{JUDGE_ENDPOINT}",
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Rule-based judge — deterministic side-effect check

# COMMAND ----------

from mlflow.entities import Feedback
from mlflow.genai.scorers import scorer

@scorer(name="wrote_to_delta")
def wrote_to_delta(trace) -> Feedback:
    """Inspect tool-call spans for a Delta write (saveAsTable or CREATE TABLE ... USING DELTA)."""
    spans = trace.data.spans if hasattr(trace, "data") else []
    hits = []
    for s in spans:
        text = str(getattr(s, "inputs", "")) + str(getattr(s, "outputs", ""))
        low = text.lower()
        if "saveastable" in low or "create table" in low or "using delta" in low:
            hits.append(s.name)
    if hits:
        return Feedback(value="yes", rationale=f"Delta write observed in spans: {hits[:3]}")
    return Feedback(value="no", rationale="No saveAsTable / CREATE TABLE span found in trace.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Run the evaluation

# COMMAND ----------

results = mlflow.genai.evaluate(
    data=traces_df,
    scorers=[
        followed_databricks_best_practices,
        used_correct_api,
        produced_runnable_code,
        followed_constraints,
        wrote_to_delta,
    ],
)

print("Evaluation complete. Open the MLflow experiment UI → Evaluations tab to view:")
print(f"  https://{os.environ.get('DATABRICKS_HOST', 'e2-demo-field-eng.cloud.databricks.com').replace('https://','')}/ml/experiments/{EXPERIMENT_ID}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## What to show in the UI
# MAGIC
# MAGIC 1. **Evaluations tab** → the latest run contains one row per trace.
# MAGIC 2. Each column is one judge; cells are yes/no with a rationale tooltip.
# MAGIC 3. Click any failing cell → jumps directly to the trace span that triggered the failure.
# MAGIC 4. Sort by any judge column to isolate systematic failures (e.g., all traces
# MAGIC    failing `followed_constraints` → the skill layer in Section 4 is where we'll fix this).
