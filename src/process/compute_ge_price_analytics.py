import argparse
import hashlib
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

PARQUET_WRITE_OPTIONS = dict(
    compression="zstd",
    compression_level=3,
    write_statistics=True,
    use_dictionary=False,
)

ITEM_HISTORY_SCHEMA = pa.schema(
    [
        pa.field("item_id", pa.int32()),
        pa.field("snapshot_date", pa.date32()),
        pa.field("snapshot_ts", pa.timestamp("us", tz="UTC")),
        pa.field("avg_high_price", pa.int64(), nullable=True),
        pa.field("avg_low_price", pa.int64(), nullable=True),
        pa.field("high_price_volume", pa.int64()),
        pa.field("low_price_volume", pa.int64()),
    ]
)

MA_SCHEMA = pa.schema(
    [
        pa.field("item_id", pa.int32()),
        pa.field("snapshot_date", pa.date32()),
        pa.field("MA_avg_high_price", pa.float64(), nullable=True),
        pa.field("MA_avg_low_price", pa.float64(), nullable=True),
        pa.field("MA_high_price_volume", pa.float64(), nullable=True),
        pa.field("MA_low_price_volume", pa.float64(), nullable=True),
        pa.field("high_price_history", pa.list_(pa.float64()), nullable=True),
        pa.field("low_price_history", pa.list_(pa.float64()), nullable=True),
        pa.field("high_volume_history", pa.list_(pa.float64()), nullable=True),
        pa.field("low_volume_history", pa.list_(pa.float64()), nullable=True),
        pa.field("valid_days_high", pa.int32()),
        pa.field("valid_days_low", pa.int32()),
        pa.field("window_start_date", pa.date32(), nullable=True),
        pa.field("window_end_date", pa.date32()),
    ]
)

SNAPSHOT_DATE_RE = re.compile(r"snapshot_date=(\d{4}-\d{2}-\d{2})")
METADATA_FILE = "_source_metadata.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def _parse_snapshot_date_from_dir(path: Path) -> date:
    match = SNAPSHOT_DATE_RE.search(str(path))
    if not match:
        raise ValueError(f"Expected snapshot_date directory in: {path}")
    return date.fromisoformat(match.group(1))


def _snapshot_partitions(src_root: Path) -> list[Path]:
    return sorted([p for p in src_root.iterdir() if p.is_dir() and SNAPSHOT_DATE_RE.search(str(p))])


def _latest_snapshot_file(snapshot_dir: Path) -> Path:
    parquet_files = sorted(snapshot_dir.glob("*.parquet"))
    if not parquet_files:
        raise FileNotFoundError(f"No parquet files found in {snapshot_dir}")
    return parquet_files[-1]


