
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import sys

import duckdb


# ============================================================
# Configuration
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_FILE = PROJECT_ROOT / "data" / "raw" / "Appliances.jsonl.gz"
RAW_MANIFEST = PROJECT_ROOT / "data" / "raw" / "manifest.json"

INTERIM_DIR = PROJECT_ROOT / "data" / "interim"

OUTPUT_FILE = INTERIM_DIR / "appliances_reviews.parquet"
TEMP_FILE = INTERIM_DIR / "appliances_reviews.tmp.parquet"

REPORT_FILE = INTERIM_DIR / "conversion_report.json"

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

# Reference metrics from our successful full-source scan.
REFERENCE_METRICS = {
    "row_count": 2_128_605,
    "minimum_rating": 1.0,
    "maximum_rating": 5.0,
    "title_characters": 47_553_980,
    "review_characters": 360_827_182,
    "image_attachments": 148_536,
}


# ============================================================
# Utilities
# ============================================================

def sha256_file(file_path):
    """Calculate SHA-256 without loading the entire file."""

    sha256 = hashlib.sha256()

    with open(file_path, "rb") as file:
        for chunk in iter(
            lambda: file.read(CHUNK_SIZE),
            b""
        ):
            sha256.update(chunk)

    return sha256.hexdigest()


def load_manifest():
    """Load the raw dataset manifest."""

    if not RAW_MANIFEST.exists():
        raise FileNotFoundError(
            f"Manifest not found: {RAW_MANIFEST}"
        )

    with open(RAW_MANIFEST, "r", encoding="utf-8") as file:
        return json.load(file)


def sql_string(value):
    """Safely construct a SQL string literal."""

    return "'" + str(value).replace("'", "''") + "'"


def describe_relation(connection, query):
    """Return column names and types for a SQL relation."""

    result = connection.execute(
        f"DESCRIBE {query}"
    ).fetchall()

    return [
        (row[0], row[1])
        for row in result
    ]


# ============================================================
# Source verification
# ============================================================

def verify_source(manifest):
    """Check raw file size and SHA-256 against its manifest."""

    if not RAW_FILE.exists():
        raise FileNotFoundError(
            f"Dataset not found: {RAW_FILE}"
        )

    actual_size = RAW_FILE.stat().st_size
    expected_size = manifest["file_size_bytes"]

    if actual_size != expected_size:
        raise ValueError(
            f"File size mismatch. "
            f"Expected {expected_size:,}, "
            f"received {actual_size:,}."
        )

    print("Calculating raw dataset SHA-256...")

    actual_checksum = sha256_file(RAW_FILE)
    expected_checksum = manifest["sha256"]

    if actual_checksum != expected_checksum:
        raise ValueError(
            "Raw dataset checksum does not match the manifest."
        )

    print("Source integrity verified.")

    return actual_checksum


# ============================================================
# Conversion and verification
# ============================================================

