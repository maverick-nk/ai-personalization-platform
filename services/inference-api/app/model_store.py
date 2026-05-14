from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

import mlflow
from mlflow.tracking import MlflowClient

from .scorers.base import BaseScorer
from .scorers.factory import get_scorer

log = logging.getLogger(__name__)


@dataclass
class LoadedModel:
    scorer: BaseScorer
    schema: dict          # feature_schema.json artifact
    version: str


class ModelStore:
    """Loads a model from MLflow and hot-swaps it in the background.

    Hot-swap contract:
    - The active model is swapped under _lock so scorer.py always sees a consistent
      (scorer, schema, version) triple — never a partially-loaded state.
    - A background asyncio task polls MLflow every poll_interval_seconds and replaces
      the model only when the registered version changes.
    - Startup blocks until a model is loaded; if loading fails the service cannot start.
    """

    def __init__(
        self,
        tracking_uri: str,
        model_name: str,
        alias: str,
        alias_fallback: str,
        poll_interval_seconds: int,
    ) -> None:
        mlflow.set_tracking_uri(tracking_uri)
        self._client = MlflowClient()
        self._model_name = model_name
        self._alias = alias
        self._alias_fallback = alias_fallback
        self._poll_interval = poll_interval_seconds
        self._lock = asyncio.Lock()
        self._current: LoadedModel | None = None
        self._poll_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._current = await asyncio.to_thread(self._load)
        log.info("Model loaded: %s v%s", self._model_name, self._current.version)
        self._poll_task = asyncio.create_task(self._poll_loop(), name="model-hotswap")

    async def stop(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

    async def get(self) -> LoadedModel | None:
        async with self._lock:
            return self._current

    async def _poll_loop(self) -> None:
        while True:
            await asyncio.sleep(self._poll_interval)
            try:
                candidate = await asyncio.to_thread(self._load)
                async with self._lock:
                    if (
                        self._current is None
                        or candidate.version != self._current.version
                    ):
                        self._current = candidate
                        log.info("Hot-swapped model to v%s", candidate.version)
            except Exception:
                log.exception("Model poll failed — keeping current model")

    def _load(self) -> LoadedModel:
        """Download the latest model artifact from MLflow. Runs in a thread pool."""
        mv = self._resolve_version()
        run_id = mv.run_id
        version = mv.version

        # model_type is logged as a run param by the training pipeline — read it here
        # so the scorer factory can pick the right implementation without any
        # hardcoded algorithm assumptions in this file.
        run = self._client.get_run(run_id)
        model_type = run.data.params.get("model_type")
        if model_type is None:
            log.warning("Run %s has no 'model_type' param — defaulting to 'lightgbm'", run_id)
            model_type = "lightgbm"

        with tempfile.TemporaryDirectory() as tmp:
            model_uri = mlflow.artifacts.download_artifacts(
                artifact_uri=f"runs:/{run_id}/model",
                dst_path=tmp,
            )
            scorer = get_scorer(model_type, model_uri)

            schema_path = mlflow.artifacts.download_artifacts(
                artifact_uri=f"runs:/{run_id}/feature_schema.json",
                dst_path=tmp,
            )
            schema = json.loads(Path(schema_path).read_text())

        return LoadedModel(scorer=scorer, schema=schema, version=str(version))

    def _resolve_version(self):
        for alias in (self._alias, self._alias_fallback):
            try:
                return self._client.get_model_version_by_alias(self._model_name, alias)
            except Exception:
                log.warning("Alias '%s' not found for model '%s'", alias, self._model_name)
        raise RuntimeError(
            f"No model version found for '{self._model_name}' "
            f"under aliases '{self._alias}' or '{self._alias_fallback}'"
        )
