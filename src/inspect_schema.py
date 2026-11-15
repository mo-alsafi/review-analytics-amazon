from pathlib import Path
import duckdb
import gzip
import json
import sys


# ============================================================
# Configuration
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

RAW_FILE = PROJECT_ROOT / "data" / "raw" / "Appliances.jsonl.gz"
MANIFEST_FILE = PROJECT_ROOT / "data" / "raw" / "manifest.json"


# ============================================================
# Schema inspection
# ============================================================

def inspect_schema(connection):
    """
    Infer the complete dataset schema using DuckDB.

    sample_size=-1 means all records participate in
    automatic schema detection.
    """

    query = """
        DESCRIBE
        SELECT *
        FROM read_json_auto(
            ?,
            format = 'newline_delimited',
            compression = 'gzip',
            sample_size = -1
        )
    """

    return connection.execute(
        query,
        [str(RAW_FILE)]
    ).fetchall()


# ============================================================
# First-record inspection
# ============================================================

def inspect_first_record():
    """Read one raw JSON record for a value-level preview."""

    with gzip.open(
        RAW_FILE,
        mode="rt",
        encoding="utf-8"
    ) as file:

        for line in file:
            if line.strip():
                return json.loads(line)

    raise ValueError("No records found in the raw dataset.")


def format_value(value, max_length=180):
    """Format sample values without printing excessively long text."""

    if isinstance(value, (dict, list)):
        value = json.dumps(
            value,
            ensure_ascii=False,
            default=str
        )
    else:
        value = repr(value)

    if len(value) > max_length:
        value = value[:max_length] + "..."

    return value


# ============================================================
# Main
# ============================================================

def main():

    if not RAW_FILE.exists():
        raise FileNotFoundError(
            f"Dataset not found: {RAW_FILE}"
        )

    if not MANIFEST_FILE.exists():
        raise FileNotFoundError(
            f"Manifest not found: {MANIFEST_FILE}"
        )

    with open(MANIFEST_FILE, "r", encoding="utf-8") as file:
        manifest = json.load(file)

    actual_size = RAW_FILE.stat().st_size
    expected_size = manifest["file_size_bytes"]

    if actual_size != expected_size:
        raise ValueError(
            "Raw file size does not match the manifest."
        )

    print("=" * 65)
    print("AMAZON APPLIANCES — SCHEMA INSPECTION")
    print("=" * 65)

    print("File:", RAW_FILE.name)
    print("Expected records:", f"{manifest['review_row_count']:,}")
    print("File size:", f"{actual_size:,} bytes")

    connection = duckdb.connect(database=":memory:")

    try:

        print("\nInspecting schema with DuckDB...")
        print("DuckDB default schema inference enabled.")
        schema = inspect_schema(connection)

        print("\n" + "=" * 65)
        print("INFERRED SCHEMA")
        print("=" * 65)

        print(f"{'COLUMN NAME':35} {'DATA TYPE'}")
        print("-" * 65)

        for column in schema:
            column_name = column[0]
            column_type = column[1]

            print(f"{column_name:35} {column_type}")

        print("\nTotal columns:", len(schema))

        # Inspect a representative raw record.
        first_record = inspect_first_record()

        print("\n" + "=" * 65)
        print("FIRST RECORD — VALUE PREVIEW")
        print("=" * 65)

        for key, value in first_record.items():
            print(
                f"{key:25} {format_value(value)}"
            )

        print("\n" + "=" * 65)
        print("SCHEMA INSPECTION COMPLETED")
        print("=" * 65)

    finally:
        connection.close()


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        sys.exit(1)