def convert_dataset(expected_rows, source_checksum, force=False):

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)

    if OUTPUT_FILE.exists() and not force:
        raise FileExistsError(
            f"{OUTPUT_FILE.name} already exists. "
            "Use --force to replace it."
        )

    if TEMP_FILE.exists():
        raise FileExistsError(
            f"Temporary output already exists: {TEMP_FILE}. "
            "Inspect or remove it before retrying."
        )

    connection = duckdb.connect(database=":memory:")

    try:

        # ----------------------------------------------------
        # 1. Define the source relation
        # ----------------------------------------------------

        print("\nInspecting source schema...")

        source_expression = f"""
            read_json_auto(
                {sql_string(RAW_FILE)},
                format = 'newline_delimited',
                compression = 'gzip',
                sample_size = -1
            )
        """

        source_query = f"SELECT * FROM {source_expression}"

        source_schema = describe_relation(
            connection,
            source_query
        )

        source_columns = [
            column[0]
            for column in source_schema
        ]

        if source_columns != EXPECTED_COLUMNS:
            raise ValueError(
                "Unexpected source columns.\n"
                f"Expected: {EXPECTED_COLUMNS}\n"
                f"Received: {source_columns}"
            )

        print("Source schema verified.")
        print("Columns:", len(source_schema))

        # ----------------------------------------------------
        # 2. Convert to Parquet
        # ----------------------------------------------------

        print("\nStarting Parquet conversion...")

        copy_query = f"""
            COPY (
                SELECT *
                FROM {source_expression}
            )
            TO {sql_string(TEMP_FILE)}
            (
                FORMAT PARQUET,
                COMPRESSION ZSTD
            )
        """

        connection.execute(copy_query)

        print("Parquet writing completed.")

        # ----------------------------------------------------
        # 3. Verify output schema
        # ----------------------------------------------------

        print("\nVerifying output schema...")

        parquet_query = (
            f"SELECT * FROM read_parquet("
            f"{sql_string(TEMP_FILE)})"
        )

        parquet_schema = describe_relation(
            connection,
            parquet_query
        )

        if source_schema != parquet_schema:
            raise ValueError(
                "Source and Parquet schemas do not match.\n"
                f"Source: {source_schema}\n"
                f"Parquet: {parquet_schema}"
            )

        print("Schema preservation verified.")

        # ----------------------------------------------------
        # 4. Verify converted data
        # ----------------------------------------------------

        print("\nRunning output validation...")

        metrics_query = f"""
            SELECT
                COUNT(*) AS row_count,
                MIN(rating) AS minimum_rating,
                MAX(rating) AS maximum_rating,
                SUM(LENGTH(title)) AS title_characters,
                SUM(LENGTH(text)) AS review_characters,
                SUM(
                    COALESCE(ARRAY_LENGTH(images), 0)
                ) AS image_attachments
            FROM read_parquet(
                {sql_string(TEMP_FILE)}
            )
        """

        row = connection.execute(
            metrics_query
        ).fetchone()

        metrics = {
            "row_count": row[0],
            "minimum_rating": row[1],
            "maximum_rating": row[2],
            "title_characters": row[3],
            "review_characters": row[4],
            "image_attachments": row[5],
        }

        print("\nVerified metrics:")

        for name, value in metrics.items():
            print(f"{name:25} {value:,}" if isinstance(value, int)
                  else f"{name:25} {value}")

        if metrics != REFERENCE_METRICS:
            raise ValueError(
                "Parquet metrics do not match the "
                "previously validated source metrics.\n"
                f"Expected: {REFERENCE_METRICS}\n"
                f"Received: {metrics}"
            )

        if metrics["row_count"] != expected_rows:
            raise ValueError(
                "Parquet row count does not match the manifest."
            )

        print("\nAll data verification checks passed.")

        # ----------------------------------------------------
        # 5. Calculate Parquet integrity information
        # ----------------------------------------------------

        output_size = TEMP_FILE.stat().st_size
        output_checksum = sha256_file(TEMP_FILE)

        # ----------------------------------------------------
        # 6. Finalize the output
        # ----------------------------------------------------

        TEMP_FILE.replace(OUTPUT_FILE)

        report = {
            "source_file": RAW_FILE.name,
            "output_file": OUTPUT_FILE.name,
            "duckdb_version": duckdb.__version__,
            "compression": "zstd",
            "row_count": metrics["row_count"],
            "column_count": len(parquet_schema),
            "schema": [
                {
                    "column": name,
                    "data_type": data_type
                }
                for name, data_type in parquet_schema
            ],
            "validation_metrics": metrics,
            "source_sha256": source_checksum,
            "output_sha256": output_checksum,
            "source_size_bytes": RAW_FILE.stat().st_size,
            "output_size_bytes": output_size,
            "output_size_mib": round(
                output_size / (1024 ** 2), 2
            ),
            "converted_at_utc": datetime.now(
                timezone.utc
            ).isoformat()
        }

        temporary_report = REPORT_FILE.with_suffix(
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

        temporary_report.replace(REPORT_FILE)

        # ----------------------------------------------------
        # 7. Final report
        # ----------------------------------------------------

        print("\n" + "=" * 60)
        print("PARQUET CONVERSION SUCCESSFUL")
        print("=" * 60)

        print("Rows:", f"{metrics['row_count']:,}")
        print("Columns:", len(parquet_schema))

        print(
            "Compressed source:",
            f"{RAW_FILE.stat().st_size:,} bytes"
        )

        print(
            "Parquet output:",
            f"{output_size:,} bytes"
        )

        size_change = (
            (1 - output_size / RAW_FILE.stat().st_size) * 100
        )

        print(
            "Size reduction:",
            f"{size_change:.2f}%"
        )

        print("Output:", OUTPUT_FILE)
        print("Report:", REPORT_FILE)

        print("\nParquet SHA-256:")
        print(output_checksum)

    finally:
        connection.close()

        # Remove incomplete output if conversion failed.
        if TEMP_FILE.exists():
            TEMP_FILE.unlink()


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="Convert Appliances JSONL.GZ to Parquet."
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing Parquet file after validation."
    )

    args = parser.parse_args()

    manifest = load_manifest()

    expected_rows = manifest["review_row_count"]

    source_checksum = verify_source(manifest)

    print("\nExpected source records:", f"{expected_rows:,}")

    convert_dataset(
        expected_rows=expected_rows,
        source_checksum=source_checksum,
        force=args.force
    )


if __name__ == "__main__":

    try:
        main()

    except Exception as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        sys.exit(1)
