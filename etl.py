from pyspark.sql.functions import col, current_timestamp, row_number, to_date
from pyspark.sql.window import Window

CATALOG = "main"
SCHEMA = "demo"
SOURCE_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw/orders.json"
TARGET_TABLE = f"{CATALOG}.{SCHEMA}.orders_clean"

SCHEMA_DDL = "order_id STRING, customer_id STRING, total DOUBLE, ordered_at TIMESTAMP"

try:
    spark  # provided by Databricks runtime
except NameError:
    from databricks.connect import DatabricksSession
    spark = DatabricksSession.builder.serverless().getOrCreate()

raw = spark.read.schema(SCHEMA_DDL).json(SOURCE_PATH)
before_count = raw.count()

window = Window.partitionBy("order_id").orderBy(col("ordered_at").desc())
deduped = (
    raw.withColumn("_rn", row_number().over(window))
    .filter(col("_rn") == 1)
    .drop("_rn")
    .withColumn("loaded_at", current_timestamp())
    .withColumn("ordered_date", to_date("ordered_at"))
)
after_count = deduped.count()

print(f"Rows before dedup: {before_count}")
print(f"Rows after dedup:  {after_count}")

(
    deduped.write.format("delta")
    .mode("overwrite")
    .partitionBy("ordered_date")
    .saveAsTable(TARGET_TABLE)
)
