from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Kafka broker address.
    # 29092 is the EXTERNAL listener exposed to the host; 9092 is Docker-internal only.
    kafka_bootstrap_servers: str = "localhost:29092"

    # HMAC secret used to pseudonymize user IDs before any data leaves this service.
    # Must be kept consistent across deployments — changing it makes historical
    # pseudo_user_ids incomparable to new ones, breaking feature lookup in Redis.
    pseudonymize_secret: str

    # Reads values from a .env file if present, then falls back to environment variables.
    model_config = {"env_file": ".env"}


# Module-level singleton so settings are loaded once at startup, not per request.
settings = Settings()
