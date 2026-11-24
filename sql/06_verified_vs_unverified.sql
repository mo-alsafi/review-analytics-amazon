
-- ============================================================
-- Query 06: Verified vs Unverified Reviews
--
-- Business question:
-- Do verified and unverified reviews differ in their
-- ratings and written feedback?
--
-- Metrics:
-- 1. Review volume
-- 2. Share of all reviews
-- 3. Average rating
-- 4. Negative-review share
-- 5. Five-star review share
-- 6. Average review-body length
-- 7. Median review-body length
-- 8. Blank review-body share
-- ============================================================

WITH verification_metrics AS (

    SELECT

        verified_purchase,

        COUNT(*) AS review_count,

        AVG(rating) AS average_rating,

        COUNT(*) FILTER (
            WHERE rating <= 2
        ) AS negative_review_count,

        COUNT(*) FILTER (
            WHERE rating = 5
        ) AS five_star_review_count,

        AVG(
            LENGTH(TRIM(text))
        ) AS average_text_length,

        MEDIAN(
            LENGTH(TRIM(text))
        ) AS median_text_length,

        COUNT(*) FILTER (
            WHERE TRIM(text) = ''
        ) AS blank_text_count

    FROM read_parquet(
        'data/interim/appliances_reviews.parquet'
    )

    GROUP BY verified_purchase

)

SELECT

    CASE

        WHEN verified_purchase = TRUE
            THEN 'Verified'

        WHEN verified_purchase = FALSE
            THEN 'Unverified'

    END AS purchase_status,

    review_count,

    ROUND(
        100.0 * review_count /
        SUM(review_count) OVER (),
        2
    ) AS review_share_pct,

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
        100.0 * five_star_review_count / review_count,
        2
    ) AS five_star_review_share_pct,

    ROUND(
        average_text_length,
        2
    ) AS average_text_length_chars,

    ROUND(
        median_text_length,
        2
    ) AS median_text_length_chars,

    ROUND(
        100.0 * blank_text_count / review_count,
        3
    ) AS blank_text_share_pct

FROM verification_metrics

ORDER BY verified_purchase DESC;
