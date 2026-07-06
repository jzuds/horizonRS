# horizonRS

## Overview
Using numeric analysis to gain an edge in *Old School Runescape's* (OSRS) **Grand Exchange**.

## The problem
I need more gp.

## Local Development
```
uv sync

uv run python src/extract/extract_ge_price_data.py \
  --granularity 1h \
  --landing-root ./output/extract \
  --date 2026-03-16 \
  --report-only

uv run python src/extract/stage_ge_price_data.py \
  --granularity 1h \
  --landing-root ./output/extract \
  --output-root ./output/stage \
  --date 2026-03-16

uv run python src/utility/inspect_pq_file.py \
    --file ./output/stage/date=2026-03-16/timestamp=1773655200.parquet

```

## Contributing
- How to add new items or pipelines

## License
- See LICENSE file.
