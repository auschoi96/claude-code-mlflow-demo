# Task 2 — DBSQL query with CTEs + window function

Write a single Databricks SQL query in `top_customers.sql` that:

1. Reads from `main.demo.orders_clean` (the table produced by Task 1).
2. Uses a CTE to compute per-customer lifetime spend.
3. Uses a window function to rank customers by spend within each country.
4. Returns the top 5 customers per country, along with their total spend and rank.

Assume the table has columns: `order_id`, `customer_id`, `country`, `total`, `ordered_at`.

Constraints:
- One query, no intermediate CREATE TABLE or temp views.
- Must run on a DBSQL warehouse — avoid Spark-only syntax.
- Format the final spend to 2 decimal places.

When you're done, use the Databricks CLI (`databricks sql queries create ...` or `databricks api post /api/2.0/sql/statements`) to dry-run it against the workspace and report the first 10 rows.
