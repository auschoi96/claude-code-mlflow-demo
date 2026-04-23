# Task 1 — Delta Lake ETL skeleton

You're working in the `main.demo` schema on a Databricks workspace.

Write a Python script `etl.py` that:

1. Reads the JSON file `/Volumes/main/demo/raw/orders.json` (schema: `order_id STRING, customer_id STRING, total DOUBLE, ordered_at TIMESTAMP`).
2. Deduplicates on `order_id` keeping the latest `ordered_at`.
3. Adds a `loaded_at` column (`current_timestamp()`).
4. Writes the result to the Delta table `main.demo.orders_clean`, partitioned by day of `ordered_at`.
5. Prints the row count before and after dedup.

Constraints:
- Must be Databricks-idiomatic (use `spark.read.table` / `saveAsTable`, never pandas-on-driver).
- Must run on Serverless (no `.coalesce(1)`, no local file I/O, no `repartition(1)` hacks).
- Do not hardcode the catalog name; read it from a `CATALOG` variable at the top.

When you're done, run `python etl.py` to smoke-test it.
