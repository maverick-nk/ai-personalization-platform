from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import settings
from .models import AcceptedResponse, SessionEvent, WatchEvent
from .producer import KafkaProducer
from .pseudonymize import pseudonymize

# Topic names match the contracts expected by the Flink feature pipeline.
# Changing these requires a coordinated update in feature-pipeline/CONTEXT.md.
TOPIC_WATCH = "user.watch.events"
TOPIC_SESSION = "user.session.events"

_DESCRIPTION = """
Ingestion boundary for raw user interaction events. Accepts watch and session events
from client applications, pseudonymizes user identifiers, validates payloads, and
publishes to Kafka for downstream processing by the streaming feature pipeline.

## Pseudonymization

All endpoints accept a raw `user_id` and replace it with an HMAC-SHA256 digest
before the event leaves this service. The raw identifier **never appears in Kafka
topics, Redis, Parquet files, or logs** — only the hex digest (`pseudo_user_id`)
travels downstream.

The digest is deterministic: the same `user_id` + secret always produces the same
`pseudo_user_id`, so feature lookups in Redis and consent checks in the privacy
service remain consistent across services without sharing the raw identifier.

## Delivery Semantics

Events are published fire-and-forget (ADR 0003). A `202 Accepted` response means
the event was handed to the Kafka producer buffer, not that it was acknowledged by
the broker. Callers should not retry on `202` — the producer handles retries
internally up to its configured retry limit.
"""

_TAGS = [
    {
        "name": "events",
        "description": "Ingest watch and session events from client applications.",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: attach the producer to app.state so every request can access it
    # via request.app.state.producer without relying on a module-level global.
    # A single producer instance is intentional — confluent-kafka's Producer is
    # thread-safe and internally batches messages for efficiency.
    app.state.producer = KafkaProducer(settings.kafka_bootstrap_servers)
    yield
    # Shutdown: flush ensures buffered events are delivered before the process exits,
    # preventing silent data loss during rolling restarts or container stops.
    app.state.producer.flush()


app = FastAPI(
    title="Event Ingestion API",
    description=_DESCRIPTION,
    version="0.1.0",
    openapi_tags=_TAGS,
    lifespan=lifespan,
)


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}


@app.post(
    "/events/watch",
    status_code=202,
    response_model=AcceptedResponse,
    tags=["events"],
    summary="Ingest a watch event",
    description=(
        "Records a single content watch interaction. The raw `user_id` is pseudonymized "
        "before the event is published — it never appears in Kafka or any downstream store.\n\n"
        "**Delivery:** fire-and-forget. `202 Accepted` means the event entered the producer "
        "buffer; broker acknowledgement is not awaited. Do not retry on `202`.\n\n"
        "**Downstream:** the Flink feature pipeline consumes `user.watch.events` and updates "
        "`watch_count_10min`, `avg_watch_duration`, `category_affinity_score`, and `recency_score` "
        "in Redis within ~2 seconds of ingestion."
    ),
    response_description="Event accepted for asynchronous delivery to Kafka.",
)
def ingest_watch(request: Request, event: WatchEvent):
    # Pseudonymize first — the raw user_id must not appear anywhere past this point.
    # The digest is the stable identifier used in Redis keys, Parquet, and audit logs.
    pseudo_id = pseudonymize(event.user_id, settings.pseudonymize_secret)

    # Omit user_id from the payload entirely; only the digest travels to Kafka.
    # Downstream services (feature pipeline, inference API) only ever see pseudo_user_id.
    payload = {
        "pseudo_user_id": pseudo_id,
        "content_id": event.content_id,
        "watch_pct": event.watch_pct,
        "timestamp": event.timestamp,
        "genre": event.genre,
        "timezone": event.timezone,
    }
    request.app.state.producer.publish(TOPIC_WATCH, payload)

    # 202 Accepted: event is enqueued for delivery but not yet confirmed by the broker.
    # This matches the fire-and-forget contract — callers should not retry on 202.
    return JSONResponse(status_code=202, content={"accepted": True})


@app.post(
    "/events/session",
    status_code=202,
    response_model=AcceptedResponse,
    tags=["events"],
    summary="Ingest a session event",
    description=(
        "Records the start of a user viewing session. The raw `user_id` is pseudonymized "
        "before the event is published — it never appears in Kafka or any downstream store.\n\n"
        "**Delivery:** fire-and-forget. `202 Accepted` means the event entered the producer "
        "buffer; broker acknowledgement is not awaited. Do not retry on `202`.\n\n"
        "**Downstream:** the Flink feature pipeline consumes `user.session.events` and updates "
        "`session_genre_vector` and `time_of_day_bucket` in Redis within ~2 seconds of ingestion."
    ),
    response_description="Event accepted for asynchronous delivery to Kafka.",
)
def ingest_session(request: Request, event: SessionEvent):
    # Same pseudonymization contract as watch events — raw user_id never published.
    pseudo_id = pseudonymize(event.user_id, settings.pseudonymize_secret)

    payload = {
        "pseudo_user_id": pseudo_id,
        "session_id": event.session_id,
        "device": event.device,
        "start_time": event.start_time,
    }
    request.app.state.producer.publish(TOPIC_SESSION, payload)
    return JSONResponse(status_code=202, content={"accepted": True})
