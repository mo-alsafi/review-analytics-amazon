
-- ============================================================
-- Query 02: Monthly Review Volume
--
-- Business question:
-- How does customer review activity change over time?
--
-- Improvements:
-- 1. Generate a continuous monthly calendar.
-- 2. Include months with zero reviews.
-- 3. Increase percentage precision.
-- 4. Identify partial boundary months.
-- ============================================================

WITH source_reviews AS (

    SELECT

        DATE_TRUNC(
            'month',
            EPOCH_MS(timestamp)
        )::DATE AS review_month

    FROM read_parquet(
        'data/interim/appliances_reviews.parquet'
    )

),

date_bounds AS (

    SELECT

        MIN(review_month) AS first_month,
        MAX(review_month) AS last_month

    FROM source_reviews

),

month_spine AS (

    SELECT

        month_start::DATE AS review_month

    FROM date_bounds

    CROSS JOIN LATERAL generate_series(
        first_month,
        last_month,
        INTERVAL '1 month'
    ) AS months(month_start)

),

monthly_counts AS (

    SELECT

        review_month,

        COUNT(*)::BIGINT AS review_count

    FROM source_reviews

    GROUP BY review_month

),

monthly_reviews AS (

    SELECT

        calendar.review_month,

        COALESCE(
            actual.review_count,
            0
        )::BIGINT AS review_count,

        bounds.first_month,
        bounds.last_month

    FROM month_spine AS calendar

    CROSS JOIN date_bounds AS bounds

    LEFT JOIN monthly_counts AS actual

        ON calendar.review_month = actual.review_month

),

monthly_metrics AS (

    SELECT

        review_month,
        review_count,

        SUM(review_count) OVER () AS total_reviews,

        SUM(review_count) OVER (
            ORDER BY review_month
            ROWS BETWEEN UNBOUNDED PRECEDING
            AND CURRENT ROW
        ) AS cumulative_reviews,

        first_month,
        last_month

    FROM monthly_reviews

)

SELECT

    review_month,

    review_count,

    ROUND(
        100.0 * review_count /
        NULLIF(total_reviews, 0),
        6
    ) AS monthly_share_pct,

    CAST(
        cumulative_reviews AS BIGINT
    ) AS cumulative_reviews,

    CASE

        WHEN review_month = first_month
            THEN 'PARTIAL_FIRST_MONTH'

        WHEN review_month = last_month
            THEN 'PARTIAL_LAST_MONTH'

        WHEN review_count = 0
            THEN 'ZERO_REVIEW_MONTH'

        ELSE 'INTERIOR_MONTH'

    END AS month_status

FROM monthly_metrics

ORDER BY review_month;
