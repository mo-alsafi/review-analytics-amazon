
-- ============================================================
-- Query 05: Product Review Concentration
--
-- Business question:
-- How concentrated are customer reviews across products?
--
-- Product definition:
-- parent_asin = product group
--
-- Metrics:
-- 1. Total number of product groups
-- 2. Total number of reviews
-- 3. Number of products needed to account for 50%
-- 4. Number of products needed to account for 80%
-- 5. Number of products needed to account for 90%
-- 6. Share of all products needed for each threshold
-- ============================================================

WITH product_review_counts AS (

    SELECT

        parent_asin,

        COUNT(*) AS review_count

    FROM read_parquet(
        'data/interim/appliances_reviews.parquet'
    )

    GROUP BY parent_asin

),

ranked_products AS (

    SELECT

        parent_asin,

        review_count,

        ROW_NUMBER() OVER (
            ORDER BY review_count DESC, parent_asin
        ) AS product_rank,

        COUNT(*) OVER () AS total_products,

        SUM(review_count) OVER () AS total_reviews,

        SUM(review_count) OVER (
            ORDER BY review_count DESC, parent_asin
            ROWS BETWEEN UNBOUNDED PRECEDING
            AND CURRENT ROW
        ) AS cumulative_reviews

    FROM product_review_counts

),

concentration_summary AS (

    SELECT

        MAX(total_products) AS total_products,

        MAX(total_reviews) AS total_reviews,

        MIN(product_rank) FILTER (
            WHERE cumulative_reviews >= total_reviews * 0.50
        ) AS products_to_reach_50_pct,

        MIN(product_rank) FILTER (
            WHERE cumulative_reviews >= total_reviews * 0.80
        ) AS products_to_reach_80_pct,

        MIN(product_rank) FILTER (
            WHERE cumulative_reviews >= total_reviews * 0.90
        ) AS products_to_reach_90_pct

    FROM ranked_products

)

SELECT

    total_products,

    total_reviews,

    products_to_reach_50_pct,

    ROUND(
        100.0 * products_to_reach_50_pct / total_products,
        2
    ) AS product_share_for_50_pct,

    products_to_reach_80_pct,

    ROUND(
        100.0 * products_to_reach_80_pct / total_products,
        2
    ) AS product_share_for_80_pct,

    products_to_reach_90_pct,

    ROUND(
        100.0 * products_to_reach_90_pct / total_products,
        2
    ) AS product_share_for_90_pct

FROM concentration_summary;
