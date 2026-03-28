# Dataset + Controlled Augmentation Ladder

This folder now supports two workflows:

1. Legacy similar-case generation (`dataset.py` + `foamgpt_data.py`)
2. Controlled augmentation ladder (`controlled_augmentation_ladder.py`) for scalable, validated data expansion

---

## Current setup status

- Foam-Agent in this folder is **v2.0.0**
- Foam-Agent default LLM is set to:
  - `model_provider: bedrock`
  - `model_version: arn:aws:bedrock:us-west-2:567316078106:inference-profile/us.anthropic.claude-opus-4-6-v1`
- Reviewer loop max is set to **10** (`Foam-Agent/src/config.py`)
- Reviewer loop has early termination for unsupported OpenFOAM10 requirements:
  - termination reason: `unsupported_openfoam10_requirement`

---

## Controlled augmentation ladder (recommended)

Script: `controlled_augmentation_ladder.py`

### What it does

For each unique `user_prompt` group:

1. Builds controlled requirement variants by numeric perturbation ladder:
   - velocity: `+0.5`, `+1.0`, `+1.5`
   - viscosity: `-10%`, `+10%`, `+20%`
   - density: `-10%`, `+10%`, `+20%`
2. Runs each variant through Foam-Agent.
3. Accepts a variant only if all checks pass:
   - no fatal log errors
   - has positive time directory (> 0)
   - expected direct files are generated
4. Saves successful data **immediately** (append + flush + fsync), without waiting for full run completion.

### File inclusion policy for exported rows

Only direct files from these folders are exported:

- `0/`
- `system/`
- `constant/`

Excluded:

- any nested subdirectories in those folders
- `constant/polyMesh/**`
- time directories (e.g. `1`, `2`, `0.5`, etc.)

---

## Prerequisites

- OpenFOAM environment loaded
- AWS Bedrock credentials configured (if using Bedrock runtime)
- Python environment with Foam-Agent dependencies

---

## Run one chunk

From this directory:

```bash
python controlled_augmentation_ladder.py \
  --input foamgpt_train.jsonl \
  --split train \
  --openfoam-path "$WM_PROJECT_DIR" \
  --chunk-index 0 \
  --chunk-count 6 \
  --stages velocity,viscosity,density
```

---

## Run 6 batches in parallel

Run these **simultaneously** in 6 terminals/jobs:

```bash
python controlled_augmentation_ladder.py --input foamgpt_train.jsonl --split train --openfoam-path "$WM_PROJECT_DIR" --chunk-index 0 --chunk-count 6
python controlled_augmentation_ladder.py --input foamgpt_train.jsonl --split train --openfoam-path "$WM_PROJECT_DIR" --chunk-index 1 --chunk-count 6
python controlled_augmentation_ladder.py --input foamgpt_train.jsonl --split train --openfoam-path "$WM_PROJECT_DIR" --chunk-index 2 --chunk-count 6
python controlled_augmentation_ladder.py --input foamgpt_train.jsonl --split train --openfoam-path "$WM_PROJECT_DIR" --chunk-index 3 --chunk-count 6
python controlled_augmentation_ladder.py --input foamgpt_train.jsonl --split train --openfoam-path "$WM_PROJECT_DIR" --chunk-index 4 --chunk-count 6
python controlled_augmentation_ladder.py --input foamgpt_train.jsonl --split train --openfoam-path "$WM_PROJECT_DIR" --chunk-index 5 --chunk-count 6
```

You can do the same for test split by changing `--input foamgpt_test.jsonl --split test`.

---

## Outputs

Written under `ladder_outputs/` per chunk:

- `accepted_cases_<split>_chunk<i>.jsonl`
  - one accepted case-variant record per success
- `accepted_rows_<split>_chunk<i>.jsonl`
  - per-file dataset rows (immediate append per generated file)
- `failed_<split>_chunk<i>.jsonl`
  - failed case-variant records with stdout/stderr tails
- `progress_<split>_chunk<i>.jsonl`
  - step-by-step completion tracking

---

## How 6-batch splitting works

- Each unique prompt-group is assigned to exactly one chunk by stable hash bucketing.
- Bucket function: `sha256(key) % chunk_count` where `key` is case/prompt-based.
- With `chunk_count=6`, each case-group goes to one of chunk indices `0..5`.
- This guarantees:
  - no overlap across chunks
  - safe parallel execution
  - deterministic partitioning across reruns

---

## Legacy workflow (kept)

- `dataset.py` generates similar-case references for 202 cases.
- `foamgpt_data.py` builds train/test JSONL from base files.

These are still present but are separate from the controlled ladder pipeline.

## Velocity-only mode (start simple)

To run only velocity perturbations, set:

```bash
--stages velocity
```

Example (one chunk):

```bash
python controlled_augmentation_ladder.py \
  --input foamgpt_train.jsonl \
  --split train \
  --openfoam-path "$WM_PROJECT_DIR" \
  --chunk-index 0 \
  --chunk-count 6 \
  --stages velocity
```

Example (6 parallel chunks, velocity-only):

```bash
python controlled_augmentation_ladder.py --input foamgpt_train.jsonl --split train --openfoam-path "$WM_PROJECT_DIR" --chunk-index 0 --chunk-count 6 --stages velocity
python controlled_augmentation_ladder.py --input foamgpt_train.jsonl --split train --openfoam-path "$WM_PROJECT_DIR" --chunk-index 1 --chunk-count 6 --stages velocity
python controlled_augmentation_ladder.py --input foamgpt_train.jsonl --split train --openfoam-path "$WM_PROJECT_DIR" --chunk-index 2 --chunk-count 6 --stages velocity
python controlled_augmentation_ladder.py --input foamgpt_train.jsonl --split train --openfoam-path "$WM_PROJECT_DIR" --chunk-index 3 --chunk-count 6 --stages velocity
python controlled_augmentation_ladder.py --input foamgpt_train.jsonl --split train --openfoam-path "$WM_PROJECT_DIR" --chunk-index 4 --chunk-count 6 --stages velocity
python controlled_augmentation_ladder.py --input foamgpt_train.jsonl --split train --openfoam-path "$WM_PROJECT_DIR" --chunk-index 5 --chunk-count 6 --stages velocity
```

## Important batching behavior

The augmentation iterates over **unique user_prompt groups** (deduplicated prompt groups), not over every raw dataset row one-by-one.

- Grouping key: identical `user_prompt`
- Each group is processed once for variant generation
- Successful generated files are then expanded into per-file dataset rows and appended immediately
