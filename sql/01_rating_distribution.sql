-- ============================================================
-- Query 01: Rating Distribution
-- Business question:
-- How are customer ratings distributed across Appliances?
-- ============================================================

WITH rating_counts AS (
    SELECT
        rating,
        COUNT(*) AS review_count
    FROM read_parquet(
        'data/interim/appliances_reviews.parquet'
    )
    GROUP BY rating
),

rating_distribution AS (
    SELECT
        rating,
        review_count,
        SUM(review_count) OVER () AS total_reviews
    FROM rating_counts
)

SELECT
    CAST(rating AS INTEGER) AS rating,
    review_count,
    total_reviews,
    ROUND(
        100.0 * review_count / total_reviews,
        2
    ) AS review_share_pct,
    ROUND(
        100.0 * SUM(review_count) OVER (
            ORDER BY rating
            ROWS BETWEEN UNBOUNDED PRECEDING
            AND CURRENT ROW
        ) / total_reviews,
        2
    ) AS cumulative_share_pct
FROM rating_distribution

ORDER BY rating;