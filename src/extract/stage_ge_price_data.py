import argparse
import json
import logging
import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
import sys

import pyarrow as pa
import pyarrow.parquet as pq

try:
    CURRENT_DIR = Path(__file__).resolve().parent
except NameError:
    CURRENT_DIR = Path.cwd()

SRC_DIR = CURRENT_DIR.parent
sys.path.append(str(SRC_DIR))

from utility.utilities import get_prior_date, date_to_str

log = logging.getLogger(__name__)

GRANULARITIES = {
    "5m",
    "1h",
    "24h",
}


PARQUET_SCHEMA = pa.schema(
    [
        ("item_id", pa.int32()),
        ("avg_high_price", pa.int64()),
        ("high_price_volume", pa.int64()),
        ("avg_low_price", pa.int64()),
        ("low_price_volume", pa.int64()),
        ("api_timestamp", pa.int64()),
        ("snapshot_ts", pa.timestamp("us", tz="UTC")),
        ("ingested_at", pa.timestamp("us", tz="UTC")),
    ]
)


def landing_paths(
    root: str,
    partition_key: str,
) -> list[Path]:
    landing_dir = Path(root) / f"date={partition_key}"

    if not landing_dir.exists():
        raise FileNotFoundError(landing_dir)

    return sorted(
        landing_dir.glob("timestamp=*.json")
    )


def stage_path(
    root: str,
    partition_key: str,
) -> Path:
    return Path(root) / f"date={partition_key}"


def output_path_for(output_dir: Path, json_file: Path) -> Path:
    """The staged parquet path a given landing file maps to.

    One landing file (one bucket) -> one parquet file. Its existence is the
    idempotency marker: if it's there, this bucket has already been staged.
    """
    return output_dir / f"{json_file.stem}.parquet"


def read_payload(path: Path) -> dict:
    with path.open("r") as f:
        return json.load(f)


def transform(payload: dict) -> pa.Table:
    raw = payload.get("data")

    if not isinstance(raw, dict):
        raise ValueError(
            "Expected payload['data'] to be a dictionary."
        )

    api_timestamp = int(payload["timestamp"])

    snapshot_ts = datetime.fromisoformat(
        payload["snapshot_ts"]
    )

    ingested_at = datetime.fromisoformat(
        payload["ingested_at"]
    )

    item_ids = []
    avg_high = []
    high_vol = []
    avg_low = []
    low_vol = []

    for item_id, values in raw.items():
        if not isinstance(values, dict):
            continue

        item_ids.append(int(item_id))
        avg_high.append(values.get("avgHighPrice"))
        high_vol.append(values.get("highPriceVolume"))
        avg_low.append(values.get("avgLowPrice"))
        low_vol.append(values.get("lowPriceVolume"))

    count = len(item_ids)

    table = pa.table(
        {
            "item_id": pa.array(
                item_ids,
                type=pa.int32(),
            ),
            "avg_high_price": pa.array(
                avg_high,
                type=pa.int64(),
            ),
            "high_price_volume": pa.array(
                high_vol,
                type=pa.int64(),
            ),
            "avg_low_price": pa.array(
                avg_low,
                type=pa.int64(),
            ),
            "low_price_volume": pa.array(
                low_vol,
                type=pa.int64(),
            ),
            "api_timestamp": pa.array(
                [api_timestamp] * count,
                type=pa.int64(),
            ),
            "snapshot_ts": pa.array(
                [snapshot_ts] * count,
                type=pa.timestamp("us", tz="UTC"),
            ),
            "ingested_at": pa.array(
                [ingested_at] * count,
                type=pa.timestamp("us", tz="UTC"),
            ),
        },
        schema=PARQUET_SCHEMA,
    )

    return table.sort_by("item_id")


def add_parquet_metadata(
    table: pa.Table,
    granularity: str,
    partition_date: str,
) -> pa.Table:
    metadata = {
        b"source_system": b"osrs_ge",
        b"granularity": granularity.encode(),
        b"partition_date": partition_date.encode(),
        b"created_at": datetime.now(timezone.utc)
        .isoformat()
        .encode(),
    }

    existing_metadata = table.schema.metadata or {}

    return table.replace_schema_metadata(
        {
            **existing_metadata,
            **metadata,
        }
    )


def stage_one(
    json_file: Path,
    output_file: Path,
    granularity: str,
    partition_date: str,
) -> str:
    """Stage a single landing file. Returns 'staged' or 'confirmed_empty'.

    Writes to a temp path and atomically renames into place on success, per
    the platform's run contract, so a crash mid-write never leaves a partial
    parquet file behind for the next rerun to trip over.
    """
    payload = read_payload(json_file)

    row_count = payload.get(
        "row_count",
        len(payload.get("data", {})),
    )

    if row_count == 0:
        return "confirmed_empty"

    table = transform(payload)
    table = add_parquet_metadata(table, granularity, partition_date)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_file.with_suffix(
        f".tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}"
    )
    pq.write_table(table, tmp_path, compression="snappy")
    tmp_path.replace(output_file)

    return "staged"


