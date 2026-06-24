# horizonRS

## Overview
Using numeric analysis to gain an edge in *Old School Runescape's* (OSRS) **Grand Exchange**.

## The problem
I need more gp.

## Local Development
```
uv sync
source .venv/bin/activate

python src/extract/ge_price_data_24h.py \
    --landing-root ./output/ge_price_24h

python src/utility/inspect_pq_file.py \
    --file ./output/ge_price_24h_process/snapshot_date=2026-03-16/2026-03-17.parquet
```

## Contributing
- How to add new items or pipelines

## License
- See LICENSE file.
