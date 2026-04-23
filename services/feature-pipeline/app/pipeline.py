from __future__ import annotations

import glob
import json
import logging
import os
import time
from datetime import datetime

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

log = logging.getLogger(__name__)

_REQUIRED_EVENT_FIELDS = {"pseudo_user_id", "content_id", "watch_pct", "timestamp"}

# Typed state descriptors — replacing PICKLED_BYTE_ARRAY so Flink's web UI,
# State Processor API, and savepoint migration tooling can inspect state values.
# Field order here must match the positional Row construction in state.py to_row().
_WATCH_RECORD_TYPE = Types.ROW_NAMED(
    ["content_id", "watch_pct", "event_time_epoch", "genre"],
    [Types.STRING(), Types.DOUBLE(), Types.DOUBLE(), Types.STRING()],
)
_USER_FEATURE_STATE_TYPE = Types.ROW_NAMED(
    ["recent_watches", "session_genre_counts", "last_computed_at_epoch"],
    [
        Types.LIST(_WATCH_RECORD_TYPE),
        Types.MAP(Types.STRING(), Types.DOUBLE()),
        Types.DOUBLE(),
    ],
)


def _parse_watch_event(json_str: str) -> dict | None:
    try:
        msg = json.loads(json_str)
    except json.JSONDecodeError:
        log.warning("Dropping non-JSON Kafka message: %.200s", json_str)
        return None

    missing = _REQUIRED_EVENT_FIELDS - msg.keys()
    if missing:
        log.warning("Dropping event missing required fields %s", missing)
        return None

    watch_pct = msg["watch_pct"]
    if not isinstance(watch_pct, (int, float)) or not (0.0 <= watch_pct <= 100.0):
        log.warning("Dropping event with out-of-range watch_pct=%r", watch_pct)
        return None

    try:
        # Normalise the timestamp to a unix float immediately so all downstream
        # code works with a single numeric type rather than ISO strings.
        ts_str = msg["timestamp"].replace("Z", "+00:00")
        dt = datetime.fromisoformat(ts_str)
        msg["event_time_epoch"] = dt.timestamp()
        # event_date is derived here once and reused by both the Parquet partition
        # path and the schema column — avoids recomputing it per feature write.
        msg["event_date"] = dt.strftime("%Y-%m-%d")
        return msg
    except (ValueError, AttributeError):
        log.warning("Dropping event with unparseable timestamp: %r", msg.get("timestamp"))
        return None


class FeatureProcessFunction(KeyedProcessFunction):
    # Sinks are NOT passed to __init__ — they hold un-picklable objects (threading.Lock,
    # Redis socket). Flink serializes the function via cloudpickle before shipping it to
    # the worker; only the Settings config (pure pydantic model) survives the round-trip.
    # Sinks are created and opened in open(), which runs on the worker after deserialization.
    def __init__(self, cfg: Settings) -> None:
        super().__init__()
        self._cfg = cfg
        self._redis_sink: RedisSink | None = None
        self._parquet_sink: ParquetSink | None = None
        self._state = None

    def open(self, runtime_context: RuntimeContext) -> None:
        descriptor = ValueStateDescriptor("user_feature_state", _USER_FEATURE_STATE_TYPE)
        self._state = runtime_context.get_state(descriptor)
        self._redis_sink = RedisSink(self._cfg)
        self._redis_sink.open(runtime_context)
        self._parquet_sink = ParquetSink(self._cfg)
        self._parquet_sink.open(runtime_context)

    def close(self) -> None:
        if self._redis_sink:
            self._redis_sink.close()
        if self._parquet_sink:
            self._parquet_sink.close()

    def process_element(self, value: dict, ctx: KeyedProcessFunction.Context):
        raw = self._state.value()
        state: UserFeatureState = UserFeatureState.from_row(raw) if raw is not None else UserFeatureState()

        now_epoch: float = value["event_time_epoch"]

        record = WatchRecord(
            content_id=value["content_id"],
            watch_pct=value["watch_pct"],
            event_time_epoch=now_epoch,
            genre=value.get("genre"),
        )

        state.recent_watches.append(record)

        # Evict before computing — this is what enforces the 10-minute event-time
        # window. We use the incoming event's timestamp as "now" rather than wall
        # clock so out-of-order events don't corrupt the window boundary.
        cutoff = now_epoch - self._cfg.window_size_seconds
        state.recent_watches = [r for r in state.recent_watches if r.event_time_epoch >= cutoff]

        # Rebuild session_genre_counts from the surviving window rather than
        # incrementally updating it. This keeps session_genre_vector consistent
        # with the same 10-minute window as all other features — an incremental
        # approach would let evicted records' genre contributions linger indefinitely.
        state.session_genre_counts = {}
        for r in state.recent_watches:
            if r.genre:
                # Divide by 100 to normalise watch_pct into [0, 1] before accumulating.
                # This keeps genre weights proportional to fractional completion rather
                # than raw percentage points, making the scale consistent with other
                # decay-based features that also operate in [0, 1].
                state.session_genre_counts[r.genre] = (
                    state.session_genre_counts.get(r.genre, 0.0) + r.watch_pct / 100
                )

        computed_at = time.time()
        pseudo_user_id = value["pseudo_user_id"]

        # Single typed record — RedisSink converts values to strings internally
        # (Redis protocol requirement); ParquetSink uses the types as-is against PARQUET_SCHEMA.
        output = {
            "pseudo_user_id":           pseudo_user_id,
            "watch_count_10min":        compute_watch_count_10min(state),
            "category_affinity_score":  compute_category_affinity_score(state, now_epoch, self._cfg.category_affinity_lambda),
            "avg_watch_duration":       compute_avg_watch_duration(state),
            "time_of_day_bucket":       compute_time_of_day_bucket(now_epoch, value.get("timezone")),
            "recency_score":            compute_recency_score(state, now_epoch, self._cfg.recency_lambda),
            "session_genre_vector":     compute_session_genre_vector(state),
            "last_event_epoch":         now_epoch,
            # computed_at_epoch uses wall clock (not event time) so the inference API
            # and observability stack can measure real feature freshness latency.
            "computed_at_epoch":        computed_at,
            "event_date":               value["event_date"],
        }

        self._redis_sink.write(output)
        self._parquet_sink.buffer(output)

        state.last_computed_at_epoch = computed_at
        self._state.update(state.to_row())


