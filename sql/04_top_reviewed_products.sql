
-- ============================================================
-- Query 04: Top Reviewed Products
--
-- Business question:
-- Which product groups receive the most customer reviews?
--
-- Product definition:
-- parent_asin = product group
--
-- Additional metrics:
-- 1. Review volume
-- 2. Number of product variations
-- 3. Average rating
-- 4. Negative review count
-- 5. Negative review share
-- ============================================================

WITH product_metrics AS (

    SELECT

        parent_asin,

        COUNT(*) AS review_count,

        COUNT(DISTINCT asin) AS variant_count,

        AVG(rating) AS average_rating,

        COUNT(*) FILTER (
            WHERE rating <= 2
        ) AS negative_review_count

    FROM read_parquet(
        'data/interim/appliances_reviews.parquet'
    )

    GROUP BY parent_asin

),

ranked_products AS (

    SELECT

        parent_asin,

        review_count,

        variant_count,

        average_rating,

        negative_review_count,

        RANK() OVER (
            ORDER BY review_count DESC
        ) AS review_rank,

        SUM(review_count) OVER () AS total_reviews

    FROM product_metrics

)

SELECT

    parent_asin,

    review_rank,

    review_count,

    variant_count,

    ROUND(
        average_rating,
        3
    ) AS average_rating,

    negative_review_count,

    ROUND(
        100.0 * negative_review_count / review_count,
        2
    ) AS negative_review_share_pct,

    ROUND(
        100.0 * review_count / total_reviews,
        4
    ) AS category_review_share_pct

FROM ranked_products

WHERE review_rank <= 20

ORDER BY review_rank, parent_asin;
