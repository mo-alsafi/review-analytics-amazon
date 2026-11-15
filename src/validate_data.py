
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sys

import duckdb


# ============================================================
# Configuration
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PARQUET_FILE = (
    PROJECT_ROOT / "data" / "interim" /
    "appliances_reviews.parquet"
)

RAW_MANIFEST = PROJECT_ROOT / "data" / "raw" / "manifest.json"

CONVERSION_REPORT = (
    PROJECT_ROOT / "data" / "interim" /
    "conversion_report.json"
)

REPORT_DIR = PROJECT_ROOT / "reports"

VALIDATION_REPORT = (
    REPORT_DIR / "data_validation_report.json"
)

CHUNK_SIZE = 8 * 1024 * 1024

EXPECTED_COLUMNS = [
    "rating",
    "title",
    "text",
    "images",
    "asin",
    "parent_asin",
    "user_id",
    "timestamp",
    "helpful_vote",
    "verified_purchase",
]

EXPECTED_TYPES = {
    "rating": "DOUBLE",
    "title": "VARCHAR",
    "text": "VARCHAR",
    "asin": "VARCHAR",
    "parent_asin": "VARCHAR",
    "user_id": "VARCHAR",
    "timestamp": "BIGINT",
    "helpful_vote": "BIGINT",
    "verified_purchase": "BOOLEAN",
}


# ============================================================
# Utilities
# ============================================================

def calculate_sha256(file_path):
    """Calculate file SHA-256 without loading it into memory."""

    sha256 = hashlib.sha256()

    with open(file_path, "rb") as file:
        for chunk in iter(
            lambda: file.read(CHUNK_SIZE),
            b""
        ):
            sha256.update(chunk)

    return sha256.hexdigest()


def load_json(file_path):
    """Load a JSON file."""

    if not file_path.exists():
        raise FileNotFoundError(
            f"Required file not found: {file_path}"
        )

    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def timestamp_to_utc(value):
    """Convert Unix milliseconds to readable UTC."""

    if value is None:
        return None

    return datetime.fromtimestamp(
        value / 1000,
        tz=timezone.utc
    ).isoformat()


# ============================================================
# Schema validation
# ============================================================

def validate_schema(connection):

    schema = connection.execute(
        """
        DESCRIBE
        SELECT *
        FROM read_parquet(?)
        """,
        [str(PARQUET_FILE)]
    ).fetchall()

    actual_columns = [row[0] for row in schema]

    if actual_columns != EXPECTED_COLUMNS:
        raise ValueError(
            "Column names or ordering do not match the expected schema.\n"
            f"Expected: {EXPECTED_COLUMNS}\n"
            f"Actual: {actual_columns}"
        )

    actual_types = {
        row[0]: row[1]
        for row in schema
    }

    for column, expected_type in EXPECTED_TYPES.items():

        actual_type = actual_types[column]

        if actual_type != expected_type:
            raise ValueError(
                f"Incorrect type for {column}: "
                f"expected {expected_type}, got {actual_type}"
            )

    images_type = actual_types["images"]

    if not (
        images_type.startswith("STRUCT(")
        and images_type.endswith("[]")
    ):
        raise ValueError(
            f"Unexpected images data type: {images_type}"
        )

    print("Schema validation passed.")

    return actual_types


# ============================================================
# Data profiling and validation
# ============================================================

def profile_dataset(connection):

    query = """
        SELECT

            COUNT(*) AS total_rows,

            COUNT(*) FILTER (
                WHERE rating IS NULL
                   OR rating NOT IN (1, 2, 3, 4, 5)
            ) AS invalid_rating_rows,

            MIN(rating) AS minimum_rating,
            MAX(rating) AS maximum_rating,

            COUNT(*) FILTER (
                WHERE timestamp IS NULL
            ) AS null_timestamp_rows,

            MIN(timestamp) AS minimum_timestamp,
            MAX(timestamp) AS maximum_timestamp,

            COUNT(*) FILTER (
                WHERE verified_purchase IS NULL
            ) AS null_verified_purchase_rows,

            COUNT(*) FILTER (
                WHERE title IS NULL
            ) AS null_title_rows,

            COUNT(*) FILTER (
                WHERE title IS NOT NULL
                  AND TRIM(title) = ''
            ) AS blank_title_rows,

            COUNT(*) FILTER (
                WHERE text IS NULL
            ) AS null_text_rows,

            COUNT(*) FILTER (
                WHERE text IS NOT NULL
                  AND TRIM(text) = ''
            ) AS blank_text_rows,

            COUNT(*) FILTER (
                WHERE asin IS NULL
            ) AS null_asin_rows,

            COUNT(*) FILTER (
                WHERE parent_asin IS NULL
            ) AS null_parent_asin_rows,

            COUNT(*) FILTER (
                WHERE user_id IS NULL
            ) AS null_user_id_rows,

            COUNT(*) FILTER (
                WHERE helpful_vote IS NULL
            ) AS null_helpful_vote_rows,

            COUNT(*) FILTER (
                WHERE helpful_vote < 0
            ) AS negative_helpful_vote_rows,

            COUNT(*) FILTER (
                WHERE images IS NULL
            ) AS null_images_rows,

            SUM(
                COALESCE(ARRAY_LENGTH(images), 0)
            ) AS total_image_attachments

        FROM read_parquet(?)
    """

    row = connection.execute(
        query,
        [str(PARQUET_FILE)]
    ).fetchone()

    columns = [
        "total_rows",
        "invalid_rating_rows",
        "minimum_rating",
        "maximum_rating",
        "null_timestamp_rows",
        "minimum_timestamp",
        "maximum_timestamp",
        "null_verified_purchase_rows",
        "null_title_rows",
        "blank_title_rows",
        "null_text_rows",
        "blank_text_rows",
        "null_asin_rows",
        "null_parent_asin_rows",
        "null_user_id_rows",
        "null_helpful_vote_rows",
        "negative_helpful_vote_rows",
        "null_images_rows",
        "total_image_attachments",
    ]

    metrics = dict(zip(columns, row))

    return metrics


