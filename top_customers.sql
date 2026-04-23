WITH customer_lifetime_spend AS (
    SELECT
        customer_id,
        country,
        SUM(total) AS lifetime_spend
    FROM main.demo.orders_clean
    GROUP BY customer_id, country
),
ranked_customers AS (
    SELECT
        customer_id,
        country,
        lifetime_spend,
        DENSE_RANK() OVER (
            PARTITION BY country
            ORDER BY lifetime_spend DESC
        ) AS spend_rank
    FROM customer_lifetime_spend
)
SELECT
    country,
    customer_id,
    CAST(ROUND(lifetime_spend, 2) AS DECIMAL(18, 2)) AS total_spend,
    spend_rank
FROM ranked_customers
WHERE spend_rank <= 5
ORDER BY country ASC, spend_rank ASC, customer_id ASC;