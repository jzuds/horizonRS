import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

PARQUET_SCHEMA = pa.schema(
    [
        pa.field("item_id", pa.int32()),
        pa.field("avg_high_price", pa.int64(), nullable=True),
        pa.field("high_price_volume", pa.int64()),
        pa.field("avg_low_price", pa.int64(), nullable=True),
        pa.field("low_price_volume", pa.int64()),
        pa.field("snapshot_ts", pa.timestamp("us", tz="UTC")),
        pa.field("snapshot_date", pa.date32()),
        pa.field("ingestion_date", pa.date32()),
    ]
)

_INGESTION_DATE_RE = re.compile(r"ingestion_date=(\d{4}-\d{2}-\d{2})")

def _parse_ingestion_date(src_dir: Path) -> str:
    """Extract ingestion_date from the partition directory name."""
    match = _INGESTION_DATE_RE.search(str(src_dir))
    if not match:
        raise ValueError(
            f"Expected directory name to contain 'ingestion_date=YYYY-MM-DD', got: {src_dir}"
        )
    return match.group(1)

def _flatten(src: Path, ingestion_date: str) -> pd.DataFrame:
    """Flatten a single JSON snapshot into a DataFrame."""
    raw = json.loads(src.read_text())

    unix_ts = raw.get("timestamp")
    if unix_ts is None:
        raise ValueError(f"Missing 'timestamp' field in: {src}")
    snapshot_ts = datetime.fromtimestamp(unix_ts, tz=timezone.utc)

    records = raw.get("data", {})

    rows = [
        {
            "item_id": int(item_id_str),
            "avg_high_price": prices.get("avgHighPrice"),
            "high_price_volume": prices.get("highPriceVolume", 0),
            "avg_low_price": prices.get("avgLowPrice"),
            "low_price_volume": prices.get("lowPriceVolume", 0),
            "snapshot_ts": snapshot_ts,
            "snapshot_date": snapshot_ts.date(),
            "ingestion_date": ingestion_date,
        }
        for item_id_str, prices in records.items()
    ]

    df = pd.DataFrame(rows)
    df["avg_high_price"] = df["avg_high_price"].astype("Int64")
    df["avg_low_price"] = df["avg_low_price"].astype("Int64")
    df["high_price_volume"] = df["high_price_volume"].astype("int64")
    df["low_price_volume"] = df["low_price_volume"].astype("int64")
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"]).dt.date
    df["ingestion_date"] = pd.to_datetime(df["ingestion_date"]).dt.date
    return df

def transform_partition(src_dir: Path, dest: Path) -> list[Path]:
    """
    Process all JSON files in an ingestion_date partition directory.

    Returns a list of written Parquet paths.
    """
    json_files = sorted(src_dir.glob("*.json"))
    if not json_files:
        raise FileNotFoundError(f"No JSON files found in: {src_dir}")

    ingestion_date = _parse_ingestion_date(src_dir)

    written = []
    for src in json_files:
        df = _flatten(src, ingestion_date)
        snapshot_date = df["snapshot_date"].iloc[0]

        out_dir = dest / f"snapshot_date={snapshot_date}"
        out_dir.mkdir(parents=True, exist_ok=True)

        out_path = out_dir / f"{ingestion_date}.parquet"
        pq.write_table(
            pa.Table.from_pandas(df, schema=PARQUET_SCHEMA, preserve_index=False),
            out_path,
            compression="snappy",
        )
        print(f"[transform] {src.name} -> {out_path}  ({len(df):,} rows)")
        written.append(out_path)

    return written

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GE price transform: JSON partition -> Parquet")
    parser.add_argument(
        "--src-dir",
        required=True,
        type=Path,
        help="ingestion_date partition directory (e.g. output/ge_price_24h/ingestion_date=2026-03-17)",
    )
    parser.add_argument(
        "--dest",
        required=True,
        type=Path,
        help="Root of transformed output directory",
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = _parse_args()
    transform_partition(src_dir=args.src_dir, dest=args.dest)