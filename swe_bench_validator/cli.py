"""Command-line interface for SWE-bench data point validation."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

import click
from rich.console import Console

from .validator import ValidationError, load_config, validate_data_points

console = Console()


@click.command()
@click.option(
    "--data-points",
    "data_points",
    multiple=True,
    help="Specific data point JSON file(s) to validate.",
)
@click.option(
    "--data-dir",
    default="data_points",
    help="Directory containing data points (default: data_points).",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to validator config JSON.",
)
def main(data_points: List[str], data_dir: str, config_path: Optional[Path]) -> None:
    """Validate SWE-bench data points using the official evaluation harness."""
    try:
        config = load_config(config_path)
        paths: List[Path] = []
        if data_points:
            paths = [Path(path) for path in data_points]
        else:
            paths = sorted(Path(data_dir).glob("*.json"))
        if not paths:
            raise ValidationError("No data point files provided or found.")

        result = validate_data_points(paths, config)
        console.print("[bold green]Validation succeeded.[/bold green]")
        console.print(f"[dim]{result['detail']}[/dim]")
    except ValidationError as exc:
        console.print(f"[bold red]Validation failed: {exc}[/bold red]")
        sys.exit(1)
    except Exception as exc:
        console.print(f"[bold red]Unexpected error: {exc}[/bold red]")
        console.print_exception()
        sys.exit(2)


if __name__ == "__main__":
    main()
