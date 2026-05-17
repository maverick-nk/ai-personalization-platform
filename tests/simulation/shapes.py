from __future__ import annotations

import json
import os
import time

from locust import LoadTestShape

from tests.simulation.config import RampStage, Suite


class DynamicLoadShape(LoadTestShape):
    """Drives user count from SUITE_CONFIG env var (JSON-serialised Suite).

    tick() is called every 1s by Locust. Returns (user_count, spawn_rate) or
    None to stop the test when all stages have elapsed.
    """

    _suite: Suite | None = None
    _start_time: float | None = None
    _stage_index: int = 0
    _stage_start: float | None = None

    def _load_suite(self) -> Suite:
        raw = os.environ.get("SUITE_CONFIG")
        if not raw:
            raise RuntimeError("SUITE_CONFIG env var not set — use runner.py to start the test")
        return Suite.model_validate(json.loads(raw))

    def tick(self) -> tuple[int, int] | None:
        if self._suite is None:
            self._suite = self._load_suite()
            self._start_time = time.monotonic()
            self._stage_index = 0
            self._stage_start = self._start_time

        now = time.monotonic()
        elapsed_total = now - self._start_time  # type: ignore[operator]

        if elapsed_total >= self._suite.duration_s:
            return None

        stages = self._suite.stages
        if self._stage_index >= len(stages):
            return None

        stage: RampStage = stages[self._stage_index]
        elapsed_in_stage = now - self._stage_start  # type: ignore[operator]

        if elapsed_in_stage >= stage.total_seconds:
            self._stage_index += 1
            self._stage_start = now
            if self._stage_index >= len(stages):
                return None
            stage = stages[self._stage_index]
            elapsed_in_stage = 0.0

        if stage.is_hold:
            # Hold at the user count set by the previous ramp stage.
            current_users = self._suite.peak_users if self._stage_index == 0 else stages[self._stage_index - 1].to_users
            return (current_users, self._suite.spawn_rate)

        # Linear interpolation within this ramp stage.
        frac = min(elapsed_in_stage / stage.duration_s, 1.0) if stage.duration_s > 0 else 1.0
        user_count = int(stage.from_users + (stage.to_users - stage.from_users) * frac)
        return (user_count, self._suite.spawn_rate)
