import argparse
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
import os, uuid
import sys
from pathlib import Path

try:
    CURRENT_DIR = Path(__file__).resolve().parent
except NameError:
    CURRENT_DIR = Path.cwd()

SRC_DIR = CURRENT_DIR.parent
sys.path.append(str(SRC_DIR))

from utility.wiki_api import BASE_URL, WIKI_API_ENDPOINTS, build_session
from utility.utilities import get_prior_date, date_to_str, str_to_date

log = logging.getLogger(__name__)

BUCKET_SECONDS = {
    "5m": 300,
    "1h": 3600,
    "24h": 86400,
}

GRANULARITY_ENDPOINT_KEY = {
    "5m": "5m_price",
    "1h": "1h_price",
    "24h": "24h_price",
}

ALWAYS_REQUIRE_COMPLETE = {"24h"}

WIKI_TRACKING_START = datetime(2021, 3, 1, tzinfo=timezone.utc)


def bucket_starts_for_day(price_date: date, bucket_seconds: int) -> list[datetime]:
    """All bucket start timestamps (UTC) needed to cover one calendar day.

    One API call returns exactly one bucket for all ~3,700 items, so a full
    day requires a series of calls (288 for /5m, 24 for /1h) rather than a
    single request.
    """
    day_start = datetime(price_date.year, price_date.month, price_date.day, tzinfo=timezone.utc)
    n_buckets = 86400 // bucket_seconds
    return [day_start + timedelta(seconds=i * bucket_seconds) for i in range(n_buckets)]


def fetch_bucket(session, endpoint_key: str, bucket_ts: datetime) -> dict:
    unix_ts = int(bucket_ts.timestamp())
    endpoint = WIKI_API_ENDPOINTS[endpoint_key]
    resp = session.get(f"{BASE_URL}/{endpoint}", params={"timestamp": unix_ts}, timeout=30)
    resp.raise_for_status()
    payload = resp.json()

    if "data" not in payload:
        raise ValueError(f"Unexpected response shape: {list(payload.keys())}")

    reported_ts = payload.get("timestamp")
    if reported_ts is not None and int(reported_ts) != unix_ts:
        log.warning(
            "Bucket timestamp mismatch on %s: requested unix=%d, API reported unix=%s. "
            "Landing under the requested timestamp regardless, since that's our unit of work.",
            endpoint, unix_ts, reported_ts,
        )

    return payload


def build_enveloped_payload(payload: dict, bucket_ts: datetime, ingested_at: datetime, granularity: str) -> dict:
    data = payload.get("data", {})
    return {
        "timestamp": payload.get("timestamp", int(bucket_ts.timestamp())),
        "requested_timestamp": int(bucket_ts.timestamp()),
        "snapshot_ts": bucket_ts.isoformat(),
        "ingested_at": ingested_at.isoformat(),
        "source": f"osrs_ge_{granularity}",
        "row_count": len(data),
        "data": data,
    }


def landing_path(landing_root: str, partition_key: str, bucket_ts: datetime) -> Path:
    filename = f"timestamp={int(bucket_ts.timestamp())}.json"
    return Path(landing_root) / f"date={partition_key}" / filename


def write_landing(payload: dict, landing_root: str, partition_key: str, bucket_ts: datetime) -> Path:
    path = landing_path(landing_root, partition_key, bucket_ts)
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = path.with_suffix(f".tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}")
    with tmp_path.open("w") as f:
        json.dump(payload, f, sort_keys=True)
    tmp_path.replace(path)

    log.info("Landed %d row(s) to %s", payload["row_count"], path)
    return path


