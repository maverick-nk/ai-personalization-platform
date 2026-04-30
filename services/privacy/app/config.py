from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # asyncpg DSN for the privacy logical database on the shared Postgres instance.
    # Internal Docker hostname (postgres:5432) when containerised; localhost when on host.
    database_url: str = "postgresql+asyncpg://platform:platform@localhost:5432/privacy"

    # HMAC secret used to pseudonymize raw user IDs on public endpoints.
    # Must match the secret used by event-ingestion — same user_id must produce the same
    # pseudo_user_id so consent records align with feature keys in Redis.
    pseudonymize_secret: str

    # Audit log monthly partitions older than this are dropped at startup.
    # Set to 3 for this learning project. Production systems should extend this
    # (12 months for CCPA, duration of consent for GDPR) and archive to cold
    # storage rather than drop.
    audit_retention_months: int = 3

    model_config = {"env_file": ".env"}


settings = Settings()