def _find_kafka_connector_jar() -> str | None:
    # Search order:
    # 1. connectors/ directory next to the service root (downloaded by make download-connectors)
    # 2. FLINK_HOME env var opt/ (points to root venv pyflink, set by Makefile)
    # 3. pyflink package opt/ (fallback for standalone Flink installs)
    service_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(service_root, "connectors", "flink-sql-connector-kafka-*.jar"),
    ]
    flink_home = os.environ.get("FLINK_HOME")
    if flink_home:
        candidates.append(os.path.join(flink_home, "opt", "flink-sql-connector-kafka-*.jar"))
    try:
        import pyflink
        candidates.append(os.path.join(os.path.dirname(pyflink.__file__), "opt", "flink-sql-connector-kafka-*.jar"))
    except ImportError:
        pass
    for pattern in candidates:
        matches = glob.glob(pattern)
        if matches:
            return matches[0]
    return None


def build_pipeline(
    env: StreamExecutionEnvironment,
    settings: Settings | None = None,
) -> None:
    cfg = settings or default_settings

    kafka_source = (
        KafkaSource.builder()
        .set_bootstrap_servers(cfg.kafka_bootstrap_servers)
        .set_topics(cfg.kafka_watch_topic)
        .set_group_id(cfg.kafka_consumer_group)
        # latest: the pipeline processes new events only and does not replay history
        # on startup. Change to earliest() if historical backfill is ever needed.
        .set_starting_offsets(KafkaOffsetsInitializer.latest())
        .set_value_only_deserializer(SimpleStringSchema())
        .build()
    )

    process_fn = FeatureProcessFunction(cfg)

    (
        env
        .from_source(kafka_source, WatermarkStrategy.no_watermarks(), "KafkaWatchEvents")
        .map(_parse_watch_event, output_type=Types.PICKLED_BYTE_ARRAY())
        .filter(lambda x: x is not None)
        .key_by(lambda x: x["pseudo_user_id"])
        # no_watermarks: event-time windowing is enforced manually inside
        # process_element using the event's own timestamp, avoiding the latency
        # introduced by Flink's watermark waiting mechanism.
        .process(process_fn)
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    env = StreamExecutionEnvironment.get_execution_environment()
    # Parallelism 1 runs the pipeline in a single thread without a Flink cluster.
    # Sufficient for local dev and the test harness; increase for production.
    env.set_parallelism(1)
    # Checkpointing commits Kafka consumer offsets alongside Flink state. On restart,
    # the pipeline resumes from the last checkpoint rather than latest, preventing
    # event loss during planned restarts or crashes.
    env.enable_checkpointing(60_000)

    connector_jar = _find_kafka_connector_jar()
    if connector_jar:
        env.add_jars(f"file://{connector_jar}")
    else:
        log.warning(
            "Kafka connector JAR not found — run 'make download-connectors' before starting. "
            "Pipeline will fail when KafkaSource is initialised."
        )

    build_pipeline(env)
    env.execute("feature-pipeline")


if __name__ == "__main__":
    main()
