from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from datetime import datetime, timezone
import argparse
import gzip
import hashlib
import json
import re
import sys
import time


# ============================================================
# Configuration
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data" / "raw"
OUTPUT_FILE = DATA_DIR / "Appliances.jsonl.gz"
MANIFEST_FILE = DATA_DIR / "manifest.json"

SOURCE_URL = (
    "https://mcauleylab.ucsd.edu/public_datasets/data/"
    "amazon_2023/raw/review_categories/Appliances.jsonl.gz"
)

CHUNK_SIZE = 8 * 1024 * 1024  # 8 MiB


# ============================================================
# Utilities
# ============================================================

def format_size(size_bytes):
    """Convert bytes into a human-readable size."""
    return f"{size_bytes / (1024 ** 2):,.2f} MiB"


def sha256_file(file_path):
    """Calculate SHA-256 without loading the entire file into memory."""
    sha256 = hashlib.sha256()

    with open(file_path, "rb") as file:
        for chunk in iter(lambda: file.read(CHUNK_SIZE), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def utc_timestamp():
    """Return the current UTC timestamp."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


# ============================================================
# Remote file inspection
# ============================================================

def get_remote_metadata(url):
    """
    Retrieve remote file metadata without downloading the dataset.

    Try HEAD first. Fall back to a ranged GET if HEAD is unsupported.
    """

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    request = Request(
        url,
        headers=headers,
        method="HEAD"
    )

    try:
        with urlopen(request, timeout=30) as response:
            response_headers = response.headers

            content_length = response_headers.get("Content-Length")

            return {
                "status": response.status,
                "final_url": response.geturl(),
                "content_type": response_headers.get("Content-Type"),
                "content_length": (
                    int(content_length)
                    if content_length else None
                ),
                "last_modified": response_headers.get("Last-Modified")
            }

    except HTTPError as error:

        if error.code not in (403, 405, 501):
            raise

        print("HEAD request unavailable. Trying ranged GET...")

    # Fallback: request only the first byte.
    request = Request(
        url,
        headers={
            **headers,
            "Range": "bytes=0-0"
        }
    )

    with urlopen(request, timeout=30) as response:
        content_range = response.headers.get("Content-Range")
        match = re.search(r"/(\d+)$", content_range or "")

        content_length = response.headers.get("Content-Length")

        total_size = (
            int(match.group(1))
            if match
            else int(content_length)
            if content_length and response.status == 200
            else None
        )

        return {
            "status": response.status,
            "final_url": response.geturl(),
            "content_type": response.headers.get("Content-Type"),
            "content_length": total_size,
            "last_modified": response.headers.get("Last-Modified")
        }


def inspect_remote_file():
    """Display information about the remote dataset."""

    print("\nChecking remote dataset...\n")

    metadata = get_remote_metadata(SOURCE_URL)

    print("HTTP status:", metadata["status"])
    print("Final URL:", metadata["final_url"])
    print("Content type:", metadata["content_type"])
    print("Last modified:", metadata["last_modified"])

    size = metadata["content_length"]

    if size is not None:
        print("Compressed size:", format_size(size))
        print("Size in bytes:", f"{size:,}")
    else:
        print("Remote file size: Not provided by server")

    return metadata


# ============================================================
# Dataset validation
# ============================================================

def validate_jsonl_gzip(file_path):
    """
    Validate gzip integrity and JSONL structure.

    Reads one record at a time to avoid loading the dataset
    into memory.

    Returns:
        row_count
        first_record_keys
    """

    print("\nValidating compressed dataset...")

    row_count = 0
    first_record_keys = None

    with gzip.open(file_path, "rt", encoding="utf-8") as file:

        for line_number, line in enumerate(file, start=1):

            if not line.strip():
                continue

            try:
                record = json.loads(line)

            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid JSON at line {line_number}: {error}"
                ) from error

            if not isinstance(record, dict):
                raise ValueError(
                    f"Expected a JSON object at line {line_number}."
                )

            if first_record_keys is None:
                first_record_keys = sorted(record.keys())

            row_count += 1

            if row_count % 500_000 == 0:
                print(f"Validated {row_count:,} records...")

    if row_count == 0:
        raise ValueError("Dataset contains no valid records.")

    print(f"Validation completed: {row_count:,} records.")

    return row_count, first_record_keys


# ============================================================
# Download process
# ============================================================


def download_dataset(metadata, force=False):
    """Download, resume, validate and document the dataset."""

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if OUTPUT_FILE.exists() and not force:
        raise FileExistsError(
            f"{OUTPUT_FILE.name} already exists. "
            "Use --force to replace it."
        )

    temporary_file = OUTPUT_FILE.with_name(
        OUTPUT_FILE.name + ".part"
    )

    expected_size = metadata["content_length"]

    if expected_size is None:
        raise ValueError(
            "Cannot safely download: remote file size is unknown."
        )

    max_attempts = 5
    download_complete = False
    last_error = None

    print("\nStarting dataset download...")
    print("Expected size:", format_size(expected_size))

    # --------------------------------------------------------
    # Download with retry and resume support
    # --------------------------------------------------------

    for attempt in range(1, max_attempts + 1):

        current_size = (
            temporary_file.stat().st_size
            if temporary_file.exists()
            else 0
        )

        if current_size > expected_size:
            raise ValueError(
                "Partial download exceeds the expected file size."
            )

        if current_size == expected_size:
            download_complete = True
            break

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Encoding": "identity"
        }

        # Resume from the last successfully saved byte.
        if current_size > 0:

            headers["Range"] = f"bytes={current_size}-"

            if metadata.get("last_modified"):
                headers["If-Range"] = metadata["last_modified"]

            print(
                f"\nResuming from byte {current_size:,} "
                f"({current_size / expected_size * 100:.1f}%)."
            )

        else:
            print(f"\nDownload attempt {attempt}/{max_attempts}")

        request = Request(
            SOURCE_URL,
            headers=headers
        )

        try:

            with urlopen(request, timeout=90) as response:

                status = response.status

                # Determine whether the server honored our
                # resume request.
                if current_size > 0 and status == 206:

                    content_range = response.headers.get(
                        "Content-Range",
                        ""
                    )

                    match = re.fullmatch(
                        r"bytes\s+(\d+)-(\d+)/(\d+|\*)",
                        content_range
                    )

                    if not match:
                        raise ValueError(
                            "Invalid or missing Content-Range header."
                        )

                    range_start = int(match.group(1))
                    range_total = match.group(3)

                    if range_start != current_size:
                        raise ValueError(
                            "Server resumed from an unexpected byte."
                        )

                    if (
                        range_total != "*"
                        and int(range_total) != expected_size
                    ):
                        raise ValueError(
                            "Remote file size changed during download."
                        )

                    mode = "ab"

                elif current_size > 0 and status == 200:

                    # Server ignored Range or the validator changed.
                    # Start again from byte zero.
                    print(
                        "Server did not honor resume request. "
                        "Restarting from zero."
                    )

                    current_size = 0
                    mode = "wb"

                elif current_size == 0 and status == 200:

                    mode = "wb"

                else:
                    raise ValueError(
                        f"Unexpected HTTP response status: {status}"
                    )

                received_this_attempt = 0

                with open(temporary_file, mode) as output:

                    while True:

                        chunk = response.read(CHUNK_SIZE)

                        if not chunk:
                            break

                        output.write(chunk)

                        received_this_attempt += len(chunk)

                        total_received = (
                            current_size + received_this_attempt
                        )

                        percentage = (
                            total_received / expected_size
                        ) * 100

                        print(
                            f"\rDownloaded: "
                            f"{format_size(total_received)} "
                            f"({percentage:.1f}%)",
                            end="",
                            flush=True
                        )

            actual_size = temporary_file.stat().st_size

            if actual_size == expected_size:

                download_complete = True
                print("\nDownload completed.")
                break

            if actual_size > expected_size:
                raise ValueError(
                    "Downloaded file exceeds expected size."
                )

            last_error = (
                f"Connection ended early: "
                f"{actual_size:,}/{expected_size:,} bytes received."
            )

            print(f"\n{last_error}")

        except Exception as error:

            last_error = str(error)

            print(
                f"\nAttempt {attempt} failed: {last_error}"
            )

        # Preserve the partial download and retry.
        if not download_complete and attempt < max_attempts:

            delay = min(2 ** attempt, 10)

            print(
                f"Retrying in {delay} seconds. "
                "Partial data will be preserved."
            )

            time.sleep(delay)

    if not download_complete:

        partial_size = (
            temporary_file.stat().st_size
            if temporary_file.exists()
            else 0
        )

        raise OSError(
            f"Download could not be completed after {max_attempts} "
            f"attempts.\n"
            f"Received: {partial_size:,}/{expected_size:,} bytes.\n"
            f"Partial file preserved at: {temporary_file}\n"
            f"Run the download command again to resume.\n"
            f"Last error: {last_error}"
        )

    # --------------------------------------------------------
    # Validate downloaded file
    # --------------------------------------------------------

    print("\nValidating compressed dataset...")

    try:
        row_count, first_record_keys = validate_jsonl_gzip(
            temporary_file
        )

    except Exception:
        print(
            "Downloaded file failed validation. "
            "Preserving it for investigation."
        )
        raise

    checksum = sha256_file(temporary_file)

    # --------------------------------------------------------
    # Generate manifest
    # --------------------------------------------------------

    actual_size = temporary_file.stat().st_size

    manifest = {
        "dataset": "Amazon Reviews 2023",
        "category": "Appliances",
        "source_url": SOURCE_URL,
        "downloaded_at_utc": utc_timestamp(),
        "filename": OUTPUT_FILE.name,
        "format": "JSONL.GZ",
        "file_size_bytes": actual_size,
        "file_size_mib": round(
            actual_size / (1024 ** 2), 2
        ),
        "sha256": checksum,
        "review_row_count": row_count,
        "first_record_keys": first_record_keys,
        "remote_last_modified": metadata["last_modified"]
    }

    # --------------------------------------------------------
    # Finalize
    # --------------------------------------------------------

    temporary_file.replace(OUTPUT_FILE)

    temporary_manifest = MANIFEST_FILE.with_suffix(
        ".json.tmp"
    )

    with open(
        temporary_manifest,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            manifest,
            file,
            indent=4,
            ensure_ascii=False
        )

    temporary_manifest.replace(MANIFEST_FILE)

    print("\n" + "=" * 55)
    print("DATASET ACQUISITION SUCCESSFUL")
    print("=" * 55)

    print("File:", OUTPUT_FILE)
    print("Records:", f"{row_count:,}")
    print("Size:", format_size(actual_size))
    print("SHA-256:", checksum)
    print("Manifest:", MANIFEST_FILE)


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="Download and document Amazon Appliances reviews."
    )

    parser.add_argument(
        "--download",
        action="store_true",
        help="Actually download the dataset."
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing dataset after successful validation."
    )

    args = parser.parse_args()

    if args.force and not args.download:
        parser.error("--force requires --download.")

    try:

        metadata = inspect_remote_file()

        if args.download:
            download_dataset(
                metadata=metadata,
                force=args.force
            )

        else:
            print(
                "\nMetadata inspection only. "
                "No dataset was downloaded."
            )

            print(
                "Run again with --download to acquire the dataset."
            )

    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:

        print("\nERROR:", error, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()