# ============================================================
# Main validation
# ============================================================

def main():

    print("=" * 65)
    print("AMAZON APPLIANCES — DATA VALIDATION")
    print("=" * 65)

    # --------------------------------------------------------
    # 1. Load reference documents
    # --------------------------------------------------------

    manifest = load_json(RAW_MANIFEST)
    conversion = load_json(CONVERSION_REPORT)

    if not PARQUET_FILE.exists():
        raise FileNotFoundError(
            f"Parquet dataset not found: {PARQUET_FILE}"
        )

    expected_rows = manifest["review_row_count"]

    # --------------------------------------------------------
    # 2. Verify Parquet file integrity
    # --------------------------------------------------------

    print("\nChecking Parquet file integrity...")

    actual_checksum = calculate_sha256(PARQUET_FILE)

    if actual_checksum != conversion["output_sha256"]:
        raise ValueError(
            "Parquet SHA-256 does not match conversion report."
        )

    print("Parquet checksum verified.")

    if conversion["row_count"] != expected_rows:
        raise ValueError(
            "Conversion report row count does not match "
            "the raw manifest."
        )

    # --------------------------------------------------------
    # 3. Schema validation
    # --------------------------------------------------------

    connection = duckdb.connect(database=":memory:")

    try:

        print("\nValidating schema...")

        schema = validate_schema(connection)

        # ----------------------------------------------------
        # 4. Profile the dataset
        # ----------------------------------------------------

        print("\nProfiling dataset...")

        metrics = profile_dataset(connection)

    finally:
        connection.close()

    # --------------------------------------------------------
    # 5. Evaluate hard validation rules
    # --------------------------------------------------------

    failures = []

    if metrics["total_rows"] != expected_rows:
        failures.append(
            "Parquet row count does not match raw manifest."
        )

    if metrics["invalid_rating_rows"] > 0:
        failures.append(
            "Invalid ratings were detected."
        )

    # --------------------------------------------------------
    # 6. Format timestamp boundaries
    # --------------------------------------------------------

    minimum_timestamp_utc = timestamp_to_utc(
        metrics["minimum_timestamp"]
    )

    maximum_timestamp_utc = timestamp_to_utc(
        metrics["maximum_timestamp"]
    )

    # --------------------------------------------------------
    # 7. Build validation report
    # --------------------------------------------------------

    report = {
        "dataset": "Amazon Reviews 2023",
        "category": "Appliances",
        "validated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),

        "file": PARQUET_FILE.name,

        "file_size_bytes": PARQUET_FILE.stat().st_size,

        "sha256": actual_checksum,

        "schema": schema,

        "metrics": metrics,

        "timestamp_range_utc": {
            "minimum": minimum_timestamp_utc,
            "maximum": maximum_timestamp_utc
        },

        "validation": {
            "row_count_matches_manifest": (
                metrics["total_rows"] == expected_rows
            ),
            "ratings_within_1_to_5": (
                metrics["invalid_rating_rows"] == 0
            ),
            "schema_valid": True,
            "parquet_checksum_valid": True
        },

        "failures": failures
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    temporary_report = VALIDATION_REPORT.with_suffix(
        ".json.tmp"
    )

    with open(
        temporary_report,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            report,
            file,
            indent=4,
            ensure_ascii=False
        )

    temporary_report.replace(VALIDATION_REPORT)

    # --------------------------------------------------------
    # 8. Display results
    # --------------------------------------------------------

    print("\n" + "=" * 65)
    print("VALIDATION RESULTS")
    print("=" * 65)

    for name, value in metrics.items():
        print(f"{name:35} {value}")

    print("\nTimestamp range (UTC):")
    print("Minimum:", minimum_timestamp_utc)
    print("Maximum:", maximum_timestamp_utc)

    print("\nSchema:")
    for column, data_type in schema.items():
        print(f"{column:25} {data_type}")

    print("\nHard validation failures:", len(failures))

    if failures:
        for failure in failures:
            print("FAIL:", failure)

        print("\nDATA VALIDATION FAILED")
        sys.exit(1)

    print("\nDATA VALIDATION PASSED")
    print("Report:", VALIDATION_REPORT)


if __name__ == "__main__":

    try:
        main()

    except Exception as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        sys.exit(1)
