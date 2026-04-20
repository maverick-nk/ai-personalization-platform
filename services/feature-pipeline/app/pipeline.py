from __future__ import annotations

import glob
import json
import os
import time
from datetime import datetime, timezone

from pyflink.common import WatermarkStrategy
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common.typeinfo import Types
from pyflink.datastream import KeyedProcessFunction, RuntimeContext, StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import KafkaOffsetsInitializer, KafkaSource
from pyflink.datastream.state import ValueStateDescriptor

from .config import Settings, settings as default_settings
from .features import (
    compute_avg_watch_duration,
    compute_category_affinity_score,
    compute_recency_score,
    compute_session_genre_vector,
    compute_time_of_day_bucket,
    compute_watch_count_10min,
)
from .parquet_sink import ParquetSink
from .redis_sink import RedisSink
from .state import UserFeatureState, WatchRecord


def _parse_watch_event(json_str: str) -> dict | None:
    try:
        msg = json.loads(json_str)
        ts_str = msg["timestamp"].replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts_str)
        msg["event_time_epoch"] = dt.timestamp()
        msg["event_date"] = dt.strftime("%Y-%m-%d")
        return msg
    except Exception:
        return None


class FeatureProcessFunction(KeyedProcessFunction):
    def __init__(self, cfg: Settings, redis_sink: RedisSink, parquet_sink: ParquetSink) -> None:
        super().__init__()
        self._cfg = cfg
        self._redis_sink = redis_sink
        self._parquet_sink = parquet_sink
        self._state = None

    def open(self, runtime_context: RuntimeContext) -> None:
        descriptor = ValueStateDescriptor("user_feature_state", Types.PICKLED_BYTE_ARRAY())
        self._state = runtime_context.get_state(descriptor)

    def process_element(self, value: dict, ctx: KeyedProcessFunction.Context):
        state: UserFeatureState = self._state.value() or UserFeatureState()

        now_epoch: float = value["event_time_epoch"]

        record = WatchRecord(
            content_id=value["content_id"],
            watch_pct=value["watch_pct"],
            event_time_epoch=now_epoch,
            genre=value.get("genre"),
        )

        state.recent_watches.append(record)

        if record.genre:
            state.session_genre_counts[record.genre] = (
                state.session_genre_counts.get(record.genre, 0.0) + record.watch_pct
            )

        cutoff = now_epoch - self._cfg.window_size_seconds
        state.recent_watches = [r for r in state.recent_watches if r.event_time_epoch >= cutoff]

        computed_at = time.time()
        pseudo_user_id = value["pseudo_user_id"]

        output = {
            "pseudo_user_id": pseudo_user_id,
            "watch_count_10min": str(compute_watch_count_10min(state)),
            "category_affinity_score": f"{compute_category_affinity_score(state, now_epoch, self._cfg.category_affinity_lambda):.6f}",
            "avg_watch_duration": f"{compute_avg_watch_duration(state):.6f}",
            "time_of_day_bucket": compute_time_of_day_bucket(now_epoch),
            "recency_score": f"{compute_recency_score(state, now_epoch, self._cfg.recency_lambda):.6f}",
            "session_genre_vector": compute_session_genre_vector(state),
            "last_event_epoch": f"{now_epoch:.3f}",
            "computed_at_epoch": f"{computed_at:.3f}",
            "event_date": value["event_date"],
        }

        self._redis_sink.write(output)
        self._parquet_sink.buffer(output)

        state.last_computed_at_epoch = computed_at
        self._state.update(state)


def _find_kafka_connector_jar() -> str | None:
    try:
        import apache_flink
        flink_root = os.path.dirname(apache_flink.__file__)
        pattern = os.path.join(flink_root, "opt", "flink-sql-connector-kafka-*.jar")
        matches = glob.glob(pattern)
        return matches[0] if matches else None
    except Exception:
        return None


def build_pipeline(
    env: StreamExecutionEnvironment,
    settings: Settings | None = None,
    redis_sink: RedisSink | None = None,
    parquet_sink: ParquetSink | None = None,
) -> None:
    cfg = settings or default_settings

    r_sink = redis_sink or RedisSink(cfg)
    p_sink = parquet_sink or ParquetSink(cfg)

    # Open sinks here since they're used inside the KeyedProcessFunction,
    # not wired as standalone Flink operators.
    r_sink.open(None)
    p_sink.open(None)

    kafka_source = (
        KafkaSource.builder()
        .set_bootstrap_servers(cfg.kafka_bootstrap_servers)
        .set_topics(cfg.kafka_watch_topic)
        .set_group_id(cfg.kafka_consumer_group)
        .set_starting_offsets(KafkaOffsetsInitializer.latest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )

    process_fn = FeatureProcessFunction(cfg, r_sink, p_sink)

    (
        env
        .from_source(kafka_source, WatermarkStrategy.no_watermarks(), "KafkaWatchEvents")
        .map(_parse_watch_event, output_type=Types.PICKLED_BYTE_ARRAY())
        .filter(lambda x: x is not None)
        .key_by(lambda x: x["pseudo_user_id"])
        .process(process_fn)
    )


def main() -> None:
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)

    connector_jar = _find_kafka_connector_jar()
    if connector_jar:
        env.add_jars(f"file://{connector_jar}")

    build_pipeline(env)
    env.execute("feature-pipeline")


if __name__ == "__main__":
    main()
