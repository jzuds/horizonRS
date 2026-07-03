import argparse
import json
import logging
import os, uuid
from datetime import datetime, timezone
from pathlib import Path
from datetime import date
import sys

import pyarrow as pa
import pyarrow.parquet as pq

try:
    CURRENT_DIR = Path(__file__).resolve().parent
except NameError:
    CURRENT_DIR = Path.cwd()

SRC_DIR = CURRENT_DIR.parent
sys.path.append(str(SRC_DIR))

from utility.utilities import get_prior_date, date_to_str, str_to_date


log = logging.getLogger(__name__)

PARQUET_SCHEMA = pa.schema([
    ("item_id", pa.int32()),
    ("avg_high_price", pa.int64()),
    ("high_price_volume", pa.int64()),
    ("avg_low_price", pa.int64()),
    ("low_price_volume", pa.int64()),
    ("api_timestamp", pa.timestamp("ns", tz="UTC")),
    ("snapshot_ts", pa.timestamp("ns", tz="UTC")),
    ("ingested_at", pa.timestamp("ns", tz="UTC")),
])


def landing_path(root: str, partition_key: str) -> Path:
    return Path(root) / f"date={partition_key}" / "daily_price.json"


def stage_path(root: str, partition_key: str) -> Path:
    return Path(root) / f"date={partition_key}" / "daily_price.parquet"


def read_payload(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(path)

    with path.open("r") as f:
        return json.load(f)


def transform(payload: dict) -> pa.Table:
    raw = payload.get("data")

    if not isinstance(raw, dict):
        raise ValueError("Expected payload['data'] to be a dictionary.")

    # 'timestamp' is unix epoch seconds; snapshot_ts/ingested_at are already ISO 8601 with offset
    api_timestamp = datetime.fromtimestamp(payload["timestamp"], tz=timezone.utc)
    snapshot_ts = datetime.fromisoformat(payload["snapshot_ts"])
    ingested_at = datetime.fromisoformat(payload["ingested_at"])

    item_ids, avg_high, high_vol, avg_low, low_vol = [], [], [], [], []

    for item_id, values in raw.items():
        if not isinstance(values, dict):
            continue

        item_ids.append(int(item_id))
        avg_high.append(values.get("avgHighPrice"))
        high_vol.append(values.get("highPriceVolume"))
        avg_low.append(values.get("avgLowPrice"))
        low_vol.append(values.get("lowPriceVolume"))

    n = len(item_ids)

    table = pa.table(
        {
            "item_id": pa.array(item_ids, type=pa.int32()),
            "avg_high_price": pa.array(avg_high, type=pa.int64()),
            "high_price_volume": pa.array(high_vol, type=pa.int64()),
            "avg_low_price": pa.array(avg_low, type=pa.int64()),
            "low_price_volume": pa.array(low_vol, type=pa.int64()),
            "api_timestamp": pa.array([api_timestamp] * n, type=pa.timestamp("ns", tz="UTC")),
            "snapshot_ts": pa.array([snapshot_ts] * n, type=pa.timestamp("ns", tz="UTC")),
            "ingested_at": pa.array([ingested_at] * n, type=pa.timestamp("ns", tz="UTC")),
        },
        schema=PARQUET_SCHEMA,
    )

    return table.sort_by("item_id")


def write_stage(table: pa.Table, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = path.with_suffix(f".tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}")

    try:
        pq.write_table(table, tmp_path, compression="snappy")
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    log.info("Wrote %d rows to %s", table.num_rows, path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage OSRS GE 24h price snapshot into typed Parquet."
    )

    parser.add_argument(
        "--landing-root",
        required=True,
        help="Root directory of landing JSON files.",
    )

    parser.add_argument(
        "--output-root",
        required=True,
        help="Root directory for staged Parquet output.",
    )

    parser.add_argument(
        "--date",
        required=False,
        default=get_prior_date(date.today()),
        help="Partition date (YYYY-MM-DD).",
    )

    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help="Overwrite existing staged output.",
    )

    return parser.parse_args()


def main() -> None:

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    args = parse_args()

    date_partition = date_to_str(args.date)

    input_path = landing_path(
        args.landing_root,
        date_partition,
    )

    output_path = stage_path(
        args.output_root,
        date_partition,
    )

    if output_path.exists() and not args.force_overwrite:
        log.info("Skipping existing staged file %s", output_path)
        return

    log.info("Reading %s", input_path)

    payload = read_payload(input_path)

    table = transform(payload)

    log.info(
        "Transformed %d rows × %d columns",
        table.num_rows,
        table.num_columns,
    )

    write_stage(table, output_path)


if __name__ == "__main__":
    main()