def write_dataset(
    json_files: list[Path],
    output_dir: Path,
    granularity: str,
    partition_date: str,
    force_overwrite: bool,
    stop_on_error: bool,
) -> dict:
    """Stage every landing file that hasn't been staged yet.

    Idempotency is per-bucket (per landing file), not per-day: a file whose
    output parquet already exists is skipped, everything else is staged.
    This is what makes it safe to call after every extraction run throughout
    the day -- each call only does work for buckets landed since the last one.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    staged, skipped_existing, skipped_empty, failed = 0, 0, 0, 0

    for json_file in json_files:
        output_file = output_path_for(output_dir, json_file)

        if output_file.exists() and not force_overwrite:
            skipped_existing += 1
            continue

        try:
            outcome = stage_one(json_file, output_file, granularity, partition_date)

            if outcome == "confirmed_empty":
                skipped_empty += 1
                log.info(
                    "[%s] Skipping confirmed-empty bucket %s",
                    granularity, json_file.name,
                )
            else:
                staged += 1
                log.info(
                    "[%s] Staged %s -> %s",
                    granularity, json_file.name, output_file,
                )

        except Exception:
            failed += 1
            log.exception(
                "[%s] Failed to stage %s", granularity, json_file,
            )
            if stop_on_error:
                raise

    return {
        "staged": staged,
        "skipped_existing": skipped_existing,
        "skipped_empty": skipped_empty,
        "failed": failed,
    }


def preview_dataset(
    json_files: list[Path],
    output_dir: Path,
    force_overwrite: bool,
) -> dict:
    """Report-only classification, mirroring extract's --report-only mode.

    Doesn't write anything -- useful for checking whether a staging run is
    actually needed before running one.
    """
    to_stage, already_staged, confirmed_empty, unreadable = 0, 0, 0, 0

    for json_file in json_files:
        output_file = output_path_for(output_dir, json_file)

        if output_file.exists() and not force_overwrite:
            already_staged += 1
            continue

        try:
            payload = read_payload(json_file)
        except (json.JSONDecodeError, OSError):
            unreadable += 1
            continue

        row_count = payload.get(
            "row_count",
            len(payload.get("data", {})),
        )

        if row_count == 0:
            confirmed_empty += 1
        else:
            to_stage += 1

    return {
        "to_stage": to_stage,
        "already_staged": already_staged,
        "confirmed_empty": confirmed_empty,
        "unreadable": unreadable,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Stage OSRS GE landing JSON files "
            "into a Parquet dataset."
        )
    )

    parser.add_argument(
        "--granularity",
        required=True,
        choices=sorted(GRANULARITIES),
        help="Price bucket size: 5m, 1h, or 24h.",
    )

    parser.add_argument(
        "--landing-root",
        required=True,
        help="Root directory containing landing JSON files.",
    )

    parser.add_argument(
        "--output-root",
        required=True,
        help="Root directory for staged parquet output.",
    )

    parser.add_argument(
        "--date",
        default=None,
        help="Partition date YYYY-MM-DD.",
    )

    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help="Re-stage landing files even if a parquet output already exists "
             "for them. Off by default: a plain rerun only stages buckets that "
             "haven't been staged yet, so it's safe (and cheap) to call after "
             "every extraction run throughout the day. Use this only if you "
             "suspect a previously-staged bucket is wrong, not for routine "
             "incremental staging.",
    )

    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Abort the whole run on the first landing file that fails to "
             "stage, instead of logging it and continuing with the rest.",
    )

    parser.add_argument(
        "--fail-on-incomplete",
        action="store_true",
        help="Raise if any landing file failed to stage this run.",
    )

    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Don't stage anything. Classify each landing file as "
             "already-staged, to-stage, confirmed-empty, or unreadable and "
             "print a summary. Use this to decide whether a staging run is "
             "actually needed before running one.",
    )

    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s "
            "[%(levelname)s] "
            "%(name)s: %(message)s"
        ),
    )

    args = parse_args()

    if args.date:
        price_date = args.date
    else:
        price_date = date_to_str(get_prior_date(date.today()))

    json_files = landing_paths(
        args.landing_root,
        price_date,
    )

    if not json_files:
        raise FileNotFoundError(
            f"No landing JSON files found for "
            f"{args.granularity} {price_date}"
        )

    output_dir = stage_path(
        args.output_root,
        price_date,
    )

    log.info(
        "[%s] Found %d landing file(s) for %s",
        args.granularity,
        len(json_files),
        price_date,
    )

    if args.report_only:
        report = preview_dataset(json_files, output_dir, args.force_overwrite)
        log.info(
            "[%s] Report date=%s to_stage=%d already_staged=%d "
            "confirmed_empty=%d unreadable=%d total=%d",
            args.granularity, price_date, report["to_stage"],
            report["already_staged"], report["confirmed_empty"],
            report["unreadable"], len(json_files),
        )
        return

    result = write_dataset(
        json_files,
        output_dir,
        args.granularity,
        price_date,
        force_overwrite=args.force_overwrite,
        stop_on_error=args.stop_on_error,
    )

    log.info(
        "[%s] Finished staging date=%s staged=%d skipped_existing=%d "
        "skipped_empty=%d failed=%d total_landing_files=%d",
        args.granularity, price_date, result["staged"],
        result["skipped_existing"], result["skipped_empty"],
        result["failed"], len(json_files),
    )

    if result["failed"] and args.fail_on_incomplete:
        raise RuntimeError(
            f"{result['failed']} of {len(json_files)} landing file(s) failed "
            f"to stage for {args.granularity} {price_date}."
        )


if __name__ == "__main__":
    main()