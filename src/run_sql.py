from pathlib import Path
import argparse
import os
import sys

import duckdb


# ============================================================
# Configuration
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SQL_DIR = PROJECT_ROOT / "sql"


# ============================================================
# SQL discovery
# ============================================================

def discover_sql_files():
    """
    Discover SQL files in the project's SQL directory.

    Files are sorted alphabetically to ensure
    deterministic execution order.
    """

    if not SQL_DIR.exists():
        raise FileNotFoundError(
            f"SQL directory not found: {SQL_DIR}"
        )

    return sorted(SQL_DIR.glob("*.sql"))


def resolve_sql_file(filename):
    """
    Resolve a requested SQL file safely.

    Only SQL files directly inside the SQL directory
    are accepted.
    """

    requested_path = Path(filename)

    if (
        requested_path.name != filename
        or requested_path.suffix.lower() != ".sql"
    ):
        raise ValueError(
            "Provide a SQL filename inside the sql directory, "
            "for example: 01_rating_distribution.sql"
        )

    sql_file = (SQL_DIR / filename).resolve()

    if sql_file.parent != SQL_DIR.resolve():
        raise ValueError("SQL file must be inside the SQL directory.")

    if not sql_file.is_file():
        raise FileNotFoundError(
            f"SQL file not found: {sql_file}"
        )

    return sql_file


# ============================================================
# SQL execution
# ============================================================

def execute_sql_file(sql_file):
    """
    Execute one SQL file using an independent
    in-memory DuckDB connection.
    """

    print("\n" + "=" * 70)
    print(f"EXECUTING: {sql_file.name}")
    print("=" * 70)

    sql_query = sql_file.read_text(encoding="utf-8")

    if not sql_query.strip():
        raise ValueError("SQL file is empty.")

    connection = duckdb.connect(database=":memory:")

    try:

        result = connection.execute(sql_query)

        if result.description is None:
            print("\nQuery executed successfully.")
            return

        dataframe = result.fetchdf()

        print("\nQUERY RESULTS")
        print("-" * 70)

        print(
            dataframe.to_string(index=False)
            if not dataframe.empty
            else "Query returned no rows."
        )

        print("-" * 70)
        print(f"Rows returned: {len(dataframe):,}")

        print("\nSQL execution successful.")

    finally:
        connection.close()


# ============================================================
# Command-line interface
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="Execute project SQL analysis files using DuckDB."
    )

    parser.add_argument(
        "sql_file",
        nargs="?",
        help="Name of the SQL file to execute."
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Execute all SQL files in alphabetical order."
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List available SQL files."
    )

    args = parser.parse_args()

    if args.list:

        if args.all or args.sql_file:
            parser.error("--list cannot be combined with other options.")

        files = discover_sql_files()

        print("\nAVAILABLE SQL FILES")
        print("-" * 40)

        if not files:
            print("No SQL files found.")
        else:
            for file in files:
                print(file.name)

        return 0

    if args.all and args.sql_file:
        parser.error("Specify either a SQL file or --all, not both.")

    if not args.all and not args.sql_file:
        parser.error("Provide a SQL filename or use --all.")

    # --------------------------------------------------------
    # Ensure all project-relative paths resolve from the root.
    # --------------------------------------------------------

    os.chdir(PROJECT_ROOT)

    try:

        if args.all:

            sql_files = discover_sql_files()

            if not sql_files:
                print("No SQL files found.")
                return 0

            print(f"\nFound {len(sql_files)} SQL files.")

        else:

            sql_files = [
                resolve_sql_file(args.sql_file)
            ]

        successful = 0
        failed = []

        # ----------------------------------------------------
        # Execute each SQL file independently.
        # ----------------------------------------------------

        for sql_file in sql_files:

            try:

                execute_sql_file(sql_file)
                successful += 1

            except Exception as error:

                failed.append(sql_file.name)

                print(
                    f"\nFAILED: {sql_file.name}",
                    file=sys.stderr
                )

                print(
                    f"Reason: {error}",
                    file=sys.stderr
                )

        # ----------------------------------------------------
        # Execution summary
        # ----------------------------------------------------

        print("\n" + "=" * 70)
        print("SQL EXECUTION SUMMARY")
        print("=" * 70)

        print(f"Successful: {successful}")
        print(f"Failed:     {len(failed)}")
        print(f"Total:      {len(sql_files)}")

        if failed:

            print("\nFailed files:")

            for filename in failed:
                print(f"- {filename}")

            return 1

        print("\nALL SQL FILES EXECUTED SUCCESSFULLY")

        return 0

    except Exception as error:

        print(
            f"\nERROR: {error}",
            file=sys.stderr
        )

        return 1


if __name__ == "__main__":
    sys.exit(main())