def _normalize_snapshot_df(df: pd.DataFrame, snapshot_date: date) -> pd.DataFrame:
    expected_columns = [
        "item_id",
        "avg_high_price",
        "high_price_volume",
        "avg_low_price",
        "low_price_volume",
        "snapshot_ts",
        "snapshot_date",
    ]
    missing = [col for col in expected_columns if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    if df.empty:
        raise ValueError(f"Snapshot {snapshot_date} contains no rows")

    if df["item_id"].isnull().any():
        raise ValueError("Null item_id values found")

    if df["item_id"].duplicated().any():
        raise ValueError("Duplicate item_id values found")

    if not pd.api.types.is_integer_dtype(df["item_id"]):
        df["item_id"] = df["item_id"].astype("int32")

    if pd.api.types.is_datetime64_any_dtype(df["snapshot_ts"]):
        if df["snapshot_ts"].dt.tz is None:
            df["snapshot_ts"] = df["snapshot_ts"].dt.tz_localize("UTC")
    else:
        df["snapshot_ts"] = pd.to_datetime(df["snapshot_ts"], utc=True)

    if pd.api.types.is_datetime64_any_dtype(df["snapshot_date"]):
        df["snapshot_date"] = df["snapshot_date"].dt.date
    else:
        df["snapshot_date"] = df["snapshot_date"].apply(lambda v: v if isinstance(v, date) else date.fromisoformat(str(v)))

    if not (df["snapshot_date"] == snapshot_date).all():
        raise ValueError("snapshot_date values do not match partition date")

    if df["high_price_volume"].lt(0).any() or df["low_price_volume"].lt(0).any():
        raise ValueError("Negative volume values found")

    for price_col in ["avg_high_price", "avg_low_price"]:
        if df[price_col].dropna().lt(0).any():
            raise ValueError(f"Negative values found in {price_col}")

    df = df.copy()
    df["item_id"] = df["item_id"].astype("int32")
    df["avg_high_price"] = df["avg_high_price"].astype("Int64")
    df["avg_low_price"] = df["avg_low_price"].astype("Int64")
    df["high_price_volume"] = df["high_price_volume"].astype("int64")
    df["low_price_volume"] = df["low_price_volume"].astype("int64")

    return df


def _source_fingerprint(files: list[Path]) -> str:
    entries = [
        {"name": str(p.name), "size": p.stat().st_size, "mtime": p.stat().st_mtime}
        for p in sorted(files, key=lambda p: p.name)
    ]
    text = json.dumps(entries, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_metadata(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def _write_metadata(path: Path, metadata: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metadata, indent=2))


def _write_parquet(df: pd.DataFrame, schema: pa.Schema, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)
    pq.write_table(table, output_path, **PARQUET_WRITE_OPTIONS)
    logger.info("Wrote %s rows to %s", len(df), output_path)


def _empty_dataframe(schema: pa.Schema) -> pd.DataFrame:
    return pd.DataFrame({name: pd.Series([], dtype="Int64" if field.nullable else "int64")
                         if pa.types.is_integer(field.type) else pd.Series([], dtype="float64")
                         for name, field in zip(schema.names, schema)})


def _build_item_history_df(df: pd.DataFrame) -> pd.DataFrame:
    return df[
        [
            "item_id",
            "snapshot_date",
            "snapshot_ts",
            "avg_high_price",
            "avg_low_price",
            "high_price_volume",
            "low_price_volume",
        ]
    ].copy()


def _build_MA_df(
    snapshot_date: date,
    src_root: Path,
    window_days: int = 7,
) -> tuple[pd.DataFrame, list[Path]]:
    frames: list[pd.DataFrame] = []
    source_files: list[Path] = []

    for offset in range(window_days):
        window_date = snapshot_date - timedelta(days=offset)
        partition_dir = src_root / f"snapshot_date={window_date.isoformat()}"
        if not partition_dir.exists():
            continue

        try:
            source_file = _latest_snapshot_file(partition_dir)
            window_df = pd.read_parquet(source_file)
            window_df = _normalize_snapshot_df(window_df, window_date)
            frames.append(
                window_df[[
                    "item_id",
                    "avg_high_price",
                    "avg_low_price",
                    "high_price_volume",
                    "low_price_volume",
                    "snapshot_date",
                ]]
            )
            source_files.append(source_file)
        except FileNotFoundError:
            continue

    if not frames:
        return pd.DataFrame(columns=MA_SCHEMA.names), source_files

    combined = pd.concat(frames, ignore_index=True)
    window_dates = [snapshot_date - timedelta(days=offset) for offset in range(window_days - 1, -1, -1)]
    date_to_position = {dt: pos for pos, dt in enumerate(window_dates)}
    combined["window_position"] = combined["snapshot_date"].map(date_to_position)

    all_item_ids = combined["item_id"].unique()
    all_index = pd.MultiIndex.from_product([all_item_ids, list(range(window_days))], names=["item_id", "window_position"])
    combined = combined.set_index(["item_id", "window_position"]).reindex(all_index)

    def make_window_list(values: pd.Series) -> list:
        return [None if pd.isna(v) else float(v) for v in values.tolist()]

    window_data = combined.groupby(level="item_id").agg(
        MA_avg_high_price=("avg_high_price", "mean"),
        MA_avg_low_price=("avg_low_price", "mean"),
        MA_high_price_volume=("high_price_volume", "mean"),
        MA_low_price_volume=("low_price_volume", "mean"),
        valid_days_high=("avg_high_price", lambda x: int(x.notna().sum())),
        valid_days_low=("avg_low_price", lambda x: int(x.notna().sum())),
    )

    high_history = combined["avg_high_price"].groupby(level="item_id").apply(make_window_list)
    low_history = combined["avg_low_price"].groupby(level="item_id").apply(make_window_list)
    high_volume_history = combined["high_price_volume"].groupby(level="item_id").apply(make_window_list)
    low_volume_history = combined["low_price_volume"].groupby(level="item_id").apply(make_window_list)

    aggregated = window_data.reset_index()
    aggregated["high_price_history"] = aggregated["item_id"].map(high_history)
    aggregated["low_price_history"] = aggregated["item_id"].map(low_history)
    aggregated["high_volume_history"] = aggregated["item_id"].map(high_volume_history)
    aggregated["low_volume_history"] = aggregated["item_id"].map(low_volume_history)
    aggregated["snapshot_date"] = snapshot_date
    aggregated["window_start_date"] = snapshot_date - timedelta(days=window_days - 1)
    aggregated["window_end_date"] = snapshot_date

    return aggregated, source_files


def _prepare_table(df: pd.DataFrame, schema: pa.Schema) -> pd.DataFrame:
    if df.empty:
        empty_df = pd.DataFrame()
        for field in schema:
            if pa.types.is_integer(field.type):
                dtype = "Int64" if field.nullable else "int64"
            elif pa.types.is_floating(field.type):
                dtype = "float64"
            elif pa.types.is_timestamp(field.type):
                dtype = "datetime64[ns, UTC]" if field.type.tz else "datetime64[ns]"
            elif pa.types.is_date(field.type):
                dtype = "datetime64[ns]"
            else:
                dtype = "object"
            empty_df[field.name] = pd.Series(dtype=dtype)
        return empty_df

    missing_columns = [name for name in schema.names if name not in df.columns]
    for name in missing_columns:
        field = schema.field(name)
        if pa.types.is_integer(field.type):
            df[name] = pd.Series([pd.NA] * len(df), dtype="Int64" if field.nullable else "int64")
        elif pa.types.is_floating(field.type):
            df[name] = pd.Series([pd.NA] * len(df), dtype="float64")
        elif pa.types.is_timestamp(field.type):
            df[name] = pd.Series([pd.NaT] * len(df), dtype="datetime64[ns, UTC]" if field.type.tz else "datetime64[ns]")
        elif pa.types.is_date(field.type):
            df[name] = pd.Series([pd.NaT] * len(df), dtype="datetime64[ns]")
        else:
            df[name] = pd.Series([pd.NA] * len(df), dtype="object")
    return df[schema.names]


def _publish_snapshot(
    snapshot_date: date,
    src_root: Path,
    dest_root: Path,
    window_days: int,
    force: bool = False,
) -> None:
    logger.info("Processing snapshot_date=%s", snapshot_date)

    current_dir = src_root / f"snapshot_date={snapshot_date.isoformat()}"
    current_file = _latest_snapshot_file(current_dir)
    current_df = pd.read_parquet(current_file)
    current_df = _normalize_snapshot_df(current_df, snapshot_date)

    item_history_dir = dest_root / "item_history" / f"snapshot_date={snapshot_date.isoformat()}"
    item_history_path = item_history_dir / f"{snapshot_date.isoformat()}.parquet"
    item_history_meta = item_history_dir / METADATA_FILE

    current_files = sorted(current_dir.glob("*.parquet"))
    current_fingerprint = _source_fingerprint(current_files)
    current_metadata = {"snapshot_date": snapshot_date.isoformat(), "source_fingerprint": current_fingerprint}

    if not force:
        existing = _load_metadata(item_history_meta)
        if existing and existing.get("source_fingerprint") == current_fingerprint and item_history_path.exists():
            logger.info("Skipping item_history for %s; no source changes", snapshot_date)
        else:
            item_history_df = _build_item_history_df(current_df)
            item_history_df = _prepare_table(item_history_df, ITEM_HISTORY_SCHEMA)
            _write_parquet(item_history_df, ITEM_HISTORY_SCHEMA, item_history_path)
            _write_metadata(item_history_meta, current_metadata)

    MA_dir = dest_root / "daily_top_changes" / f"snapshot_date={snapshot_date.isoformat()}"
    MA_path = MA_dir / f"{snapshot_date.isoformat()}.parquet"
    MA_meta = MA_dir / METADATA_FILE

    MA_df, MA_source_files = _build_MA_df(snapshot_date, src_root, window_days)
    MA_fingerprint = _source_fingerprint(MA_source_files)
    MA_metadata = {
        "snapshot_date": snapshot_date.isoformat(),
        "source_fingerprint": MA_fingerprint,
        "window_days": window_days,
        "source_partitions": [str(p) for p in sorted(MA_source_files, key=lambda p: str(p))],
    }

    if not force:
        existing_MA = _load_metadata(MA_meta)
        if (
            existing_MA
            and existing_MA.get("source_fingerprint") == MA_fingerprint
            and MA_path.exists()
        ):
            logger.info("Skipping daily_top_changes MA output for %s; no source changes", snapshot_date)
            return

    MA_df = _prepare_table(MA_df, MA_SCHEMA)
    _write_parquet(MA_df, MA_SCHEMA, MA_path)
    _write_metadata(MA_meta, MA_metadata)


def _snapshot_dates_from_args(src_root: Path, snapshot_date: date | None) -> list[date]:
    if snapshot_date:
        partition_dir = src_root / f"snapshot_date={snapshot_date.isoformat()}"
        if not partition_dir.exists():
            raise FileNotFoundError(f"Source snapshot_date partition not found: {partition_dir}")
        return [snapshot_date]
    return [_parse_snapshot_date_from_dir(p) for p in _snapshot_partitions(src_root)]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute GE price analytics: item history and 7-day moving average analytics."
    )
    parser.add_argument(
        "--src-root",
        required=True,
        type=Path,
        help="Root of processed snapshot partitions (e.g. output/ge_price_24h_process)",
    )
    parser.add_argument(
        "--dest",
        required=True,
        type=Path,
        help="Root of analytics output directory",
    )
    parser.add_argument(
        "--snapshot-date",
        default=None,
        help="Optional single snapshot_date to process (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=7,
        help="Number of days to include in the moving average window",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force regeneration of analytics outputs even if metadata indicates no source changes",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    snapshot_date = date.fromisoformat(args.snapshot_date) if args.snapshot_date else None
    snapshot_dates = _snapshot_dates_from_args(args.src_root, snapshot_date)

    for snapshot_date in snapshot_dates:
        _publish_snapshot(
            snapshot_date=snapshot_date,
            src_root=args.src_root,
            dest_root=args.dest,
            window_days=args.lookback_days,
            force=args.force,
        )


if __name__ == "__main__":
    main()