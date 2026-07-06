import argparse
import json
import logging
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


def write_dataset(
    json_files: list[Path],
    output_dir: Path,
    granularity: str,
    partition_date: str,
) -> None:
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    for json_file in json_files:
        log.info(
            "[%s] Reading %s",
            granularity,
            json_file,
        )

        payload = read_payload(json_file)

        row_count = payload.get(
            "row_count",
            len(payload.get("data", {})),
        )

        if row_count == 0:
            log.info(
                "[%s] Skipping confirmed-empty bucket %s",
                granularity,
                json_file.name,
            )
            continue

        table = transform(payload)

        table = add_parquet_metadata(
            table,
            granularity,
            partition_date,
        )

        output_file = (
            output_dir
            / f"{json_file.stem}.parquet"
        )

        pq.write_table(
            table,
            output_file,
            compression="snappy",
        )

        log.info(
            "[%s] Wrote %d rows to %s",
            granularity,
            table.num_rows,
            output_file,
        )


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
        default=date_to_str(
            get_prior_date(date.today())
        ),
        help="Partition date YYYY-MM-DD.",
    )

    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help="Overwrite existing parquet files.",
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

    json_files = landing_paths(
        args.landing_root,
        args.date,
    )

    if not json_files:
        raise FileNotFoundError(
            f"No landing JSON files found for "
            f"{args.granularity} {args.date}"
        )

    output_dir = stage_path(
        args.output_root,
        args.date,
    )

    if (
        output_dir.exists()
        and any(output_dir.glob("*.parquet"))
        and not args.force_overwrite
    ):
        log.info(
            "[%s] Skipping existing dataset %s",
            args.granularity,
            output_dir,
        )
        return

    if args.force_overwrite and output_dir.exists():
        for parquet_file in output_dir.glob(
            "*.parquet"
        ):
            parquet_file.unlink()

    log.info(
        "[%s] Found %d landing file(s)",
        args.granularity,
        len(json_files),
    )

    write_dataset(
        json_files,
        output_dir,
        args.granularity,
        args.date,
    )

    log.info(
        "[%s] Finished staging dataset %s",
        args.granularity,
        output_dir,
    )


if __name__ == "__main__":
    main()
