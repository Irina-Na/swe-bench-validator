# SWE-bench Docker Architecture

This document explains how SWE-bench evaluates data points using Docker,
how images are built and cached, and where a data-point validator plugs in.
It is written for infrastructure and DevOps contexts.

## 1) High-level architecture

SWE-bench runs evaluations inside Docker containers to make tests
reproducible across machines. The evaluation harness (`swebench.harness`)
creates or pulls Docker images in three layers and then executes tests
inside containers built from those images.

```
Base image  ->  Env image  ->  Instance image  ->  Test container
```

The layers are cached to reduce repeat build time:

- Base: shared OS + build tooling for all repositories.
- Env: repository-specific Python/system dependencies.
- Instance: a specific repository at a specific commit plus the patch.

## 2) The 3-layer image system

### 2.1 Base image

Purpose:
- Provide a stable OS layer with common build tooling (git, compilers,
  system packages).
- Shared across many repositories.

Characteristics:
- Built rarely and cached for re-use.
- Controlled by SWE-bench harness defaults.

### 2.2 Environment image

Purpose:
- Install dependencies required by a repository's test suite
  (pip/conda/system packages).

Characteristics:
- One env image per repository configuration.
- Built on top of base.
- Reused across multiple instances of the same repo.

### 2.3 Instance image

Purpose:
- Pin a specific repository state (base commit) and apply a patch.
- Ensure the tests run against that exact code version.

Characteristics:
- Built on top of env.
- One instance image per datapoint.

## 3) Image build and cache lifecycle

The harness controls image creation and cache policy via `--cache_level`:

- `none`: no caching; all images rebuilt for each run (slowest, least disk).
- `base`: only base image cached.
- `env` (default): cache base and env images.
- `instance`: cache all images (fastest, most disk).

As the evaluation runs:

1. If the base image is missing and cache allows, it is built.
2. If the env image is missing, it is built on top of base.
3. For each datapoint, the harness creates the instance image by:
   - cloning the repo,
   - checking out `base_commit`,
   - applying the patch,
   - committing the result into the image layer.

Build logs are typically written under `logs/build_images`,
and evaluation logs under `logs/run_evaluation`.

## 4) Test execution flow

At runtime, the harness does the following for each datapoint:

1. **Prepare inputs**
   - The datapoint JSON provides `repo`, `base_commit`, `patch`,
     `FAIL_TO_PASS`, and `PASS_TO_PASS`.
   - The validator converts the datapoint into a SWE-bench prediction
     (`instance_id`, `model_patch`, `model_name_or_path`).

2. **Build or pull Docker images**
   - Base image: shared tooling layer.
   - Env image: dependencies for the repo.
   - Instance image: repository at the target commit + patch applied.

3. **Apply the patch**
   - The harness applies `model_patch` as a git diff.
   - If patch application fails, the instance is marked as failed.

4. **Run tests inside the container**
   - Test commands are derived from the repo metadata.
   - Tests include all cases in `FAIL_TO_PASS` and `PASS_TO_PASS`.
   - Timeouts are enforced to avoid hung runs.

5. **Parse results**
   - `FAIL_TO_PASS` must pass.
   - `PASS_TO_PASS` must remain passing.
   - Failure on either set marks the datapoint invalid.

6. **Write results**
   - Summary results go to `evaluation_results`.
   - Per-instance logs are emitted for debugging.

## 5) Concrete execution example

Example: validating a single datapoint using the golden patch.

Input:
- `instance_id`: `astropy__astropy-11693`
- `patch`: stored in the datapoint JSON
- `FAIL_TO_PASS`: one test
- `PASS_TO_PASS`: several regression tests

Flow:
1. Harness loads the datapoint and builds the prediction JSONL.
2. Docker builds base + env images (if not cached).
3. Instance image is created by cloning `astropy/astropy`,
   checking out the `base_commit`, and applying `patch`.
4. The container runs tests:
   - `FAIL_TO_PASS` must pass after applying the patch.
   - `PASS_TO_PASS` must also pass (regression safety).
5. Harness returns a resolved status or a detailed error.

## 6) Integration points for the validator

The validator integrates with the SWE-bench Docker system at the
`run_evaluation` entrypoint:

- **Input conversion**: datapoint JSON -> prediction JSONL.
- **Instance selection**: `--instance_ids` limits evaluation to the
  changed datapoints.
- **Timeout control**: validator passes timeout settings for CI safety.
- **Result parsing**: validator interprets resolved/failed status and
  returns actionable errors.

This means the validator does not re-implement Docker logic; it delegates
to the official harness to ensure parity with SWE-bench’s own evaluation.

## 7) Where dependencies are installed

Dependencies are installed during env image construction:

- System dependencies: in the base or env image layer.
- Python dependencies: during env image build (pip/conda).

The instance image then layers repo code + patch on top of this prepared
environment, ensuring that tests run in a consistent, pre-configured
dependency set.

## 8) Operational notes for CI

- Docker must be available on the runner.
- Disk usage can be large; prefer `cache_level=env` or `base` in CI.
- Keep `max_workers` low (often 1) for stable runs.
- Clean up containers/images if disk pressure is high.

## 9) Summary

SWE-bench’s Docker architecture isolates each datapoint in a reproducible
container workflow using a 3-layer image system. The validator’s role is
to feed datapoints into the official harness, which handles image builds,
patch application, test execution, and result reporting.
