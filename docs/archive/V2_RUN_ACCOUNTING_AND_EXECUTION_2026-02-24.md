# V2 Run Accounting and Execution (2026-02-24)

Date: 2026-02-24
Status: Executed
Author: Codex

## 1) Full Accounting Snapshot (pre-correction)

Legacy queue basis (`logs/v2_full_manifests_20260223_222457.txt`):
- Planned manifests: 48
- Planned instances: 2000
- Methods: `oracle`, `gm_progressive`, `bm25`, `agentic_cold_start`

Observed run state in `results/v2_full_runs/patch_runs`:
- Latest manifests seen: 44
- Complete manifests: 38
- Incomplete manifests: 6
- Not started manifests: 4
- Completed instances: 1007 / 1388 seen

Incomplete (latest attempt):
- `django_django_agentic_cold_start_v1.yaml` (144/231)
- `django_django_bm25_v1.yaml` (19/231)
- `sympy_sympy_bm25_v1.yaml` (56/75)
- `matplotlib_matplotlib_gm_progressive_v1.yaml` (23/34)
- `scikit_learn_scikit_learn_gm_progressive_v1.yaml` (12/32)
- `sphinx_doc_sphinx_gm_progressive_v1.yaml` (12/44)

Not started (legacy 4-method campaign):
- `django_django_gm_progressive_v1.yaml`
- `sympy_sympy_gm_progressive_v1.yaml`
- `django_django_oracle_v1.yaml`
- `sympy_sympy_oracle_v1.yaml`

## 2) Corrected V2 Method Matrix

Manifest generator now targets this full 8-method matrix (includes oracle):
1. `oracle`
2. `gm_progressive`
3. `rag_progressive`
4. `gm_deterministic`
5. `raw_rag_function`
6. `raw_rag_fixed`
7. `bm25`
8. `agentic_cold_start`

Generated artifacts:
- `patch_manifests/v2_verified/manifest_ledger_v2.json`
- `logs/v2_full_manifests_8method_20260224_100240.txt`

Corrected campaign totals:
- Planned manifests: 96
- Planned instances: 4000

## 3) Implementation Changes Made

1. `run_patch.py`
- Added retrieval dispatch support for:
  - `raw_rag_function`
  - `raw_rag_fixed`
  - `rag_baseline` (baseline-mode compatibility)

2. `tools/generate_v2_verified_manifests.py`
- Expanded full-run method matrix to 8 methods (above).
- Added `rag_symmetric_tools: true` only for `rag_progressive`.
- Deterministic/raw retrieval methods remain non-symmetric tool mode.

3. Tests added/updated:
- `tests/test_patch_runner.py`
  - Added retrieval dispatch tests for `raw_rag_function` and `rag_baseline`.
- `tests/test_generate_v2_verified_manifests.py`
  - Added matrix and payload-flag tests.

Validation:
- `./.venv/bin/python -m unittest discover -s tests -v`
- Result: `228` tests passed.

## 4) Execution Launch (corrected campaign)

Pool launch:
- Command mode: local, stage1-only, resume enabled
- Repo concurrency: 8
- Issue workers per manifest: 2
- Manifest timeout: disabled (`0`)

Command:
```bash
./.venv/bin/python tools/run_manifest_pool.py \
  --manifest-list logs/v2_full_manifests_8method_20260224_100240.txt \
  --results-dir results/v2_full_runs \
  --max-parallel-repos 8 \
  --manifest-timeout-s 0 \
  --resume-incomplete \
  --execution-mode local \
  --evaluate-mode stage1_only \
  --run-workers 2
```

Runtime artifacts:
- Pool process: active (`tools/run_manifest_pool.py`)
- Pool log: `logs/v2_repo_pool_20260224_100338.log`
- Failure log: `logs/v2_repo_pool_failures_20260224_100338.log`

Dashboard restart:
- Command manifest list switched to corrected 96-manifest list.
- Dashboard process: active on `127.0.0.1:5051`
- Dashboard log: `logs/v2_patch_dashboard_20260224_100353.log`

## 5) Immediate Post-launch Health

From pool log:
- Start line confirms corrected campaign:
  - `manifests_total=96`
  - `pending=58`
  - `skipped=38`
  - `run_workers=2`
- Resume behavior confirmed for previously incomplete manifests.
- New methods (`gm_deterministic`) are actively queued/running.

From dashboard API (`/api/status`):
- `summary_plan.n_manifests_planned = 96`
- `summary_plan.n_instances_planned = 4000`
- Per-method plan now includes all 8 methods.
