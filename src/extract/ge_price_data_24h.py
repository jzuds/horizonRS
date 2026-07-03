import argparse
import json
import logging
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

def fetch_24h(session, snapshot_ts: datetime) -> dict:
    unix_ts = int(snapshot_ts.timestamp())
    resp = session.get(f"{BASE_URL}/{WIKI_API_ENDPOINTS['24h_price']}", params={"timestamp": unix_ts}, timeout=30)
    resp.raise_for_status()
    payload = resp.json()

    if "data" not in payload:
        raise ValueError(f"Unexpected response shape: {list(payload.keys())}")

    return payload


def build_enveloped_payload(payload: dict, snapshot_ts: datetime, ingested_at: datetime) -> dict:
    return {
        "timestamp": payload.get("timestamp", -1),
        "snapshot_ts": snapshot_ts.isoformat(),
        "ingested_at": ingested_at.isoformat(),
        "source": "osrs_ge_24h",
        "data": payload.get("data", {}),
    }


def landing_path(landing_root: str, partition_key) -> Path:
    filename = f"daily_price.json"
    return Path(landing_root) / f"date={partition_key}" / filename


def write_landing(payload: dict, landing_root: str, partition_key: str) -> Path:
    path = landing_path(landing_root, partition_key)
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = path.with_suffix(f".tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}")
    with tmp_path.open("w") as f:
        json.dump(payload, f, sort_keys=True)
    tmp_path.replace(path)

    log.info("Landed %d items to %s", len(payload["data"]), path)
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract OSRS GE 24h price snapshot.")
    parser.add_argument("--landing-root", required=True, help="Root path for landing output, e.g. /Volumes/{catalog}/raw/landing/ge_price_24h")
    parser.add_argument(
        "--date",
        default=None,
        help="Price date (YYYY-MM-DD). Defaults to yesterday (UTC).",
    )
    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help="If set, ignores existing snapshot and re-fetches data.",
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

    snapshot_ts = datetime(
        price_date.year, price_date.month, price_date.day,
        tzinfo=timezone.utc,
    )
    partition_key = date_to_str(snapshot_ts)
    path = landing_path(args.landing_root, partition_key)
    
    should_skip = (not args.force_overwrite) and path.exists()
    if should_skip:
        log.info("Skipping existing snapshot %s", path)
        return

    log.info("Fetching 24h prices for %s", price_date)

    session = build_session()

    ingestion_dt = datetime.now(timezone.utc)
    raw_payload = fetch_24h(session, snapshot_ts)
    
    if len(raw_payload.get("data")) == 0:
        log.info("Empty or invalid data for %s — skipping write", price_date)
        return
    
    enveloped_payload = build_enveloped_payload(
        raw_payload,
        snapshot_ts,
        ingestion_dt,
    )

    write_landing(enveloped_payload, args.landing_root, partition_key)


if __name__ == "__main__":
    main()
