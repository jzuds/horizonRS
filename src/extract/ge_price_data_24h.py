import argparse
import json
import logging
from datetime import date, datetime, timedelta, timezone

import sys
from pathlib import Path

try:
    CURRENT_DIR = Path(__file__).resolve().parent
except NameError:
    CURRENT_DIR = Path.cwd()

SRC_DIR = CURRENT_DIR.parent
sys.path.append(str(SRC_DIR))

from utility.wiki_api import BASE_URL, WIKI_API_ENDPOINTS, build_session

log = logging.getLogger(__name__)

def fetch_24h(session, snapshot_ts: datetime) -> dict:
    unix_ts = int(snapshot_ts.timestamp())
    resp = session.get(f"{BASE_URL}/{WIKI_API_ENDPOINTS['24h_price']}", params={"timestamp": unix_ts}, timeout=30)
    resp.raise_for_status()
    payload = resp.json()

    if "data" not in payload:
        raise ValueError(f"Unexpected response shape: {list(payload.keys())}")

    return payload


def landing_path(landing_root: str, ingestion_date: date, snapshot_ts: datetime) -> Path:
    ts_str = snapshot_ts.strftime("%Y-%m-%dT%H%M%SZ")
    return Path(landing_root) / f"ingestion_date={ingestion_date.isoformat()}" / f"snapshot_ts={ts_str}.json"


def write_landing(payload: dict, landing_root: str, ingestion_date: date, snapshot_ts: datetime) -> Path:
    path = landing_path(landing_root, ingestion_date, snapshot_ts)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w") as f:
        json.dump(payload, f)

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
    return parser.parse_args()


def resolve_date(date_str: str | None) -> date:
    if date_str:
        return date.fromisoformat(date_str)
    return datetime.now(timezone.utc).date() - timedelta(days=1)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    args = parse_args()
    price_date = resolve_date(args.date)

    snapshot_ts = datetime(
        price_date.year, price_date.month, price_date.day,
        tzinfo=timezone.utc,
    )

    log.info("Fetching 24h prices for %s", price_date)

    session = build_session()
    payload = fetch_24h(session, snapshot_ts)

    ingestion_date = datetime.now(timezone.utc).date()
    write_landing(payload, args.landing_root, ingestion_date, snapshot_ts)


if __name__ == "__main__":
    main()
