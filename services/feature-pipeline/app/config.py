from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    kafka_bootstrap_servers: str = "localhost:29092"
    kafka_watch_topic: str = "user.watch.events"
    kafka_consumer_group: str = "feature-pipeline"

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_feature_ttl_seconds: int = 3600

    # Override to /data/parquet when containerised (maps to the shared parquet_store volume)
    parquet_base_path: str = "data/parquet"
    parquet_flush_interval_seconds: int = 60
    parquet_flush_batch_size: int = 500

    window_size_seconds: int = 600
    recency_lambda: float = 0.001
    category_affinity_lambda: float = 0.0005

    model_config = {"env_file": ".env"}


settings = Settings()
