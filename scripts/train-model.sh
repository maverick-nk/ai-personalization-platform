#!/usr/bin/env bash
# Trains a LightGBM click-probability model and registers it to MLflow.
#
# If the Parquet store is empty (no real Flink data yet), seeds synthetic data
# automatically so the pipeline can run out of the box.
#
# Usage:
#   ./scripts/train-model.sh [--parquet-path PATH] [--alias ALIAS]
#
# Options:
#   --parquet-path PATH   Override where Parquet data is read from.
#                         Default: /tmp/parquet_sample (synthetic seed data).
#                         Set to your Docker volume path if Flink has written real data.
#   --alias ALIAS         MLflow alias to register the model under.
#                         Default: staging (inference-api polls staging as fallback).
#
# Environment:
#   MLFLOW_URL            MLflow tracking server. Default: http://localhost:5001
#   INFERENCE_URL         Inference API health endpoint. Default: http://localhost:8002
#   MODEL_NAME            MLflow registered model name. Default: personalization-click-model
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TRAINING_DIR="$REPO_ROOT/services/model-training"

MLFLOW_URL="${MLFLOW_URL:-http://localhost:5001}"
INFERENCE_URL="${INFERENCE_URL:-http://localhost:8002}"
# Must match MODEL_TRAINING_MLFLOW_MODEL_NAME / INFERENCE_MLFLOW_MODEL_NAME in docker-compose
MODEL_NAME="${MODEL_NAME:-personalization-click-model}"
PARQUET_PATH="/tmp/parquet_sample"
MODEL_ALIAS="staging"

# ── Argument parsing ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --parquet-path) PARQUET_PATH="$2"; shift 2 ;;
    --alias)        MODEL_ALIAS="$2";  shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ── MLflow reachability check ──────────────────────────────────────────────────
echo "→ Checking MLflow at ${MLFLOW_URL}..."
if ! curl -sf "${MLFLOW_URL}/health" >/dev/null 2>&1; then
  echo "✗ MLflow is not reachable at ${MLFLOW_URL}."
  echo "  Run ./scripts/start-infra.sh first, or set MLFLOW_URL."
  exit 1
fi
echo "  ✓ MLflow healthy"

# ── Parquet data check / seed ──────────────────────────────────────────────────
# Check for at least one .parquet file under the given path.
if find "$PARQUET_PATH" -name "*.parquet" -quit 2>/dev/null | grep -q .; then
  echo "→ Using existing Parquet data at ${PARQUET_PATH}"
else
  echo "→ No Parquet data found at ${PARQUET_PATH} — seeding synthetic data..."
  (cd "$TRAINING_DIR" && uv run python scripts/seed_parquet.py)
  echo "  ✓ Synthetic data written to ${PARQUET_PATH}"
fi

# ── Train ──────────────────────────────────────────────────────────────────────
echo "→ Running model training pipeline (alias: ${MODEL_ALIAS})..."
(
  cd "$TRAINING_DIR"
  MODEL_TRAINING_PARQUET_BASE_PATH="$PARQUET_PATH" \
  MODEL_TRAINING_MLFLOW_TRACKING_URI="$MLFLOW_URL" \
  MODEL_TRAINING_MODEL_ALIAS="$MODEL_ALIAS" \
  uv run python -m app
)

# ── Resolve the version that was just registered ──────────────────────────────
# Use the model-training venv's mlflow (guaranteed installed) to look up which
# version now sits under the alias — avoids parsing training log output.
NEW_VERSION=$(
  cd "$TRAINING_DIR" && uv run python3 - <<PYEOF 2>/dev/null || true
import mlflow
mlflow.set_tracking_uri("${MLFLOW_URL}")
try:
    mv = mlflow.tracking.MlflowClient().get_model_version_by_alias("${MODEL_NAME}", "${MODEL_ALIAS}")
    print(mv.version, end="")
except Exception:
    pass
PYEOF
)

# ── Wait for inference-api to serve the new version ───────────────────────────
# The inference-api polls MLflow every 30s. We give it 60s.
if curl -sf "${INFERENCE_URL}/health" >/dev/null 2>&1; then
  if [[ -n "$NEW_VERSION" ]]; then
    echo "→ Waiting for inference-api to load model v${NEW_VERSION} (poll interval: 30s)..."
  else
    echo "→ Waiting for inference-api to load the model (poll interval: 30s)..."
  fi
  TIMEOUT=60
  INTERVAL=5
  elapsed=0
  while true; do
    current=$(curl -sf "${INFERENCE_URL}/health" 2>/dev/null \
      | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('model_version') or '')" 2>/dev/null || true)
    # If we know the target version, wait for it specifically.
    # Otherwise (MLflow query failed) accept any non-null version.
    if [[ -n "$NEW_VERSION" && "$current" == "$NEW_VERSION" ]]; then
      echo "  ✓ inference-api serving model version ${current}"
      break
    elif [[ -z "$NEW_VERSION" && -n "$current" ]]; then
      echo "  ✓ inference-api serving model version ${current}"
      break
    fi
    if (( elapsed >= TIMEOUT )); then
      echo "  ⚠ inference-api has not loaded model v${NEW_VERSION:-<new>} after ${TIMEOUT}s."
      echo "    It will retry on its next poll cycle (every 30s)."
      echo "    Check: curl ${INFERENCE_URL}/health"
      break
    fi
    printf "."
    sleep "$INTERVAL"
    elapsed=$(( elapsed + INTERVAL ))
  done
  echo ""
else
  echo "  (inference-api not reachable — skipping load check)"
fi

echo ""
echo "✓ Done. Model registered to MLflow under alias '${MODEL_ALIAS}'."
echo "  MLflow UI: ${MLFLOW_URL}"
echo "  Inference: ${INFERENCE_URL}/health"
