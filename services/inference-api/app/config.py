from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INFERENCE_", env_nested_delimiter="__")

    # Pseudonymization — must match the secret used by event-ingestion
    pseudonym_secret: str = "dev-secret-change-in-prod"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    # Hard deadline for Redis HGETALL — must be well under the 50ms e2e budget
    redis_timeout_seconds: float = 0.01

    # Privacy service
    privacy_base_url: str = "http://localhost:8001"
    # Must be <<5ms to stay within the inference latency budget (ADR 0007)
    privacy_timeout_seconds: float = 0.003

    # MLflow
    mlflow_tracking_uri: str = "http://localhost:5001"
    mlflow_model_name: str = "personalization-click-model"
    # Alias checked on startup and during hot-swap polling
    mlflow_model_alias: str = "production"
    mlflow_model_alias_fallback: str = "staging"
    # How often the background task checks for a new model version
    model_poll_interval_seconds: int = 30

    # Content catalog — JSON array of {content_id, genre, title}
    # Covers all genres the model was trained on; new genres are ignored at inference time
    content_catalog: list[dict] = Field(default=[
        {"content_id": "c001", "genre": "action",  "title": "Shadow Strike"},
        {"content_id": "c002", "genre": "action",  "title": "Iron Edge"},
        {"content_id": "c003", "genre": "action",  "title": "Blitz Protocol"},
        {"content_id": "c004", "genre": "drama",   "title": "The Long Winter"},
        {"content_id": "c005", "genre": "drama",   "title": "Borrowed Time"},
        {"content_id": "c006", "genre": "drama",   "title": "Still Waters"},
        {"content_id": "c007", "genre": "comedy",  "title": "Wrong Floor"},
        {"content_id": "c008", "genre": "comedy",  "title": "Plus One"},
        {"content_id": "c009", "genre": "comedy",  "title": "Family Chaos"},
        {"content_id": "c010", "genre": "sci-fi",  "title": "Event Horizon 2"},
        {"content_id": "c011", "genre": "sci-fi",  "title": "Deep Signal"},
        {"content_id": "c012", "genre": "sci-fi",  "title": "Nova Station"},
        {"content_id": "c013", "genre": "thriller","title": "Dark Current"},
        {"content_id": "c014", "genre": "thriller","title": "Last Witness"},
        {"content_id": "c015", "genre": "thriller","title": "Cold Room"},
        {"content_id": "c016", "genre": "romance", "title": "Late Arrival"},
        {"content_id": "c017", "genre": "romance", "title": "Second Chance"},
        {"content_id": "c018", "genre": "horror",  "title": "The Empty House"},
        {"content_id": "c019", "genre": "horror",  "title": "Below Zero"},
        {"content_id": "c020", "genre": "documentary", "title": "The Final Reef"},
    ])

    # Trending fallback — content_ids returned when personalization is unavailable
    trending_content_ids: list[str] = Field(default=[
        "c001", "c004", "c007", "c010", "c013", "c016", "c018", "c020",
    ])
