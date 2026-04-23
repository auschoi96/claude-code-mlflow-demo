# Task 3 — Fix a subtle Spark UDF bug

The file `buggy_udf.py` below contains a UDF that is supposed to normalize phone numbers to E.164 format. It passes unit tests on a tiny sample but fails at scale.

```python
# buggy_udf.py
from pyspark.sql import SparkSession
from pyspark.sql.functions import udf
from pyspark.sql.types import StringType
import re

spark = SparkSession.builder.getOrCreate()

_country_code_cache = {}  # module-level mutable state

def normalize_phone(raw: str, default_country: str = "US") -> str:
    if raw is None:
        return None
    digits = re.sub(r"\D", "", raw)
    if default_country not in _country_code_cache:
        _country_code_cache[default_country] = {"US": "1", "GB": "44", "DE": "49"}[default_country]
    cc = _country_code_cache[default_country]
    if digits.startswith(cc):
        return f"+{digits}"
    return f"+{cc}{digits}"

normalize_phone_udf = udf(normalize_phone, StringType())

df = spark.read.table("main.demo.contacts")
result = df.withColumn("phone_e164", normalize_phone_udf("phone"))
result.write.mode("overwrite").saveAsTable("main.demo.contacts_clean")
```

Your task:

1. Identify the bug(s). (Hint: mutable state + UDFs + multiple executors is trouble, and there's also a correctness edge case around country codes.)
2. Fix the code. Keep it as a UDF (do not convert to built-in `regexp_replace` — the customer insists on UDF for extensibility).
3. Write a PySpark test in `test_normalize_phone.py` that would catch the bug you fixed.
4. Run the test with `pytest test_normalize_phone.py -v`.

Constraints:
- Keep the UDF a Python UDF (not pandas UDF, not SQL UDF) — the customer is on an older runtime.
- Do not change the function signature.