def read_row_count(path: Path) -> int | None:
    """Best-effort peek at an existing landing file's row_count, for --report-only.

    Falls back to counting `data` directly for any file landed before
    `row_count` existed. Returns None if the file can't be read/parsed at all.
    """
    try:
        with path.open("r") as f:
            payload = json.load(f)
        if "row_count" in payload:
            return int(payload["row_count"])
        return len(payload.get("data", {}))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract a full day of OSRS GE bucketed price snapshots (5m, 1h, or 24h)."
    )
    parser.add_argument(
        "--granularity",
        required=True,
        choices=sorted(BUCKET_SECONDS.keys()),
        help="Which bucketed endpoint to pull: 5m, 1h, or 24h.",
    )
    parser.add_argument(
        "--landing-root",
        required=True,
        help="Root path for landing output, e.g. /Volumes/{catalog}/raw/landing/ge_price_5m",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Price date (YYYY-MM-DD) to cover. Defaults to yesterday (UTC).",
    )
    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help="If set, re-fetches buckets even if a landing file already exists for them — "
             "including ones already confirmed empty. Rarely needed: use this only if you "
             "suspect a previously-landed bucket is wrong, not for routine backfill (a plain "
             "rerun already only touches genuine gaps).",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Abort the whole run on the first bucket that fails to fetch, instead of "
             "logging it and continuing. Off by default: a failed bucket is surfaced via "
             "the run summary and left for the next rerun, rather than failing the entire day.",
    )
    parser.add_argument(
        "--request-delay-seconds",
        type=float,
        default=0.0,
        help="Optional pause between successive bucket requests, as a courtesy to the "
             "wiki API beyond the retry/backoff already built into the HTTP session.",
    )
    parser.add_argument(
        "--fail-on-incomplete",
        action="store_true",
        help="Raise if any bucket for the day failed to fetch (confirmed-empty buckets do "
             "NOT count against this for 5m/1h, since empty is a valid outcome there). "
             "Always enforced for --granularity 24h regardless of this flag, and for 24h "
             "a confirmed-empty response also counts as a failure, not a valid outcome.",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Don't fetch anything. Classify each bucket for the day using only what's "
             "already landed on disk (plus the future/out-of-range checks) and print a "
             "completeness summary, including the specific missing bucket timestamps. "
             "Use this to decide whether a backfill run is actually needed before running one.",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    args = parse_args()

    if args.date:
        price_date = str_to_date(args.date)
    else:
        price_date = get_prior_date(date.today())

    partition_key = date_to_str(price_date)
    bucket_seconds = BUCKET_SECONDS[args.granularity]
    endpoint_key = GRANULARITY_ENDPOINT_KEY[args.granularity]
    buckets = bucket_starts_for_day(price_date, bucket_seconds)
    now = datetime.now(timezone.utc)

    log.info(
        "%s %d %s bucket(s) for %s",
        "Auditing" if args.report_only else "Extracting",
        len(buckets), args.granularity, price_date,
    )

    landed_with_data, landed_empty, skipped = 0, 0, 0
    failed, not_yet_available, out_of_range = 0, 0, 0
    gap_buckets: list[int] = []

    session = None if args.report_only else build_session()

    for bucket_ts in buckets:
        unix_ts = int(bucket_ts.timestamp())
        path = landing_path(args.landing_root, partition_key, bucket_ts)
        already_landed = path.exists() and not args.force_overwrite

        if already_landed:
            if args.report_only or args.granularity in ALWAYS_REQUIRE_COMPLETE:
                row_count = read_row_count(path)
                if row_count is not None:
                    if row_count == 0:
                        landed_empty += 1
                    else:
                        landed_with_data += 1
                    continue

                log.warning("Landed file unreadable: %s", path)
                if args.report_only:
                    gap_buckets.append(unix_ts)
                    failed += 1
                    continue
            else:
                skipped += 1
                continue

        bucket_end = bucket_ts + timedelta(seconds=bucket_seconds)
        if bucket_end > now:
            not_yet_available += 1
            continue

        if bucket_ts < WIKI_TRACKING_START:
            out_of_range += 1
            continue

        if args.report_only:
            gap_buckets.append(unix_ts)
            failed += 1
            continue

        try:
            ingestion_dt = datetime.now(timezone.utc)
            raw_payload = fetch_bucket(session, endpoint_key, bucket_ts)

            enveloped_payload = build_enveloped_payload(
                raw_payload, bucket_ts, ingestion_dt, args.granularity,
            )
            write_landing(enveloped_payload, args.landing_root, partition_key, bucket_ts)

            if enveloped_payload["row_count"] == 0:
                landed_empty += 1
                log.info(
                    "Bucket %s (unix=%d) landed with zero rows — recorded as confirmed-empty, "
                    "won't be re-fetched on rerun.",
                    args.granularity, unix_ts,
                )
            else:
                landed_with_data += 1

        except Exception:
            failed += 1
            gap_buckets.append(unix_ts)
            log.exception(
                "Failed to extract %s bucket %s (unix=%d)",
                args.granularity, bucket_ts.isoformat(), unix_ts,
            )
            if args.stop_on_error:
                raise

        if args.request_delay_seconds:
            time.sleep(args.request_delay_seconds)

    landed = landed_with_data + landed_empty

    log.info(
        "Done. granularity=%s date=%s landed=%d (data=%d, confirmed_empty=%d) skipped=%d "
        "failed=%d not_yet_available=%d out_of_range=%d expected=%d",
        args.granularity, price_date, landed, landed_with_data, landed_empty, skipped,
        failed, not_yet_available, out_of_range, len(buckets),
    )

    if gap_buckets:
        preview = ", ".join(str(ts) for ts in gap_buckets[:50])
        more = f" (+{len(gap_buckets) - 50} more)" if len(gap_buckets) > 50 else ""
        log.info("Gap bucket timestamps (unix): %s%s", preview, more)

    if args.report_only:
        return

    fail_count = failed + (landed_empty if args.granularity in ALWAYS_REQUIRE_COMPLETE else 0)
    require_complete = args.fail_on_incomplete or args.granularity in ALWAYS_REQUIRE_COMPLETE

    if fail_count and require_complete:
        raise RuntimeError(
            f"{fail_count} of {len(buckets)} {args.granularity} bucket(s) unresolved for "
            f"{price_date} (failed={failed}, confirmed_empty={landed_empty}). "
            f"Failing ingestion."
        )


if __name__ == "__main__":
    main()