import argparse
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    CURRENT_DIR = Path(__file__).resolve().parent
except NameError:
    CURRENT_DIR = Path.cwd()

SRC_DIR = CURRENT_DIR.parent
sys.path.append(str(SRC_DIR))

from utility.wiki_api import BASE_URL, WIKI_API_ENDPOINTS, build_session

log = logging.getLogger(__name__)


def fetch_mapping(session) -> dict:
    endpoint = WIKI_API_ENDPOINTS["mapping"]

    resp = session.get(
        f"{BASE_URL}/{endpoint}",
        timeout=30,
    )
    resp.raise_for_status()

    payload = resp.json()

    if not isinstance(payload, list):
        raise ValueError(
            f"Unexpected response type: {type(payload).__name__}"
        )

    return payload


def build_enveloped_payload(
    payload: list,
    ingested_at: datetime,
) -> dict:
    return {
        "ingested_at": ingested_at.isoformat(),
        "source": "osrs_ge_mapping",
        "row_count": len(payload),
        "data": payload,
    }


def landing_path(
    landing_root: str,
    ingestion_dt: datetime,
) -> Path:
    partition = ingestion_dt.strftime("%Y-%m-%d")
    filename = f"ingested_at={ingestion_dt.strftime('%Y%m%dT%H%M%SZ')}.json"

    return (
        Path(landing_root)
        / f"date={partition}"
        / filename
    )


def write_landing(
    payload: dict,
    landing_root: str,
    ingestion_dt: datetime,
) -> Path:
    path = landing_path(
        landing_root,
        ingestion_dt,
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp_path = path.with_suffix(
        f".tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}"
    )

    with tmp_path.open("w") as f:
        json.dump(
            payload,
            f,
            sort_keys=True,
        )

    tmp_path.replace(path)

    log.info(
        "Landed %d row(s) to %s",
        payload["row_count"],
        path,
    )

    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract the OSRS Wiki item mapping endpoint."
    )

    parser.add_argument(
        "--landing-root",
        required=True,
        help="Root landing path.",
    )

    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help="Overwrite today's landing file if it already exists.",
    )

    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    args = parse_args()

    ingestion_dt = datetime.now(timezone.utc)

    path = landing_path(
        args.landing_root,
        ingestion_dt,
    )

    if path.exists() and not args.force_overwrite:
        log.info(
            "Landing file already exists: %s",
            path,
        )
        return

    session = build_session()

    log.info("Extracting mapping endpoint")

    raw_payload = fetch_mapping(session)

    enveloped_payload = build_enveloped_payload(
        raw_payload,
        ingestion_dt,
    )

    write_landing(
        enveloped_payload,
        args.landing_root,
        ingestion_dt,
    )

    log.info(
        "Done. landed=%d",
        enveloped_payload["row_count"],
    )


if __name__ == "__main__":
    main()