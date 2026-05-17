from __future__ import annotations

import re
from typing import Literal

import yaml
from pydantic import BaseModel, field_validator, model_validator


def _parse_duration(value: str) -> int:
    """Convert '5m', '30s', '1h' to integer seconds."""
    m = re.fullmatch(r"(\d+)(s|m|h)", value.strip())
    if not m:
        raise ValueError(f"Invalid duration '{value}': use e.g. '5m', '30s', '1h'")
    n, unit = int(m.group(1)), m.group(2)
    return n * {"s": 1, "m": 60, "h": 3600}[unit]


class RampStage(BaseModel):
    from_users: int = 0
    to_users: int
    duration_s: int
    hold_s: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> RampStage:
        if "hold" in d:
            return cls(from_users=0, to_users=0, duration_s=0, hold_s=_parse_duration(d["hold"]))
        return cls(
            from_users=d.get("from", 0),
            to_users=d["to"],
            duration_s=_parse_duration(d["over"]),
        )

    @property
    def is_hold(self) -> bool:
        return self.hold_s > 0

    @property
    def total_seconds(self) -> int:
        return self.hold_s if self.is_hold else self.duration_s


class UserBehavior(BaseModel):
    watch_probability: float = 0.7
    consent_revoke_probability: float = 0.05
    genre_distribution: dict[str, float] = {"action": 0.33, "drama": 0.34, "comedy": 0.33}
    session_length_mean_s: float = 45.0

    @field_validator("watch_probability", "consent_revoke_probability")
    @classmethod
    def _clamp(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("probability must be in [0, 1]")
        return v

    @model_validator(mode="after")
    def _normalise_genres(self) -> UserBehavior:
        total = sum(self.genre_distribution.values())
        if total > 0:
            self.genre_distribution = {k: v / total for k, v in self.genre_distribution.items()}
        return self


class Assertions(BaseModel):
    latency_p95_ms: float = 50.0
    error_rate_pct: float = 1.0


class Suite(BaseModel):
    name: str
    test_type: Literal["load", "stress", "soak", "spike"] = "load"
    peak_users: int
    spawn_rate: int = 2
    duration: str
    ramp_profile: list[dict]
    user_behavior: UserBehavior = UserBehavior()
    assertions: Assertions = Assertions()

    # Computed after parse
    duration_s: int = 0
    stages: list[RampStage] = []

    @model_validator(mode="after")
    def _compute(self) -> Suite:
        self.duration_s = _parse_duration(self.duration)
        self.stages = [RampStage.from_dict(d) for d in self.ramp_profile]
        return self


def load_suite(path: str) -> Suite:
    with open(path) as f:
        raw = yaml.safe_load(f)
    return Suite.model_validate(raw)
