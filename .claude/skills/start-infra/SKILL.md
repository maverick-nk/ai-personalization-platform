---
name: start-infra
description: Starts local infrastructure via docker-compose, polls health checks for each service, and reports readiness. Use before running the test harness or any service that depends on Kafka, Redis, Postgres, or MLflow. Triggers on phrases like "start infra", "bring up infra", "start the stack", "/start-infra", "start docker", or "is the infra running".
---

# Start Infra

This skill brings up local infrastructure (Kafka, Redis, Postgres, MLflow), waits for each component to be healthy, and reports what's ready — so you know the environment is safe to develop against before writing or running code.

---

## Step 1 — Check Docker is Running

```bash
docker info
```

If Docker is not running: "Docker is not running. Start Docker Desktop and try again." — stop.

---

## Step 2 — Locate docker-compose File

Look for `docker-compose.yml` or `docker-compose.yaml` in the repo root and in `infra/`.

If not found: "No docker-compose file found. Has the infra bootstrap been completed? See Step 0 in `docs/implementation-plan.md`." — stop.

---

## Step 3 — Check Current Stack State

```bash
docker compose ps
```

If all required services are already `running` and healthy: "Stack is already up and healthy:" — list services and stop (don't restart unnecessarily).

If some services are stopped or unhealthy: report which ones, then proceed to Step 4.

If no services are running: proceed to Step 4.

---

## Step 4 — Start the Stack

```bash
docker compose up -d
```

Then poll until healthy or timeout (60s). Check each required service:

| Service | How to check health |
|---|---|
| Kafka | `docker compose exec kafka kafka-topics.sh --bootstrap-server localhost:9092 --list` exits 0 |
| Zookeeper | `docker compose exec zookeeper zkServer.sh status` shows `Mode: standalone` or `leader` |
| Redis | `docker compose exec redis redis-cli ping` returns `PONG` |
| Postgres | `docker compose exec postgres pg_isready -U postgres` returns `accepting connections` |
| MLflow | `curl -sf http://localhost:5000/health` returns 200 (or `curl -sf http://localhost:5000/` for older versions) |

Poll every 3 seconds. After 60 seconds, report which services are still unhealthy and stop.

---

## Step 5 — Verify Kafka Topics Exist

Once Kafka is healthy, check that the required topics are present:

```bash
docker compose exec kafka kafka-topics.sh --bootstrap-server localhost:9092 --list
```

Expected topics:
- `user.watch.events`
- `user.session.events`

If missing: 
```bash
docker compose exec kafka kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic user.watch.events --partitions 3 --replication-factor 1

docker compose exec kafka kafka-topics.sh --bootstrap-server localhost:9092 \
  --create --topic user.session.events --partitions 3 --replication-factor 1
```

Report whether topics were created or already existed.

---

## Step 6 — Final Status Report

```
Infrastructure Status — HH:MM
──────────────────────────────
✓ Kafka         ready  (topics: user.watch.events, user.session.events)
✓ Zookeeper     ready
✓ Redis         ready
✓ Postgres      ready
✓ MLflow        ready  (http://localhost:5000)

All services healthy. Safe to run the test harness or start a service.
```

If any service failed to start, show its last 20 log lines:
```bash
docker compose logs --tail=20 <service>
```

And suggest: "Check the logs above. Common fixes: port conflict (`lsof -i :<port>`), missing env var, or volume permission issue."
