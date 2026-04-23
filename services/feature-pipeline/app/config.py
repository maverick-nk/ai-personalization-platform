from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 29092 is the host-exposed EXTERNAL listener; use kafka:9092 inside Docker.
    kafka_bootstrap_servers: str = "localhost:29092"
    kafka_watch_topic: str = "user.watch.events"
    # Unique consumer group keeps this pipeline's offsets independent of any
    # other consumer (e.g. a separate audit consumer on the same topics).
    kafka_consumer_group: str = "feature-pipeline"

    redis_host: str = "localhost"
    redis_port: int = 6379
    # 1 hour TTL balances freshness with cold-start recovery: if the pipeline
    # goes down, inference can still serve stale-but-valid features for an hour
    # before falling back to the trending feed.
    redis_feature_ttl_seconds: int = 3600

    # Override to /data/parquet when containerised (maps to the shared parquet_store volume)
    parquet_base_path: str = "data/parquet"
    # Flush on whichever threshold is hit first — batch_size for high-traffic users,
    # interval for low-traffic periods so files are never delayed indefinitely.
    parquet_flush_interval_seconds: int = 60
    parquet_flush_batch_size: int = 500

    # Event-time window for watch_count_10min; must match the feature name contract
    # registered in MLflow — changing this without retraining breaks serving consistency.
    window_size_seconds: int = 600
    # Decay constants control how quickly past behaviour loses influence.
    # Smaller λ = longer memory. recency_lambda is faster-decaying than
    # category_affinity_lambda because overall engagement fades quicker than genre taste.
    recency_lambda: float = 0.001
    category_affinity_lambda: float = 0.0005

    model_config = {"env_file": ".env"}


settings = Settings()
