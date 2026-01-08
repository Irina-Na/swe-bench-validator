"""Core validation logic for SWE-bench data points."""

from __future__ import annotations

from dataclasses import dataclass
import inspect
import json
from pathlib import Path
import tempfile
from typing import Any, Dict, Iterable, List, Optional, Tuple


class ValidationError(Exception):
    """Validation error for SWE-bench data points."""


@dataclass
class ValidatorConfig:
    dataset_name: str = "swe-bench"
    split: str = "test"
    timeout_seconds: int = 1800
    max_workers: int = 1


REQUIRED_FIELDS = {
    "repo",
    "instance_id",
    "base_commit",
    "patch",
    "FAIL_TO_PASS",
    "PASS_TO_PASS",
}


def load_config(path: Optional[Path]) -> ValidatorConfig:
    if path is None:
        return ValidatorConfig()
    if not path.exists():
        raise ValidationError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return ValidatorConfig(
        dataset_name=raw.get("dataset_name", "swe-bench"),
        split=raw.get("split", "test"),
        timeout_seconds=int(raw.get("timeout_seconds", 1800)),
        max_workers=int(raw.get("max_workers", 1)),
    )


def _parse_test_list(value: Any, field_name: str) -> List[str]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValidationError(
                f"{field_name} is a string but not valid JSON: {exc}"
            ) from exc
        if not isinstance(parsed, list):
            raise ValidationError(f"{field_name} JSON must be a list")
        return parsed
    raise ValidationError(f"{field_name} must be a list or JSON string list")


def load_datapoint(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise ValidationError(f"Data point file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Malformed JSON in {path}: {exc}") from exc

    missing = REQUIRED_FIELDS - set(data.keys())
    if missing:
        raise ValidationError(f"Missing required fields in {path}: {sorted(missing)}")

    data["FAIL_TO_PASS"] = _parse_test_list(data["FAIL_TO_PASS"], "FAIL_TO_PASS")
    data["PASS_TO_PASS"] = _parse_test_list(data["PASS_TO_PASS"], "PASS_TO_PASS")
    return data


def build_prediction(data_point: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "instance_id": data_point["instance_id"],
        "model_patch": data_point["patch"],
        "model_name_or_path": "golden",
    }


def _resolve_run_evaluation():
    try:
        from swebench.harness.run_evaluation import run_evaluation
    except ImportError:
        from swebench.harness import run_evaluation
    return run_evaluation


def _prepare_predictions_file(predictions: List[Dict[str, Any]]) -> Path:
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl", mode="w", encoding="utf-8")
    try:
        for item in predictions:
            temp.write(json.dumps(item))
            temp.write("\n")
    finally:
        temp.close()
    return Path(temp.name)


def _call_run_evaluation(
    run_evaluation,
    predictions: List[Dict[str, Any]],
    instance_ids: List[str],
    config: ValidatorConfig,
) -> Any:
    sig = inspect.signature(run_evaluation)
    params = sig.parameters
    kwargs: Dict[str, Any] = {}

    predictions_path: Optional[Path] = None
    if "predictions" in params:
        kwargs["predictions"] = predictions
    elif "predictions_path" in params:
        predictions_path = _prepare_predictions_file(predictions)
        kwargs["predictions_path"] = str(predictions_path)

    if "instance_ids" in params:
        kwargs["instance_ids"] = instance_ids
    if "dataset_name" in params:
        kwargs["dataset_name"] = config.dataset_name
    if "split" in params:
        kwargs["split"] = config.split
    if "timeout" in params:
        kwargs["timeout"] = config.timeout_seconds
    if "max_workers" in params:
        kwargs["max_workers"] = config.max_workers
    if "num_processes" in params:
        kwargs["num_processes"] = config.max_workers

    try:
        return run_evaluation(**kwargs)
    finally:
        if predictions_path is not None and predictions_path.exists():
            try:
                predictions_path.unlink()
            except OSError:
                pass


def _normalize_result(result: Any) -> Tuple[bool, str]:
    if isinstance(result, dict):
        if "success" in result:
            return bool(result["success"]), "success flag returned"
        if "resolved" in result and isinstance(result["resolved"], (int, float)):
            total = result.get("total", 1)
            return result["resolved"] == total, "resolved/total summary returned"
        if "per_instance" in result and isinstance(result["per_instance"], dict):
            statuses = result["per_instance"].values()
            all_ok = all(status.get("resolved", False) for status in statuses)
            return all_ok, "per_instance resolved summary returned"
    return True, "run_evaluation completed without structured result"


def validate_data_points(
    paths: Iterable[Path],
    config: ValidatorConfig,
) -> Dict[str, Any]:
    data_points = [load_datapoint(path) for path in paths]
    predictions = [build_prediction(dp) for dp in data_points]
    instance_ids = [dp["instance_id"] for dp in data_points]

    run_evaluation = _resolve_run_evaluation()
    result = _call_run_evaluation(run_evaluation, predictions, instance_ids, config)
    ok, detail = _normalize_result(result)
    if not ok:
        raise ValidationError(f"Validation failed: {detail}")
    return {"result": result, "detail": detail}
