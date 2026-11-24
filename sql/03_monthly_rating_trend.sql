
-- ============================================================
-- Query 03: Monthly Rating Trend
--
-- Business question:
-- How does average customer rating change over time?
--
-- Additional metrics:
-- 1. Monthly review volume
-- 2. Average rating
-- 3. Negative star-derived review count
-- 4. Negative star-derived review share
-- 5. Calendar month coverage
-- ============================================================

WITH source_reviews AS (

    SELECT

        DATE_TRUNC(
            'month',
            EPOCH_MS(timestamp)
        )::DATE AS review_month,

        rating

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

monthly_metrics AS (

    SELECT

        review_month,

        COUNT(*) AS review_count,

        AVG(rating) AS average_rating,

        COUNT(*) FILTER (
            WHERE rating <= 2
        ) AS negative_review_count,

        COUNT(*) FILTER (
            WHERE rating = 3
        ) AS neutral_review_count

    FROM source_reviews

    GROUP BY review_month

),

monthly_calendar AS (

    SELECT

        calendar.review_month,

        COALESCE(
            metrics.review_count,
            0
        ) AS review_count,

        metrics.average_rating,

        COALESCE(
            metrics.negative_review_count,
            0
        ) AS negative_review_count,

        COALESCE(
            metrics.neutral_review_count,
            0
        ) AS neutral_review_count,

        bounds.first_month,
        bounds.last_month

    FROM month_spine AS calendar

    CROSS JOIN date_bounds AS bounds

    LEFT JOIN monthly_metrics AS metrics

        ON calendar.review_month = metrics.review_month

)

SELECT

    review_month,

    review_count,

    ROUND(
        average_rating,
        3
    ) AS average_rating,

    negative_review_count,

    CASE

        WHEN review_count = 0 THEN NULL

        ELSE ROUND(
            100.0 * negative_review_count / review_count,
            2
        )

    END AS negative_star_share_pct,

    neutral_review_count,

    CASE

        WHEN review_month = first_month
            THEN 'PARTIAL_FIRST_MONTH'

        WHEN review_month = last_month
            THEN 'PARTIAL_LAST_MONTH'

        WHEN review_count = 0
            THEN 'ZERO_REVIEW_MONTH'

        ELSE 'INTERIOR_MONTH'

    END AS month_status

FROM monthly_calendar

ORDER BY review_month;
