# SWE-bench Data Point Validator

This repo validates SWE-bench datapoints using the official evaluation
harness (`swebench.harness.run_evaluation`). It also includes a downloader
for pulling datapoints from the SWE-bench datasets.

## Requirements

- Python 3.10+
- Docker (running)
- UV package manager
- Sufficient disk space (SWE-bench images are large)

## Setup

```bash
uv sync --frozen
```

## Validate datapoints

Validate all JSON files in `data_points/`:

```bash
uv run python -m swe_bench_validator.cli --config validator_config.json
```

Validate specific files:

```bash
uv run python -m swe_bench_validator.cli \
  --data-points data_points/astropy__astropy-11693.json \
  --config validator_config.json
```

## Download datapoints

```bash
scripts/download_swe_bench.sh --instance_id "django__django-10087"
```

## Configuration

Edit `validator_config.json` to control:

- dataset name and split
- evaluation timeout
- max workers

## Notes

- Validation uses Docker and can be resource intensive.
- In CI we typically set `max_workers=1` for stability.
