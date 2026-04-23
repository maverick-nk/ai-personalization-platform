from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .config import settings
from .models import SessionEvent, WatchEvent
from .producer import KafkaProducer
from .pseudonymize import pseudonymize

# Topic names match the contracts expected by the Flink feature pipeline.
# Changing these requires a coordinated update in feature-pipeline/CONTEXT.md.
TOPIC_WATCH = "user.watch.events"
TOPIC_SESSION = "user.session.events"


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


app = FastAPI(title="event-ingestion", lifespan=lifespan)


@app.get("/health")
def health():
    # Used by Docker / Kubernetes liveness probes and the infra bootstrap script.
    return {"status": "ok"}


@app.post("/events/watch", status_code=202)
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


@app.post("/events/session", status_code=202)
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
