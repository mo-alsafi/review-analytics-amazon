
-- ============================================================
-- Query 07: Review Text-Length Distribution
--
-- Business question:
-- How is review-body length distributed across the dataset?
--
-- Measurements:
-- 1. Review counts by character-length band
-- 2. Percentage of total reviews
-- 3. Cumulative percentage
-- 4. Mean and median body length
-- 5. 90th, 95th and 99th percentiles
-- 6. Number of blank review bodies
--
-- Note:
-- Only the review body is measured.
-- Review titles are excluded.
-- ============================================================

WITH review_lengths AS (

    SELECT

        LENGTH(
            TRIM(COALESCE(text, ''))
        ) AS text_length_chars

    FROM read_parquet(
        'data/interim/appliances_reviews.parquet'
    )

),

classified_reviews AS (

    SELECT

        text_length_chars,

        CASE

            WHEN text_length_chars = 0 THEN 1
            WHEN text_length_chars <= 50 THEN 2
            WHEN text_length_chars <= 100 THEN 3
            WHEN text_length_chars <= 250 THEN 4
            WHEN text_length_chars <= 500 THEN 5
            WHEN text_length_chars <= 1000 THEN 6
            WHEN text_length_chars <= 2000 THEN 7
            ELSE 8

        END AS band_order

    FROM review_lengths

),

length_bands AS (

    SELECT *
    FROM (
        VALUES

            (1, '0 characters (blank)'),
            (2, '1–50 characters'),
            (3, '51–100 characters'),
            (4, '101–250 characters'),
            (5, '251–500 characters'),
            (6, '501–1,000 characters'),
            (7, '1,001–2,000 characters'),
            (8, 'More than 2,000 characters')

    ) AS bands(band_order, length_band)

),

bucket_counts AS (

    SELECT

        band_order,

        COUNT(*) AS review_count

    FROM classified_reviews

    GROUP BY band_order

),

distribution AS (

    SELECT

        bands.band_order,

        bands.length_band,

        COALESCE(
            counts.review_count,
            0
        ) AS review_count

    FROM length_bands AS bands

    LEFT JOIN bucket_counts AS counts

        ON bands.band_order = counts.band_order

),

overall_statistics AS (

    SELECT

        COUNT(*) AS total_reviews,

        AVG(text_length_chars) AS average_body_length,

        MEDIAN(text_length_chars) AS median_body_length,

        QUANTILE_CONT(
            text_length_chars,
            0.90
        ) AS percentile_90,

        QUANTILE_CONT(
            text_length_chars,
            0.95
        ) AS percentile_95,

        QUANTILE_CONT(
            text_length_chars,
            0.99
        ) AS percentile_99,

        COUNT(*) FILTER (
            WHERE text_length_chars = 0
        ) AS blank_body_reviews

    FROM review_lengths

),

cumulative_distribution AS (

    SELECT

        band_order,

        length_band,

        review_count,

        SUM(review_count) OVER (
            ORDER BY band_order
            ROWS BETWEEN UNBOUNDED PRECEDING
            AND CURRENT ROW
        ) AS cumulative_reviews,

        SUM(review_count) OVER () AS total_reviews

    FROM distribution

)

SELECT

    distribution.length_band,

    distribution.review_count,

    ROUND(
        100.0 * distribution.review_count /
        NULLIF(distribution.total_reviews, 0),
        2
    ) AS review_share_pct,

    distribution.cumulative_reviews,

    ROUND(
        100.0 * distribution.cumulative_reviews /
        NULLIF(distribution.total_reviews, 0),
        2
    ) AS cumulative_share_pct,

    statistics.total_reviews,

    ROUND(
        statistics.average_body_length,
        2
    ) AS average_body_length_chars,

    statistics.median_body_length
        AS median_body_length_chars,

    ROUND(
        statistics.percentile_90,
        2
    ) AS p90_body_length_chars,

    ROUND(
        statistics.percentile_95,
        2
    ) AS p95_body_length_chars,

    ROUND(
        statistics.percentile_99,
        2
    ) AS p99_body_length_chars,

    statistics.blank_body_reviews

FROM cumulative_distribution AS distribution

CROSS JOIN overall_statistics AS statistics

ORDER BY distribution.band_order;
