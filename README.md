# horizonRS

## Overview
Using numeric analysis to gain an edge in *Old School Runescape's* (OSRS) **Grand Exchange**.

## The problem
The OSRS Grand Exchange is a living, breathing ecosystem with fast-paced and dynamic trends. As a result, "merchers" have an excellent opportunity to financially capatilize on these evolving market conditions.

## Local Development
```
uv sync
source .venv/bin/activate

python src/extract/ge_price_data_24h.py \
    --landing-root ./output/ge_price_24h

python src/process/process_ge_price_data_24h.py \
    --src-dir ./output/ge_price_24h/ingestion_date=2026-03-17 \
    --dest ./output/ge_price_24h_process

python src/utility/inspect_pq_file.py \
    --file ./output/ge_price_24h_process/snapshot_date=2026-03-16/2026-03-17.parquet
```

## Contributing
- How to add new items or pipelines

## License
- See LICENSE file.
